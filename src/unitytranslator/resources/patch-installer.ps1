param(
    [ValidateSet('Install','Remove')][string]$Action = 'Install',
    [string]$GameFolder = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Windows built-in PowerShell/.NET only; never starts the game or downloads code.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class PatchFileIdentity {
  [StructLayout(LayoutKind.Sequential)] struct Info {
    public uint Attributes; public System.Runtime.InteropServices.ComTypes.FILETIME Creation;
    public System.Runtime.InteropServices.ComTypes.FILETIME Access, Write;
    public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern SafeFileHandle CreateFile(string p,uint a,uint s,IntPtr sec,uint c,uint f,IntPtr t);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out Info i);
  public static string Read(string p) {
    using(var h=CreateFile(p,0,7,IntPtr.Zero,3,0x00200000,IntPtr.Zero)) {
      return ReadHandle(h);
    }
  }
  public static string ReadHandle(SafeFileHandle h) {
    Info i; if(h.IsInvalid || !GetFileInformationByHandle(h,out i) || i.Links!=1 || (i.Attributes&0x400)!=0)
      throw new IOException("File identity/link check failed");
    return i.Volume.ToString("X8")+":"+i.IndexHigh.ToString("X8")+i.IndexLow.ToString("X8");
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
    return $full
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
function Digest([string]$Path) {
    # .NET hashing also works when PowerShell module auto-loading is unavailable.
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
function GameClosed {
    $name = [IO.Path]::GetFileNameWithoutExtension($package.game_executable)
    foreach ($process in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        try { $image = $process.Path } catch { throw 'Game process identity unavailable; close the game.' }
        if (-not $image -or [string]::Equals([IO.Path]::GetFullPath($image),(Confined $game $package.game_executable),[StringComparison]::OrdinalIgnoreCase)) { throw 'Close the game before install/remove.' }
    }
}
function CheckGame {
    GameClosed
    foreach ($property in $package.game_files.PSObject.Properties) {
        $path = Confined $game $property.Name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Digest $path) -ne $property.Value) { throw ('Game version mismatch: '+$property.Name) }
    }
}
function SaveReceipt {
    $temp = Confined $game ($package.patch_folder+'/.receipt-'+[Guid]::NewGuid().ToString('N')+'.tmp')
    [IO.File]::WriteAllText($temp,($receipt | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $receiptPath) {
        if ([PatchFileIdentity]::Read($receiptPath) -ne $script:receiptIdentity) { throw 'Receipt identity changed.' }
        $backup = Confined $game ($package.patch_folder+'/.receipt-'+[Guid]::NewGuid().ToString('N')+'.bak')
        if (Test-Path -LiteralPath $backup) { throw 'Receipt backup collision.' }
        [IO.File]::Replace($temp,$receiptPath,$backup)
        if ([PatchFileIdentity]::Read($backup) -eq $script:receiptIdentity) { [IO.File]::Delete($backup) }
    } else { [IO.File]::Move($temp,$receiptPath) }
    $script:receiptIdentity = [PatchFileIdentity]::Read($receiptPath)
}
function RemoveOwned {
    GameClosed
    $preserved = [Collections.Generic.List[string]]::new()
    foreach ($item in @($receipt.files | Sort-Object path -Descending)) {
        if (-not $allowed.ContainsKey($item.path.ToLowerInvariant())) { throw 'Unowned receipt target.' }
        $path = Confined $game $item.path
        if (-not (Test-Path -LiteralPath $path)) { continue }
        GameClosed
        try { $identity = [PatchFileIdentity]::Read($path) } catch { $preserved.Add($item.path); continue }
        if ($identity -ne $item.identity -or (Digest $path) -ne $item.sha256) { $preserved.Add($item.path); continue }
        [IO.File]::Delete($path)
    }
    $receipt.status = if ($preserved.Count) { 'recovery_required' } else { 'removed' }
    SaveReceipt
    if ($preserved.Count) { throw ('Changed files preserved: '+($preserved -join ', ')) }
    # Delete only empty package-owned directories, never recurse or remove foreign files.
    $directories = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $package.files) {
        $parent = [IO.Path]::GetDirectoryName((Confined $game $entry.path))
        while ($parent.StartsWith($patchRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {
            [void]$directories.Add($parent); $parent = [IO.Path]::GetDirectoryName($parent)
        }
    }
    if ([PatchFileIdentity]::Read($receiptPath) -eq $script:receiptIdentity) { [IO.File]::Delete($receiptPath) }
    foreach ($directory in @($directories | Sort-Object Length -Descending)) {
        try { [IO.Directory]::Delete((Checked $directory),$false) } catch { }
    }
    try { [IO.Directory]::Delete((Checked $patchRoot),$false) } catch { }
}

$packageRoot = Checked $PSScriptRoot
$manifestPath = Confined $packageRoot 'package.json'
if ((Get-Item -LiteralPath $manifestPath).Length -gt 4194304) { throw 'Manifest too large.' }
$package = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($package.format_version -ne 1 -or $package.purpose -ne 'unitytranslator-shareable-patch' -or $package.patch_folder -ne 'UnityTranslatorPatch' -or $package.package_id -notmatch '^[a-f0-9]{32}$' -or @($package.files).Count -gt 2000 -or @($package.files).Count -lt 1) { throw 'Invalid patch manifest.' }
if (-not $GameFolder) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = [Windows.Forms.FolderBrowserDialog]::new()
    $dialog.Description = 'Oyunun EXE dosyasinin bulundugu klasoru secin'
    if ($dialog.ShowDialog() -ne 'OK') { exit 0 }
    $GameFolder = $dialog.SelectedPath
}
$game = Checked $GameFolder
if (-not (Test-Path -LiteralPath $game -PathType Container)) { throw 'Game folder missing.' }
$patchRoot = Confined $game $package.patch_folder
$receiptPath = Confined $game ($package.patch_folder+'/install-receipt.json')
$allowed = @{}
$total = [long]0
foreach ($entry in $package.files) {
    $key = $entry.path.ToLowerInvariant()
    if ($allowed.ContainsKey($key) -or $entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $entry.bytes -lt 0 -or $entry.bytes -gt 67108864) { throw 'Invalid file manifest.' }
    if ($entry.path -ne 'winhttp.dll' -and -not $entry.path.StartsWith('UnityTranslatorPatch/',[StringComparison]::Ordinal)) { throw 'Patch target outside owned subtree.' }
    if ($entry.path -eq 'UnityTranslatorPatch/install-receipt.json') { throw 'Receipt cannot be payload.' }
    $null = Confined $game $entry.path
    $allowed[$key] = $entry
    $total += $entry.bytes
}
if ($total -gt 268435456 -or -not $allowed.ContainsKey('winhttp.dll') -or -not $allowed.ContainsKey('unitytranslatorpatch/portable-runtime-v1.marker')) { throw 'Patch size/content invalid.' }
# INI is recipient-specific and never contains a sender path.
$iniPath = Confined $game 'doorstop_config.ini'
$preloader = Confined $game 'UnityTranslatorPatch/BepInEx/core/BepInEx.Preloader.dll'
$ini = "; UnityTranslator portable experimental runtime`r`n[General]`r`nenabled=true`r`ntarget_assembly=`"$preloader`"`r`nredirect_output_log=false`r`nboot_config_override=`r`nignore_disable_switch=false`r`n[UnityMono]`r`ndll_search_path_override=`r`ndebug_enabled=false`r`ndebug_address=127.0.0.1:10000`r`ndebug_suspend=false`r`n"
if ($preloader.IndexOfAny([char[]]"`r`n`0`"") -ge 0) { throw 'Invalid INI path.' }
$iniBytes = [byte[]]([Text.Encoding]::Unicode.GetPreamble()+[Text.Encoding]::Unicode.GetBytes($ini))
$sha = [Security.Cryptography.SHA256]::Create()
try { $iniHash = [BitConverter]::ToString($sha.ComputeHash($iniBytes)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
$allowed['doorstop_config.ini'] = @{path='doorstop_config.ini';sha256=$iniHash;bytes=$iniBytes.Length}

if ($Action -eq 'Remove') {
    GameClosed
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) { throw 'No owned installation receipt.' }
    $script:receiptIdentity = [PatchFileIdentity]::Read($receiptPath)
    if ((Get-Item -LiteralPath $receiptPath).Length -gt 4194304) { throw 'Receipt too large.' }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.package_id -ne $package.package_id -or $receipt.game -ne $game) { throw 'Receipt belongs to a different package/game path.' }
    foreach ($item in $receipt.files) {
        if (-not $allowed.ContainsKey($item.path.ToLowerInvariant()) -or $allowed[$item.path.ToLowerInvariant()].sha256 -ne $item.sha256) { throw 'Receipt file set changed.' }
    }
    RemoveOwned
    Write-Output 'Ceviri kaldirildi; mevcut oyun dosyalarina dokunulmadi.'
    exit 0
}
CheckGame
if ((Test-Path -LiteralPath $patchRoot) -or (Test-Path -LiteralPath $iniPath) -or (Test-Path -LiteralPath (Confined $game 'winhttp.dll'))) { throw 'Existing mod/patch found. Remove it with its own installer first; nothing overwritten.' }
foreach ($entry in $package.files) {
    $source = Confined ($packageRoot+'\payload') $entry.path
    if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or (Get-Item -LiteralPath $source).Length -ne $entry.bytes -or (Digest $source) -ne $entry.sha256) { throw ('Package hash mismatch: '+$entry.path) }
}
$receipt = @{format_version=1;package_id=$package.package_id;game=$game;status='installing';files=@()}
[void][IO.Directory]::CreateDirectory($patchRoot)
$script:receiptIdentity = ''
SaveReceipt
try {
    $entries = @($package.files)+@(@{path='doorstop_config.ini';sha256=$iniHash;bytes=$iniBytes.Length})
    foreach ($entry in $entries) {
        GameClosed
        $target = Confined $game $entry.path
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
        $target = Confined $game $entry.path
        $output = [IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $receipt.files += @{path=$entry.path;sha256=$entry.sha256;identity=[PatchFileIdentity]::ReadHandle($output.SafeFileHandle)}
            SaveReceipt
            if ($entry.path -eq 'doorstop_config.ini') { $output.Write($iniBytes,0,$iniBytes.Length) }
            else {
                $inputFile = [IO.File]::OpenRead((Confined ($packageRoot+'\payload') $entry.path))
                try { $inputFile.CopyTo($output) } finally { $inputFile.Dispose() }
            }
            $output.Flush($true)
        } finally { $output.Dispose() }
        if ((Digest $target) -ne $entry.sha256) { throw 'Copied file hash mismatch.' }
        SaveReceipt
    }
    CheckGame
    $receipt.status = 'installed'; SaveReceipt
    Write-Output ('Ceviri kuruldu: '+$package.records+' kayit. Oyunu normal baslaticinizdan acin.')
} catch {
    $failure = $_
    try { RemoveOwned } catch { Write-Warning 'Some additions preserved; inspect installation receipt.' }
    throw $failure
}
