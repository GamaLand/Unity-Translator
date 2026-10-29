param(
    [ValidateSet('Install','Remove','Launch')][string]$Action = 'Install',
    [string]$GameFolder = '',
    [string]$OutputParent = '',
    [string]$InstallFolder = '',
    [switch]$ReviewOnly,
    [ValidatePattern('^$|^[a-f0-9]{64}$')][string]$ReviewedPlanSha256 = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$script:nativeBlocks = [Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)
$script:nativeKeys = [Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)

# Fixed bundled installer. Manifest values are data, never PowerShell expressions.
# Source games are only opened for reading; installation creates an independent copy.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class RenpyCopyIdentity {
  [StructLayout(LayoutKind.Sequential)] struct Info {
    public uint Attributes; public System.Runtime.InteropServices.ComTypes.FILETIME Creation;
    public System.Runtime.InteropServices.ComTypes.FILETIME Access, Write;
    public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern SafeFileHandle CreateFile(string p,uint a,uint s,IntPtr sec,uint c,uint f,IntPtr t);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out Info i);
  [DllImport("kernel32.dll", SetLastError=true)]
  static extern bool SetFileTime(SafeFileHandle h,IntPtr creation,IntPtr access,ref System.Runtime.InteropServices.ComTypes.FILETIME write);
  [StructLayout(LayoutKind.Sequential)] struct Disposition { [MarshalAs(UnmanagedType.U1)] public bool DeleteFile; }
  [DllImport("kernel32.dll", SetLastError=true)]
  static extern bool SetFileInformationByHandle(SafeFileHandle h,int kind,ref Disposition info,uint size);
  [DllImport("kernel32.dll", EntryPoint="CreateDirectoryW", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool CreateDirectoryNative(string p,IntPtr security);
  public static string ReadHandle(SafeFileHandle h) {
    Info i;
    if(h.IsInvalid || !GetFileInformationByHandle(h,out i) || i.Links!=1 || (i.Attributes&0x400)!=0)
      throw new IOException("File identity/link check failed");
    return i.Volume.ToString("X8")+":"+i.IndexHigh.ToString("X8")+i.IndexLow.ToString("X8");
  }
  public static string Read(string p) {
    using(var h=CreateFile(p,0,7,IntPtr.Zero,3,0x00200000,IntPtr.Zero)) return ReadHandle(h);
  }
  public static SafeFileHandle HoldDirectory(string p) {
    var h=CreateFile(p,0,3,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
    Info i;
    if(h.IsInvalid || !GetFileInformationByHandle(h,out i) || (i.Attributes&0x400)!=0 || (i.Attributes&0x10)==0) {
      h.Dispose(); throw new IOException("Directory identity/link check failed");
    }
    return h;
  }
  public static void NewDirectory(string p) {
    if(!CreateDirectoryNative(p,IntPtr.Zero)) throw new IOException("A new independent output directory is required");
  }
  public static void CopyWriteTime(SafeFileHandle source,SafeFileHandle target) {
    Info i;
    if(!GetFileInformationByHandle(source,out i) || !SetFileTime(target,IntPtr.Zero,IntPtr.Zero,ref i.Write))
      throw new IOException("Copy timestamp verification failed");
  }
  public static bool DeleteUnchanged(string p,string identity,string digest) {
    using(var h=CreateFile(p,0x80010000,0,IntPtr.Zero,3,0x00200000,IntPtr.Zero)) {
      if(ReadHandle(h)!=identity) return false;
      using(var stream=new FileStream(h,FileAccess.Read))
      using(var sha=System.Security.Cryptography.SHA256.Create()) {
        var actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        if(actual!=digest) return false;
        var disposition=new Disposition { DeleteFile=true };
        if(!SetFileInformationByHandle(h,4,ref disposition,1)) throw new IOException("Owned-file deletion failed");
        return true;
      }
    }
  }
}
public static class RenpyCopyFormat {
  public static string Literal(string value) { return Literal(value,false); }
  public static string Literal(string value,bool say) {
    if(value.Length<2 || value[0]!='"' || value[value.Length-1]!='"') throw new IOException("Invalid quoted native literal");
    var result=new System.Text.StringBuilder();
    for(int i=1;i<value.Length-1;i++) {
      char c=value[i];
      if(c=='"' || c<32) throw new IOException("Invalid native literal character");
      if(say && c==' ' && value[i-1]==' ') continue;
      if(c=='\\') {
        if(++i>=value.Length-1) throw new IOException("Invalid native literal escape");
        c=value[i];
        if(c=='n') c='\n'; else if(c=='r') c=say ? 'r' : '\r';
        else if(c=='u' && i+4<value.Length-1 && value.Substring(i+1,4)=="000d") { c='\r'; i+=4; }
        else if(c!='\\' && c!='"' && !(say && c==' ')) throw new IOException("Unsupported native literal escape");
      }
      result.Append(c);
    }
    return result.ToString();
  }
  static bool In(string value,string names) { return (" "+names+" ").Contains(" "+value+" "); }
  static bool Match(string value,string pattern) { return System.Text.RegularExpressions.Regex.IsMatch(value,"\\A(?:"+pattern+")\\z",System.Text.RegularExpressions.RegexOptions.CultureInvariant); }
  static System.Collections.Generic.List<string> Tokens(string text) {
    if(text.Length>1000000 || text.Contains("__UT_")) throw new IOException("Invalid native text bounds");
    for(int j=0;j<text.Length;j++) {
      char c=text[j];
      if((c<32 && c!='\r' && c!='\n') || c=='\u0085' || c=='\u2028' || c=='\u2029' || c=='\u3016' || c=='\u3017') throw new IOException("Unsupported native text character");
      if(char.IsHighSurrogate(c)) {
        if(j+1>=text.Length || !char.IsLowSurrogate(text[++j])) throw new IOException("Unpaired native text surrogate");
      } else if(char.IsLowSurrogate(c)) throw new IOException("Unpaired native text surrogate");
    }
    var result=new System.Collections.Generic.List<string>();
    var tags=new System.Collections.Generic.Stack<string>();
    int i=0;
    while(i<text.Length) {
      int start=i; char c=text[i];
      string pair=i+1<text.Length ? text.Substring(i,2) : "";
      if(pair=="[[" || pair=="{{" || pair=="%%" || pair=="\r\n") i+=2;
      else if(c=='\r' || c=='\n') i++;
      else if(c=='[') {
        int depth=1; char quote='\0'; bool escaped=false; i++;
        while(i<text.Length && depth>0) {
          char current=text[i];
          if(i-start>8192 || current=='\r' || current=='\n') throw new IOException("Native interpolation bounds exceeded");
          if(escaped) escaped=false;
          else if(current=='\\') escaped=true;
          else if(quote!='\0') { if(current==quote) quote='\0'; }
          else if(current=='"' || current=='\'') quote=current;
          else if(current=='[') { if(++depth>32) throw new IOException("Native interpolation nesting exceeded"); }
          else if(current==']') depth--;
          i++;
        }
        if(depth!=0 || quote!='\0' || text.Substring(start+1,i-start-2).Trim().Length==0) throw new IOException("Unbalanced native interpolation");
      } else if(c=='{') {
        int end=text.IndexOf('}',start+1,Math.Min(8192,text.Length-start-1));
        if(end<0) throw new IOException("Unclosed native tag");
        string value=text.Substring(start+1,end-start-1);
        if(value.IndexOfAny(new char[]{'{','[','\r','\n','\\'})>=0) throw new IOException("Unsupported native tag argument");
        if(value.StartsWith("#",StringComparison.Ordinal)) {
          if(value.Length<2 || value.Length>1024) throw new IOException("Invalid native context tag");
        } else if(value.StartsWith("/",StringComparison.Ordinal)) {
          if(tags.Count==0 || tags.Pop()!=value.Substring(1)) throw new IOException("Unbalanced native tags");
        } else {
          int separator=value.IndexOf('=');
          string name=separator<0 ? value : value.Substring(0,separator);
          string argument=separator<0 ? "" : value.Substring(separator+1);
          if(In(name,"b i u s alt noalt") && separator<0) tags.Push(name);
          else if(In(name,"color outlinecolor size alpha cps k font a") && separator>=0 && argument.Length>0) {
            if(In(name,"color outlinecolor") && !Match(argument,"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}")) throw new IOException("Invalid native color tag");
            if(In(name,"size alpha cps k") && !Match(argument,"[+*\\-]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)")) throw new IOException("Invalid native numeric tag");
            tags.Push(name);
          } else if(In(name,"w p nw fast done") && (separator<0 || (In(name,"w p") && Match(argument,"\\d+(?:\\.\\d+)?")))) { }
          else if(In(name,"image space vspace") && separator>=0 && argument.Length>0) {
            if(name!="image" && !Match(argument,"\\d+")) throw new IOException("Invalid native spacing tag");
          } else throw new IOException("Unknown native text tag");
          if(tags.Count>32) throw new IOException("Native tag nesting exceeded");
        }
        i=end+1;
      } else { i++; continue; }
      result.Add(text.Substring(start,i-start));
    }
    if(tags.Count!=0) throw new IOException("Native tags must close explicitly");
    return result;
  }
  public static void Compare(string source,string target) {
    var left=Tokens(source); var right=Tokens(target);
    if(left.Count!=right.Count) throw new IOException("Native protected tokens changed");
    for(int i=0;i<left.Count;i++) if(left[i]!=right[i]) throw new IOException("Native protected tokens changed");
  }
}
'@

function Checked([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.StartsWith('\\') -or $full.StartsWith('//') -or $full.Substring(2).Contains(':')) { throw 'Local disk required.' }
    $walk = $full
    while ($walk) {
        if (Test-Path -LiteralPath $walk) {
            if (((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse path refused.' }
        }
        $walk = [IO.Path]::GetDirectoryName($walk)
    }
    if (([IO.DriveInfo]::new([IO.Path]::GetPathRoot($full))).DriveType -eq [IO.DriveType]::Network) { throw 'Network disk refused.' }
    if ($full.Length -eq [IO.Path]::GetPathRoot($full).Length) { return $full }
    return $full.TrimEnd('\')
}
function Confined([string]$Root,[string]$Relative) {
    if (-not $Relative -or [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) { throw 'Invalid relative path.' }
    foreach ($part in ($Relative -split '[\\/]')) {
        if (-not $part -or $part -eq '.' -or $part -eq '..' -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '[<>:"|?*\x00-\x1f]' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$') { throw 'Invalid path component.' }
    }
    $full = Checked ([IO.Path]::Combine($Root,$Relative.Replace('/', '\')))
    if (-not $full.StartsWith($Root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped root.' }
    return $full
}
function Overlaps([string]$Left,[string]$Right) {
    return $Left.Equals($Right,[StringComparison]::OrdinalIgnoreCase) -or $Left.StartsWith($Right.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -or $Right.StartsWith($Left.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)
}
function BytesDigest([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Digest([string]$Path) {
    $stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        $null = [RenpyCopyIdentity]::ReadHandle($stream.SafeFileHandle)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}
function GameClosed([string]$Root) {
    $expected = Confined $Root $package.game_executable
    $name = [IO.Path]::GetFileNameWithoutExtension($package.game_executable)
    foreach ($process in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        try { $image = $process.Path } catch { throw 'Game process identity unavailable; close the game.' }
        if (-not $image -or [string]::Equals([IO.Path]::GetFullPath($image),$expected,[StringComparison]::OrdinalIgnoreCase)) { throw 'Close the game before changing its copy.' }
    }
}
function SelectFolder([string]$Description) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = [Windows.Forms.FolderBrowserDialog]::new()
    $dialog.Description = $Description
    if ($dialog.ShowDialog() -ne 'OK') { throw 'Folder selection cancelled; no files written.' }
    return $dialog.SelectedPath
}
function CheckBuild([string]$Root) {
    GameClosed $Root
    $version = Confined $Root 'renpy/vc_version.py'
    if (-not (Test-Path -LiteralPath $version -PathType Leaf) -or (Get-Item -LiteralPath $version).Length -gt 8192) { throw 'Pinned engine version evidence missing.' }
    $versionText = [Text.UTF8Encoding]::new($false,$true).GetString([IO.File]::ReadAllBytes($version))
    if ($versionText -cnotmatch '(?m)^version = [''"]8\.1\.2\.23090503[''"]\r?$') { throw 'Pinned RenPy 8.1.2 build required.' }
    foreach ($entry in $package.copy_files) {
        $path = Confined $Root $entry.path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or (Digest $path) -cne $entry.sha256) { throw ('Matching original build required: '+$entry.path) }
    }
}
function CheckNative([string]$Path) {
    $raw = [IO.File]::ReadAllBytes($Path)
    if ($raw.Length -gt 2097152) { throw 'Oversized native payload.' }
    $text = [Text.UTF8Encoding]::new($false,$true).GetString($raw)
    if ($text.Contains("`r") -or $text.Contains("`t") -or $text.Contains([string][char]0)) { throw 'Native output must use fixed UTF-8/LF grammar.' }
    $literal = '"(?:[^"\\\x00-\x1f]|\\(?:[\\"nr]|u000d))*"'
    $sayLiteral = '"(?:[^"\\\x00-\x1f]|\\(?:[\\"nr ]|u000d))*"'
    $name = '[A-Za-z_][A-Za-z_0-9]*'
    $say = '^(?:(?<speaker>'+$name+')(?<attributes>(?: -?'+$name+')*)(?<temporary> @ -?'+$name+'(?: -?'+$name+')*)? )?(?<literal>'+$sayLiteral+')(?<suffix> nointeract)?$'
    $header = '^translate '+[regex]::Escape($package.language)+' ([A-Za-z_][A-Za-z_0-9]*):$'
    $block = ''; $pending = $null; $speaker = ''; $blockRecords = 0; $records = 0
    $blocks = $script:nativeBlocks
    $keys = $script:nativeKeys
    foreach ($line in ($text -split "`n")) {
        if ($line.Length -gt 65536) { throw 'Native physical line too long.' }
        if (-not $line.Trim()) { continue }
        if ($line.StartsWith('#',[StringComparison]::Ordinal)) { continue }
        $match = [regex]::Match($line,$header)
        if ($match.Success) {
            if ($null -ne $pending -or ($block -and $blockRecords -eq 0)) { throw 'Incomplete native block.' }
            $block = $match.Groups[1].Value; $blockRecords = 0
            if ($block -cin @('python','style','default','None') -or ($block -cne 'strings' -and $blocks.ContainsKey($block))) { throw 'Executable or duplicate native block.' }
            $blocks[$block] = $true; continue
        }
        if (-not $block) { throw 'Native statement outside translation block.' }
        if ($block -ceq 'strings') {
            $old = [regex]::Match($line,'^    old ('+$literal+')$')
            if ($old.Success -and $null -eq $pending) {
                $pending = [RenpyCopyFormat]::Literal($old.Groups[1].Value)
                if (-not $pending.Trim() -or $keys.ContainsKey($pending)) { throw 'Empty or duplicate native string key.' }
                $keys[$pending] = $true; continue
            }
            $new = [regex]::Match($line,'^    new ('+$literal+')$')
            if (-not $new.Success -or $null -eq $pending) { throw 'Only paired old/new native strings are accepted.' }
            $translation = [RenpyCopyFormat]::Literal($new.Groups[1].Value)
        } else {
            if ($line.StartsWith('    # ',[StringComparison]::Ordinal)) {
                $source = [regex]::Match($line.Substring(6),$say)
                if (-not $source.Success -or $null -ne $pending) { throw 'Ambiguous native source comment.' }
                $speaker = $source.Groups['speaker'].Value
                $shape = $speaker+'|'+$source.Groups['attributes'].Value+'|'+$source.Groups['temporary'].Value+'|'+$source.Groups['suffix'].Value
                $pending = [RenpyCopyFormat]::Literal($source.Groups['literal'].Value,$true)
                if (-not $pending.Trim()) { throw 'Empty native dialogue source.' }
                continue
            }
            if (-not $line.StartsWith('    ',[StringComparison]::Ordinal)) { throw 'Invalid native indentation.' }
            $targetSay = [regex]::Match($line.Substring(4),$say)
            $targetShape = $targetSay.Groups['speaker'].Value+'|'+$targetSay.Groups['attributes'].Value+'|'+$targetSay.Groups['temporary'].Value+'|'+$targetSay.Groups['suffix'].Value
            if (-not $targetSay.Success -or $null -eq $pending -or $targetShape -cne $shape) { throw 'Only matching quoted native say statements are accepted.' }
            if ($speaker -cin @('python','init','style','define','default','jump','call','return','show','scene','hide','with','image','menu','screen','translate','old','new','pass','extend')) { throw 'Unsupported native speaker.' }
            $translation = [RenpyCopyFormat]::Literal($targetSay.Groups['literal'].Value,$true)
        }
        if (-not $translation.Trim()) { throw 'Native translation is empty.' }
        [RenpyCopyFormat]::Compare($pending,$translation)
        $pending = $null; $records++; $blockRecords++
        if ($records -gt 10000) { throw 'Native record limit exceeded.' }
    }
    if ($null -ne $pending -or $records -eq 0 -or $blockRecords -eq 0) { throw 'Incomplete native translation payload.' }
}
function NeedDirectory([string]$Path) {
    $full = Checked $Path
    if ($script:directoryGuards.ContainsKey($full)) { return }
    $parent = [IO.Path]::GetDirectoryName($full)
    if (-not (Test-Path -LiteralPath $full)) {
        if ($parent -and $full -ne $target) { NeedDirectory $parent }
        [void][IO.Directory]::CreateDirectory($full)
    }
    $script:directoryGuards[$full] = [RenpyCopyIdentity]::HoldDirectory((Checked $full))
}
function WriteNew([string]$Relative,[byte[]]$Bytes) {
    $path = Confined $target $Relative
    NeedDirectory ([IO.Path]::GetDirectoryName($path))
    $path = Confined $target $Relative
    $output = [IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $identity = [RenpyCopyIdentity]::ReadHandle($output.SafeFileHandle)
        Journal @{path=$Relative;sha256=(BytesDigest $Bytes);identity=$identity}
        $output.Write($Bytes,0,$Bytes.Length); $output.Flush($true)
    } finally { $output.Dispose() }
    if ((Digest $path) -cne (BytesDigest $Bytes)) { throw 'Written file integrity check failed.' }
    return @{path=$Relative;sha256=(BytesDigest $Bytes);identity=$identity}
}
function CopyNew([string]$Root,$Entry) {
    $source = Confined $Root $Entry.path
    $destination = Confined $target $Entry.path
    NeedDirectory ([IO.Path]::GetDirectoryName($destination))
    $inputFile = [IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        $null = [RenpyCopyIdentity]::ReadHandle($inputFile.SafeFileHandle)
        if ($inputFile.Length -ne $Entry.bytes) { throw 'Source file size changed.' }
        $output = [IO.File]::Open((Confined $target $Entry.path),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $identity = [RenpyCopyIdentity]::ReadHandle($output.SafeFileHandle)
            Journal @{path=$Entry.path;sha256=$Entry.sha256;identity=$identity}
            $inputFile.CopyTo($output); $output.Flush($true)
            [RenpyCopyIdentity]::CopyWriteTime($inputFile.SafeFileHandle,$output.SafeFileHandle)
        } finally { $output.Dispose() }
    } finally { $inputFile.Dispose() }
    if ((Digest $destination) -cne $Entry.sha256 -or (Digest $source) -cne $Entry.sha256) { throw 'Copy integrity check failed.' }
    return @{path=$Entry.path;sha256=$Entry.sha256;identity=$identity}
}
function Journal($Record) {
    if ($null -eq $script:journalStream) { return }
    $raw = [Text.UTF8Encoding]::new($false).GetBytes(($Record | ConvertTo-Json -Compress)+"`n")
    $script:journalStream.Write($raw,0,$raw.Length)
    $script:journalStream.Flush($true)
}

$packageRoot = Checked $PSScriptRoot
$script:directoryGuards = @{}
$script:journalStream = $null
$manifestPath = Confined $packageRoot 'package.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or (Get-Item -LiteralPath $manifestPath).Length -gt 33554432) { throw 'Missing or oversized package manifest.' }
$manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
$manifestHash = BytesDigest $manifestBytes
$package = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
if ($package.format_version -notin @(1,2) -or $package.purpose -cne 'unitytranslator-renpy-translated-copy' -or $package.package_id -isnot [string] -or $package.package_id -cnotmatch '^[a-f0-9]{32}$' -or $package.copy_folder -cne ('UnityTranslatorRenpy-'+$package.package_id) -or $package.metadata_folder -cne '.unitytranslator/renpy-copy' -or $package.launcher -cne 'Play-Translated.cmd' -or $package.language -isnot [string] -or $package.language -cnotmatch '^[A-Za-z_][A-Za-z_0-9]{0,127}$' -or $package.language -cin @('None','python','style','default','strings')) { throw 'Invalid translated-copy manifest.' }
if ($package.game_executable -match '[\\/]' -or [IO.Path]::GetExtension($package.game_executable) -ine '.exe') { throw 'Invalid game executable selection.' }
if (@($package.copy_files).Count -lt 1 -or @($package.copy_files).Count -gt 20000 -or @($package.payloads).Count -lt 1 -or @($package.payloads).Count -gt 512) { throw 'Invalid copy or payload count.' }
if ((Digest $PSCommandPath) -cne $package.installer_sha256) { throw 'Installer hash mismatch.' }
$allowed = @{}; $bytes = [long]0
foreach ($entry in @($package.copy_files)+@($package.payloads)) {
    $key = $entry.path.ToLowerInvariant()
    if ($entry.path -isnot [string] -or $entry.sha256 -isnot [string] -or ($entry.bytes -isnot [int] -and $entry.bytes -isnot [long]) -or $allowed.ContainsKey($key) -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $entry.bytes -lt 0) { throw 'Invalid or duplicate copy-file manifest.' }
    if ($entry.path.StartsWith('.unitytranslator/',[StringComparison]::OrdinalIgnoreCase) -or $entry.path -ieq $package.launcher) { throw 'Copy metadata namespace collision.' }
    $null = Confined $packageRoot $entry.path
    $allowed[$key] = $entry; $bytes += $entry.bytes
}
if ($bytes -gt 34359738368 -or -not $allowed.ContainsKey($package.game_executable.ToLowerInvariant())) { throw 'Copy size or executable manifest invalid.' }
if (-not $allowed.ContainsKey('renpy/vc_version.py')) { throw 'Pinned engine version evidence is required.' }
foreach ($entry in $package.copy_files) {
    if ($entry.path -imatch '(^|[\\/])(\.git|\.hg|\.svn|\.agents|\.codex|\.claude|\.cursor|\.ssh|\.aws|\.gnupg|\.aider[^\\/]*|\.env(?:\.[^\\/]*)?)([\\/]|$)') { throw 'A reviewed clean build is required; private tooling or credential metadata cannot enter a copy plan.' }
    if ($entry.path -imatch '^game/(saves|cache)/|(^|/)__pycache__/[^/]+\.pyc$|^(log|traceback|errors)\.txt$' -or $entry.path -imatch ('^game/tl/'+[regex]::Escape($package.language)+'/')) { throw 'Copy manifest includes an excluded runtime file or existing target language.' }
}
$payloadBytes = [long]0
foreach ($entry in $package.payloads) {
    if ($entry.path -cnotmatch ('^game/tl/'+[regex]::Escape($package.language)+'/ut_[a-f0-9]{64}(?:_[0-9]{4})?\.rpy$') -or $entry.bytes -gt 2097152) { throw 'Invalid native payload path or size.' }
    $payloadBytes += $entry.bytes
}
if ($payloadBytes -gt 67108864) { throw 'Native payload size limit exceeded.' }

if ($Action -eq 'Launch') {
    $target = Checked ([IO.Path]::Combine($packageRoot,'../..'))
    if ([IO.Path]::GetFileName($target) -cne $package.copy_folder) { throw 'Installed copy identity mismatch.' }
    $receiptPath = Confined $target ($package.metadata_folder+'/receipt.json')
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.target -cne $target -or $receipt.package_id -cne $package.package_id -or $receipt.manifest_sha256 -cne $manifestHash -or $receipt.status -cne 'installed') { throw 'Completed owned installation required.' }
    CheckBuild $target
    foreach ($entry in $package.payloads) {
        if ((Digest (Confined $target $entry.path)) -cne $entry.sha256) { throw 'Installed translation changed; review a new package.' }
        CheckNative (Confined $target $entry.path)
    }
    $save = Confined $target ($package.metadata_folder+'/saves')
    $logs = Confined $target ($package.metadata_folder+'/logs')
    if ($ReviewOnly) {
        Write-Output (@{action='Launch';executable=(Confined $target $package.game_executable);language=$package.language;save_directory=$save;log_directory=$logs;game_started=$false} | ConvertTo-Json)
        exit 0
    }
    [void][IO.Directory]::CreateDirectory($save); [void][IO.Directory]::CreateDirectory($logs)
    $keys = @('RENPY_LANGUAGE','RENPY_PATH_TO_SAVES','RENPY_LOG_BASE','PYTHONDONTWRITEBYTECODE')
    $old = @{}
    foreach ($key in $keys) { $old[$key] = [Environment]::GetEnvironmentVariable($key,'Process') }
    try {
        [Environment]::SetEnvironmentVariable('RENPY_LANGUAGE',$package.language,'Process')
        [Environment]::SetEnvironmentVariable('RENPY_PATH_TO_SAVES',$save,'Process')
        [Environment]::SetEnvironmentVariable('RENPY_LOG_BASE',$logs,'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE','1','Process')
        Start-Process -FilePath (Confined $target $package.game_executable) -ArgumentList @('--savedir',('"'+$save+'"')) -WorkingDirectory $target | Out-Null
    } finally { foreach ($key in $keys) { [Environment]::SetEnvironmentVariable($key,$old[$key],'Process') } }
    exit 0
}

if ($Action -eq 'Remove') {
    if (-not $InstallFolder) { $InstallFolder = SelectFolder 'Select the translated copy to remove' }
    $target = Checked $InstallFolder
    if ([IO.Path]::GetFileName($target) -cne $package.copy_folder) { throw 'Wrong translated-copy folder.' }
    GameClosed $target
    $receiptPath = Confined $target ($package.metadata_folder+'/receipt.json')
    if ((Get-Item -LiteralPath $receiptPath).Length -gt 16777216) { throw 'Receipt too large.' }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.target -cne $target -or $receipt.package_id -cne $package.package_id -or $receipt.manifest_sha256 -cne $manifestHash -or (Overlaps $target (Checked $receipt.original_game))) { throw 'Receipt game/package identity mismatch.' }
    $allowed[$package.launcher.ToLowerInvariant()] = @{sha256=$package.launcher_sha256}
    $allowed[($package.metadata_folder+'/package.json').ToLowerInvariant()] = @{sha256=$manifestHash}
    $allowed[($package.metadata_folder+'/renpy-copy.ps1').ToLowerInvariant()] = @{sha256=$package.installer_sha256}
    $allowed[($package.metadata_folder+'/reviewed-plan.json').ToLowerInvariant()] = @{sha256=$receipt.reviewed_plan_file_sha256}
    $allowed[($package.metadata_folder+'/install-start.json').ToLowerInvariant()] = @{sha256=$receipt.installation_start_sha256}
    $seen = @{}
    foreach ($entry in $receipt.files) {
        $key = $entry.path.ToLowerInvariant()
        if ($seen.ContainsKey($key) -or -not $allowed.ContainsKey($key) -or $allowed[$key].sha256 -cne $entry.sha256 -or $entry.identity -cnotmatch '^[A-F0-9]{8}:[A-F0-9]{16}$') { throw 'Receipt contains an unowned or changed file claim.' }
        $null = Confined $target $entry.path; $seen[$key] = $true
    }
    $removalRelative = ''
    for ($index=1; $index -le 1000; $index++) {
        $candidate = $package.metadata_folder+('/removal-{0:d4}.json' -f $index)
        if (-not (Test-Path -LiteralPath (Confined $target $candidate))) { $removalRelative=$candidate; break }
    }
    if (-not $removalRelative) { throw 'Removal audit limit exceeded; preserve existing receipts.' }
    $plan = @{format_version=1;action='Remove';target=$target;manifest_sha256=$manifestHash;files=$receipt.files;removal_receipt=$removalRelative}
    $planRaw = [Text.UTF8Encoding]::new($false).GetBytes(($plan | ConvertTo-Json -Depth 12 -Compress))
    $binding = $target+"`n"+$manifestHash+"`n"+(Digest $receiptPath)+"`n"+$removalRelative+"`n"
    foreach ($entry in $receipt.files) { $binding += $entry.path+"`t"+$entry.sha256+"`t"+$entry.identity+"`n" }
    $planHash = BytesDigest ([Text.Encoding]::UTF8.GetBytes($binding))
    if ($ReviewOnly) { Write-Output (@{plan=$plan;sha256=$planHash} | ConvertTo-Json -Depth 15); exit 0 }
    if ($ReviewedPlanSha256) {
        if ($ReviewedPlanSha256 -cne $planHash) { throw 'Removal plan changed; review again.' }
    } else {
        Write-Output ($plan | ConvertTo-Json -Depth 12)
        if ((Read-Host 'Only unchanged owned COPY files are removed. Type REMOVE') -cne 'REMOVE') { throw 'Removal not approved.' }
    }
    $preserved = [Collections.Generic.List[string]]::new()
    NeedDirectory $target
    foreach ($entry in @($receipt.files | Sort-Object path -Descending)) {
        GameClosed $target
        $path = Confined $target $entry.path
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            NeedDirectory ([IO.Path]::GetDirectoryName($path))
            if (-not [RenpyCopyIdentity]::DeleteUnchanged((Confined $target $entry.path),$entry.identity,$entry.sha256)) { $preserved.Add($entry.path) }
        } catch { $preserved.Add($entry.path) }
    }
    $report = @{status='owned_files_removed_runtime_data_retained';target=$target;changed_files_preserved=@($preserved);runtime_files_preserved=$true;original_game_modified=$false;reviewed_plan_sha256=$planHash;removal_receipt=$removalRelative}
    $reportRaw = [Text.UTF8Encoding]::new($false).GetBytes(($report | ConvertTo-Json -Depth 5))
    $null = WriteNew $removalRelative $reportRaw
    foreach ($handle in $script:directoryGuards.Values) { $handle.Dispose() }
    Write-Output ([Text.Encoding]::UTF8.GetString($reportRaw))
    # The receipt and runtime-created/modified files remain. Never recursively delete.
    exit 0
}

if (-not $GameFolder) { $GameFolder = SelectFolder 'Select the matching ORIGINAL game (read only)' }
if (-not $OutputParent) { $OutputParent = SelectFolder 'Select a separate parent for the NEW translated copy' }
$game = Checked $GameFolder
$parent = Checked $OutputParent
if (-not (Test-Path -LiteralPath $game -PathType Container) -or -not (Test-Path -LiteralPath $parent -PathType Container)) { throw 'Existing original game and output parent required.' }
$target = Confined $parent $package.copy_folder
if ((Overlaps $target $game) -or (Overlaps $target $packageRoot) -or (Test-Path -LiteralPath $target)) { throw 'A new independent copy directory is required; nothing overwritten.' }
CheckBuild $game
foreach ($entry in $package.payloads) {
    $source = Confined ($packageRoot+'\payload') $entry.path
    if ((Digest $source) -cne $entry.sha256 -or (Get-Item -LiteralPath $source).Length -ne $entry.bytes) { throw 'Native payload integrity mismatch.' }
    CheckNative $source
}
$launcherBytes = [IO.File]::ReadAllBytes((Confined $packageRoot $package.launcher))
if ((BytesDigest $launcherBytes) -cne $package.launcher_sha256) { throw 'Launcher integrity mismatch.' }
$planFiles = @($package.copy_files)+@($package.payloads)+@(
    @{path=$package.launcher;sha256=$package.launcher_sha256;bytes=$launcherBytes.Length},
    @{path=($package.metadata_folder+'/package.json');sha256=$manifestHash;bytes=$manifestBytes.Length},
    @{path=($package.metadata_folder+'/renpy-copy.ps1');sha256=$package.installer_sha256;bytes=(Get-Item -LiteralPath $PSCommandPath).Length}
)
$plan = [ordered]@{format_version=1;action='Install';original_game=$game;target=$target;package_id=$package.package_id;manifest_sha256=$manifestHash;files=$planFiles;copy_omissions=$package.copy_omissions;save_policy=$package.save_policy;receipt=($package.metadata_folder+'/receipt.json');reviewed_plan=($package.metadata_folder+'/reviewed-plan.json');installation_start=($package.metadata_folder+'/install-start.json');journal=($package.metadata_folder+'/install-journal.jsonl');receipt_updates='The journal records file identity before each write. Incomplete copies are retained for recovery; nothing is overwritten or automatically cleaned.'}
$planRaw = [Text.UTF8Encoding]::new($false).GetBytes(($plan | ConvertTo-Json -Depth 12 -Compress))
$binding = $game+"`n"+$target+"`n"+$manifestHash+"`n"
foreach ($entry in $planFiles) { $binding += $entry.path+"`t"+$entry.sha256+"`t"+$entry.bytes+"`n" }
$planHash = BytesDigest ([Text.Encoding]::UTF8.GetBytes($binding))
if ($ReviewOnly) { Write-Output (@{plan=$plan;sha256=$planHash} | ConvertTo-Json -Depth 15); exit 0 }
if ($ReviewedPlanSha256) {
    if ($ReviewedPlanSha256 -cne $planHash) { throw 'The reviewed copy plan changed; review again.' }
} else {
    Write-Output ($plan | ConvertTo-Json -Depth 12)
    Write-Output ('Copy plan SHA-256: '+$planHash)
    if ((Read-Host 'Review every new copy file above. Type INSTALL') -cne 'INSTALL') { throw 'Copy installation not approved; nothing written.' }
}
CheckBuild $game
if (Test-Path -LiteralPath $target) { throw 'Copy target appeared after review; nothing overwritten.' }
$script:receipt = @{format_version=1;package_id=$package.package_id;manifest_sha256=$manifestHash;original_game=$game;target=$target;status='installing';reviewed_plan_sha256=$planHash;reviewed_plan_file_sha256=(BytesDigest $planRaw);files=@()}
try {
    NeedDirectory $parent
    [RenpyCopyIdentity]::NewDirectory((Checked $target))
    $script:directoryGuards[$target] = [RenpyCopyIdentity]::HoldDirectory((Checked $target))
    NeedDirectory (Confined $target $package.metadata_folder)
    $journalPath = Confined $target ($package.metadata_folder+'/install-journal.jsonl')
    $script:journalStream = [IO.File]::Open($journalPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $journalIdentity = [RenpyCopyIdentity]::ReadHandle($script:journalStream.SafeFileHandle)
    $startRaw = [Text.UTF8Encoding]::new($false).GetBytes(($script:receipt | ConvertTo-Json -Depth 12))
    $script:receipt.installation_start_sha256 = BytesDigest $startRaw
    $script:receipt.files += WriteNew ($package.metadata_folder+'/install-start.json') $startRaw
    $script:receipt.files += WriteNew ($package.metadata_folder+'/reviewed-plan.json') $planRaw
    $script:receipt.files += WriteNew ($package.metadata_folder+'/package.json') $manifestBytes
    $script:receipt.files += WriteNew ($package.metadata_folder+'/renpy-copy.ps1') ([IO.File]::ReadAllBytes($PSCommandPath))
    $script:receipt.files += WriteNew $package.launcher $launcherBytes
    foreach ($entry in $package.copy_files) {
        $script:receipt.files += CopyNew $game $entry
    }
    foreach ($entry in $package.payloads) {
        $script:receipt.files += CopyNew ($packageRoot+'\payload') $entry
    }
    CheckBuild $game
    $script:journalStream.Dispose(); $script:journalStream = $null
    $script:receipt.status = 'installed'
    $script:receipt.journal = @{path=($package.metadata_folder+'/install-journal.jsonl');identity=$journalIdentity;sha256=(Digest $journalPath)}
    $receiptRaw = [Text.UTF8Encoding]::new($false).GetBytes(($script:receipt | ConvertTo-Json -Depth 12))
    $null = WriteNew ($package.metadata_folder+'/receipt.json') $receiptRaw
    Write-Output (@{status='installed';target=$target;records=$package.records;plan_sha256=$planHash;original_game_modified=$false;game_started=$false} | ConvertTo-Json)
} catch {
    Write-Warning 'Incomplete copy retained with its start marker and durable journal. No original game file was written.'
    throw
} finally {
    if ($null -ne $script:journalStream) { $script:journalStream.Dispose() }
    foreach ($handle in $script:directoryGuards.Values) { $handle.Dispose() }
}
