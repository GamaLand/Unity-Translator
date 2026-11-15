# Shared recipient core. The exporter inlines this text into each bundled installer at
# its single marker line, so every distributed script stays self-contained and frozen.
# Windows built-in PowerShell/.NET only; never starts a game, downloads code or reads
# manifest values as PowerShell expressions.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class RecipientIdentity {
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
  public static bool DeleteEmptyDirectory(string p,string identity) {
    using(var h=CreateFile(p,0x10000,0,IntPtr.Zero,3,0x02200000,IntPtr.Zero)) {
      if(ReadHandle(h)!=identity) return false;
      var disposition=new Disposition { DeleteFile=true };
      return SetFileInformationByHandle(h,4,ref disposition,1);
    }
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
// One Windows name rule, the same as filesystem.ambiguous_windows_name: Windows and .NET
// treat these names as devices, drop trailing dots, spaces, NEL or NBSP, or refuse them.
public static class RecipientPath {
  static readonly string[] Devices = "CON PRN AUX NUL CONIN$ CONOUT$ COM1 COM2 COM3 COM4 COM5 COM6 COM7 COM8 COM9 COM\u00b9 COM\u00b2 COM\u00b3 LPT1 LPT2 LPT3 LPT4 LPT5 LPT6 LPT7 LPT8 LPT9 LPT\u00b9 LPT\u00b2 LPT\u00b3".Split(' ');
  public static bool Ambiguous(string name) {
    if(string.IsNullOrEmpty(name) || name.Length>255) return true;
    char last=name[name.Length-1];
    if(last=='.' || last==' ' || last=='\u0085' || last=='\u00a0') return true;
    foreach(char c in name) if(c<32 || c=='<' || c=='>' || c=='"' || c=='|' || c=='?' || c=='*') return true;
    int dot=name.IndexOf('.');
    string stem=(dot<0 ? name : name.Substring(0,dot)).TrimEnd(' ');
    // Windows matches device names in ASCII only, so only ASCII letters are upper-cased.
    var upper=new System.Text.StringBuilder(stem.Length);
    foreach(char c in stem) upper.Append(c>='a' && c<='z' ? (char)(c-32) : c);
    return Array.IndexOf(Devices,upper.ToString())>=0;
  }
  static bool Separator(char c) { return c=='\\' || c=='/'; }
  // The refusals of filesystem.checked_path that GetFullPath would hide; returns the refusal
  // message or null. Like pathlib, '.' and empty components are collapsed, not refused.
  public static string Refusal(string p) {
    if(string.IsNullOrEmpty(p)) return "Invalid path.";
    if((p.Length>1 && Separator(p[0]) && Separator(p[1])) || (p.Length>2 && p.Substring(2).IndexOf(':')>=0)) return "Local disk required.";
    int start=0;
    if(p.Length>1 && p[1]==':') {
      if(p.Length==2 || !Separator(p[2])) return "Drive-relative path refused.";
      start=3;
    } else if(Separator(p[0])) start=1;
    string rest=p.Substring(start);
    if(rest.Length>0 && Separator(rest[rest.Length-1])) rest=rest.Substring(0,rest.Length-1);
    if(rest.Length==0) return null;
    foreach(string part in rest.Split('\\','/')) {
      if(part.Length==0 || part==".") continue;
      if(part=="..") return "Path traversal refused.";
      if(Ambiguous(part)) return "Reserved or ambiguous path name refused.";
    }
    return null;
  }
}
public static class RecipientProcess {
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool QueryFullProcessImageNameW(IntPtr h,uint flags,System.Text.StringBuilder name,ref uint size);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
  // Null means the image is unreadable, as with a protected or exited process.
  public static string Image(int pid) {
    IntPtr h=OpenProcess(0x1000,false,(uint)pid);
    if(h==IntPtr.Zero) return null;
    try {
      var buffer=new System.Text.StringBuilder(32768); uint size=(uint)buffer.Capacity;
      return QueryFullProcessImageNameW(h,0,buffer,ref size) ? buffer.ToString(0,(int)size) : null;
    } finally { CloseHandle(h); }
  }
  // Same refusals as filesystem.checked_path; null means the image path is not trustworthy.
  // Pathlib collapses '.' and empty components of an image path, so only those are skipped.
  public static string CheckedImage(string p) {
    try {
      if(p.StartsWith("\\\\") || p.StartsWith("//") || (p.Length>2 && p.Substring(2).IndexOf(':')>=0)) return null;
      string[] parts=p.Replace('/','\\').Split('\\');
      for(int i=1;i<parts.Length;i++) {
        if(parts[i]=="..") return null;
        if(parts[i].Length>0 && parts[i]!="." && RecipientPath.Ambiguous(parts[i])) return null;
      }
      string full=Path.GetFullPath(p);
      for(string walk=full;!string.IsNullOrEmpty(walk);walk=Path.GetDirectoryName(walk)) {
        if((File.Exists(walk) || Directory.Exists(walk)) && (File.GetAttributes(walk)&FileAttributes.ReparsePoint)!=0) return null;
      }
      return full.Length==Path.GetPathRoot(full).Length ? full : full.TrimEnd('\\');
    } catch(Exception) { return null; }
  }
  // Executable names under the game root. Null means unknown: more than Limit entries, a
  // link/reparse entry, a reserved or ambiguous name or an unreadable directory.
  public static string[] ExecutableNames(string root,int limit) {
    var names=new List<string>(); var pending=new Stack<DirectoryInfo>(); int count=0;
    pending.Push(new DirectoryInfo(root));
    try {
      while(pending.Count>0) {
        foreach(var entry in pending.Pop().EnumerateFileSystemInfos()) {
          if(RecipientPath.Ambiguous(entry.Name) || entry.Name.IndexOf(':')>=0 || (entry.Attributes&FileAttributes.ReparsePoint)!=0) return null;
          if(++count>limit) return null;
          if((entry.Attributes&FileAttributes.Directory)!=0) pending.Push((DirectoryInfo)entry);
          else if(entry.Name.Length>4 && entry.Name.EndsWith(".exe",StringComparison.OrdinalIgnoreCase)) names.Add(entry.Name);
        }
      }
    } catch(IOException) { return null; }
    catch(UnauthorizedAccessException) { return null; }
    catch(System.Security.SecurityException) { return null; }
    return names.ToArray();
  }
}
'@

$script:directoryGuards = @{}
$script:journalStream = $null
$script:executableNames = @{}
$script:gameClosedAt = @{}

function Checked([string]$Path) {
    # Refuse before GetFullPath, which silently drops '..', trailing dots, spaces, NEL and NBSP.
    $refusal = [RecipientPath]::Refusal($Path)
    if ($null -ne $refusal) { throw $refusal }
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
        if ($part -ceq '.' -or $part -ceq '..' -or [RecipientPath]::Ambiguous($part)) { throw 'Invalid path component.' }
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
        $null = [RecipientIdentity]::ReadHandle($stream.SafeFileHandle)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}
# Pure classifier with the semantics of game_process.classify_game_processes. $Names are the
# executable file names under $Root ($null = unknown); $Snapshot rows carry name and image.
function GameProcessStatus([string]$Root,$Names,$Snapshot) {
    if ($null -eq $Names) { return 'unknown' }
    $known = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in @($Names)) { [void]$known.Add([string]$name) }
    if ($known.Count -eq 0) { return 'unknown' }
    $prefix = $Root.TrimEnd('\')+'\'
    $running = $false; $ambiguous = $false
    foreach ($process in @($Snapshot)) {
        $named = $known.Contains([string]$process.name)
        $image = $process.image
        if ($null -eq $image -or [string]$image -cnotmatch '^(?:[A-Za-z]:[\\/]|[\\/]{2})') {
            if ($named) { $ambiguous = $true }
            continue
        }
        $raw = ([string]$image).Replace('/','\')
        # A same-named EXE elsewhere is another installation, not the selected game.
        if (-not $named -and -not $raw.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { continue }
        $full = [RecipientProcess]::CheckedImage($raw)
        if ($null -eq $full) { if ($named -or $raw.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { $ambiguous = $true }; continue }
        if ($full.Equals($Root.TrimEnd('\'),[StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { $running = $true }
    }
    if ($running) { return 'running' }
    if ($ambiguous) { return 'unknown' }
    return 'closed'
}
function GameProcessSnapshot {
    foreach ($process in @(Get-Process)) {
        $image = [RecipientProcess]::Image($process.Id)
        $name = if ($image) { [IO.Path]::GetFileName($image) } else { $process.ProcessName+'.exe' }
        [pscustomobject]@{name=$name;image=$image}
    }
}
# A typed confirmation can wait indefinitely, so the next check after it is always fresh.
function ForgetGameCheck { $script:gameClosedAt.Clear() }
# $KnownNames adds package-recorded executable names (for example a copied game EXE that a
# previous partial removal already deleted); it never replaces the folder walk.
function GameClosed([string]$Root,[string[]]$KnownNames=@()) {
    $full = Checked $Root
    # Executable names are collected once per root and run; images under the root always count.
    if (-not $script:executableNames.ContainsKey($full)) { $script:executableNames[$full] = [RecipientProcess]::ExecutableNames($full,100000) }
    $names = $script:executableNames[$full]
    if ($null -ne $names) { $names = @($names)+@($KnownNames | Where-Object { $_ }) }
    if ($null -ne $names -and @($names).Count -eq 0) { throw 'No game executable was found in the selected folder; select the game folder. Nothing was changed.' }
    if ($null -eq $names) { throw 'Game folder cannot be inspected for running programs (links, reserved names, unreadable folders or too many entries); nothing was changed.' }
    # Per-file loops reuse a 'closed' observation for at most one second from its snapshot
    # start; the first call per root, 'running' and 'unknown' always take a fresh snapshot.
    $observed = $script:gameClosedAt[$full]
    if ($null -ne $observed -and $observed.ElapsedMilliseconds -lt 1000) { return }
    $script:gameClosedAt.Remove($full)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    try { $snapshot = @(GameProcessSnapshot) } catch { throw 'Game process identity unavailable; close the game.' }
    $status = GameProcessStatus $full $names $snapshot
    if ($status -ceq 'running') { throw 'Close the game before changing translation files.' }
    if ($status -cne 'closed') { throw 'Game process identity unavailable; close the game.' }
    $script:gameClosedAt[$full] = $clock
}
function NeedDirectory([string]$Path) {
    $full = Checked $Path
    if ($script:directoryGuards.ContainsKey($full)) { return }
    $parent = [IO.Path]::GetDirectoryName($full)
    if (-not (Test-Path -LiteralPath $full)) {
        if ($parent -and $full -ne $target) { NeedDirectory $parent }
        [void][IO.Directory]::CreateDirectory($full)
    }
    $script:directoryGuards[$full] = [RecipientIdentity]::HoldDirectory((Checked $full))
}
function WriteNew([string]$Relative,[byte[]]$Bytes) {
    $path = Confined $target $Relative
    NeedDirectory ([IO.Path]::GetDirectoryName($path))
    $path = Confined $target $Relative
    $output = [IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $identity = [RecipientIdentity]::ReadHandle($output.SafeFileHandle)
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
        $null = [RecipientIdentity]::ReadHandle($inputFile.SafeFileHandle)
        if ($inputFile.Length -ne $Entry.bytes) { throw 'Source file size changed.' }
        $output = [IO.File]::Open((Confined $target $Entry.path),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $identity = [RecipientIdentity]::ReadHandle($output.SafeFileHandle)
            Journal @{path=$Entry.path;sha256=$Entry.sha256;identity=$identity}
            $inputFile.CopyTo($output); $output.Flush($true)
            [RecipientIdentity]::CopyWriteTime($inputFile.SafeFileHandle,$output.SafeFileHandle)
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
# End of shared recipient core.
