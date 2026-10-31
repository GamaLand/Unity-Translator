# Fixed additive recipient implementation. Called only by the bundled shared installer.
# Never overwrites original files or claims runtime-generated sidecars as owned.
if ($package.package_id -isnot [string] -or $package.package_id -cnotmatch '^[a-f0-9]{32}$' -or $package.metadata_folder -cne ('.unitytranslator/renpy-additive/'+$package.package_id) -or $package.launcher -cne 'Play-Translated.cmd' -or $package.language -isnot [string] -or $package.language -cnotmatch '^[A-Za-z_][A-Za-z_0-9]{0,127}$' -or $package.language -cin @('None','python','style','default','strings') -or $package.native_format_version -notin @(1,2)) { throw 'Invalid additive manifest.' }
if ($OutputParent) { throw 'This patch installs additions into the game folder; no output parent is used.' }
if ($package.game_executable -isnot [string] -or $package.game_executable -match '[\\/]' -or [IO.Path]::GetExtension($package.game_executable) -ine '.exe') { throw 'Invalid game executable.' }
if (@($package.copy_files).Count -lt 1 -or @($package.copy_files).Count -gt 20000 -or @($package.payloads).Count -lt 1 -or @($package.payloads).Count -gt 512) { throw 'Invalid build or payload count.' }
$buildPaths = @{}; $payloadPaths = @{}; $total = [long]0; $buildBytes = [long]0
foreach ($entry in @($package.copy_files)+@($package.payloads)) {
    if ($entry.path -isnot [string] -or $entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or ($entry.bytes -isnot [int] -and $entry.bytes -isnot [long]) -or $entry.bytes -lt 0 -or $buildPaths.ContainsKey($entry.path.ToLowerInvariant())) { throw 'Invalid or duplicate file evidence.' }
    $null = Confined $packageRoot $entry.path
    if ($entry.path -imatch '(^|/)(\.git|\.hg|\.svn|\.agents|\.codex|\.claude|\.cursor|\.ssh|\.aws|\.gnupg|\.aider[^/]*|\.env(?:\.[^/]*)?)(/|$)' -or $entry.path -imatch '^\.unitytranslator/' -or $entry.path -ieq $package.launcher) { throw 'Private or conflicting build evidence.' }
    $buildPaths[$entry.path.ToLowerInvariant()] = $entry
    $buildBytes += $entry.bytes
    if ($buildBytes -gt 34426847232) { throw 'Build evidence size limit exceeded.' }
}
if (-not $buildPaths.ContainsKey($package.game_executable.ToLowerInvariant()) -or -not $buildPaths.ContainsKey('renpy/vc_version.py')) { throw 'Required executable/version evidence missing.' }
foreach ($entry in $package.payloads) {
    if ($entry.path -cnotmatch ('^game/tl/'+[regex]::Escape($package.language)+'/ut_[a-f0-9]{64}(?:_[0-9]{4})?\.rpy$') -or $entry.bytes -gt 2097152) { throw 'Invalid native payload path or size.' }
    $payloadPaths[$entry.path.ToLowerInvariant()] = $entry
    $total += $entry.bytes
}
if ($total -gt 67108864 -or $package.launcher_sha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid payload budget or launcher evidence.' }
$languageRelative = 'game/tl/'+$package.language

function AddonInputs([string]$Root) {
    CheckBuild $Root
    # Verify membership as well as hashes: an added script/archive must not override the patch.
    $pending = [Collections.Generic.Stack[object]]::new()
    $pending.Push(@{path=(Confined $Root 'game');depth=0})
    $count = 0; $found = @{}
    while ($pending.Count) {
        $directory = $pending.Pop()
        foreach ($child in @(Get-ChildItem -LiteralPath (Checked $directory.path) -Force)) {
            if (++$count -gt 20000) { throw 'Game input membership limit exceeded.' }
            $full = Checked $child.FullName
            $relative = $full.Substring($Root.TrimEnd('\').Length+1).Replace('\','/')
            if ($relative -imatch '^game/(saves|cache)(/|$)' -or $relative -imatch '(^|/)__pycache__(/|$)') { continue }
            if ($child.PSIsContainer) {
                if ($directory.depth -ge 32) { throw 'Game input depth limit exceeded.' }
                $pending.Push(@{path=$full;depth=($directory.depth+1)}); continue
            }
            if (-not $payloadPaths.ContainsKey($relative.ToLowerInvariant()) -and -not ($relative.EndsWith('.rpyc',[StringComparison]::OrdinalIgnoreCase) -and $payloadPaths.ContainsKey($relative.Substring(0,$relative.Length-1).ToLowerInvariant())) -and $relative -imatch '(\.rpyc?|\.rpymc?|\.rpa|_ren\.py)$') {
                if (-not $buildPaths.ContainsKey($relative.ToLowerInvariant())) { throw ('Unreviewed game input: '+$relative) }
                $found[$relative.ToLowerInvariant()] = $true
            }
        }
    }
    foreach ($entry in $package.copy_files) {
        if ($entry.path -imatch '^game/.*(\.rpyc?|\.rpymc?|\.rpa|_ren\.py)$' -and -not $found.ContainsKey($entry.path.ToLowerInvariant())) { throw 'Game input membership changed.' }
    }
}
function AddonPayloads([string]$Root,[bool]$Staged) {
    $script:nativeBlocks.Clear(); $script:nativeKeys.Clear()
    foreach ($entry in $package.payloads) {
        $name = if ($Staged) { 'payload/'+$entry.path } else { $entry.path }
        $path = Confined $Root $name
        if ((Get-Item -LiteralPath $path).Length -ne $entry.bytes -or (Digest $path) -cne $entry.sha256) { throw 'Translation payload integrity mismatch.' }
        CheckNative $path
    }
}
function AddonReceipt([string]$Root,[bool]$Launching) {
    $path = Confined $Root ($package.metadata_folder+'/receipt.json')
    if ((Get-Item -LiteralPath $path).Length -gt 16777216) { throw 'Oversized installation receipt.' }
    $result = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($result.status -cne 'installed' -or $result.target -cne $Root -or $result.package_id -cne $package.package_id -or $result.manifest_sha256 -cne $manifestHash -or $result.game_identity -cne [RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$Root])) { throw 'Installation game identity mismatch.' }
    $metadataPath = Confined $Root $package.metadata_folder
    NeedDirectory $metadataPath
    if ([RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$metadataPath]) -cne $result.metadata_identity) { throw 'Installation metadata directory changed.' }
    $languagePath = Confined $Root $languageRelative
    if (Test-Path -LiteralPath $languagePath) {
        NeedDirectory $languagePath
        if ([RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$languagePath]) -cne $result.language_identity) { throw 'Translation directory changed.' }
    } elseif ($Launching) { throw 'Installed translation directory is missing.' }
    $allowed = @{}
    foreach ($entry in $package.payloads) { $allowed[$entry.path.ToLowerInvariant()] = $entry.sha256 }
    $allowed[$package.launcher.ToLowerInvariant()] = $package.launcher_sha256
    $allowed[($package.metadata_folder+'/package.json').ToLowerInvariant()] = $manifestHash
    $allowed[($package.metadata_folder+'/renpy-copy.ps1').ToLowerInvariant()] = $package.installer_sha256
    $allowed[($package.metadata_folder+'/renpy-additive.ps1').ToLowerInvariant()] = $package.addon_sha256
    $allowed[($package.metadata_folder+'/reviewed-plan.json').ToLowerInvariant()] = $result.reviewed_plan_file_sha256
    $allowed[($package.metadata_folder+'/install-start.json').ToLowerInvariant()] = $result.installation_start_sha256
    $seen = @{}
    foreach ($entry in $result.files) {
        $key = $entry.path.ToLowerInvariant()
        if ($seen.ContainsKey($key) -or -not $allowed.ContainsKey($key) -or $allowed[$key] -cne $entry.sha256 -or $entry.identity -cnotmatch '^[A-F0-9]{8}:[A-F0-9]{16}$') { throw 'Receipt claims an unowned file.' }
        $null = Confined $Root $entry.path; $seen[$key] = $true
    }
    if ($seen.Count -ne $allowed.Count) { throw 'Incomplete ownership receipt.' }
    foreach ($name in @('reviewed-plan.json','install-start.json')) {
        $entry = @($result.files | Where-Object { $_.path -ceq ($package.metadata_folder+'/'+$name) })[0]
        $proof = Confined $Root $entry.path
        if ([RenpyCopyIdentity]::Read($proof) -cne $entry.identity -or (Digest $proof) -cne $entry.sha256) { throw 'Immutable installation proof changed.' }
    }
    return $result
}
function AddonBlockers([string]$Root) {
    $result = @()
    foreach ($entry in $package.payloads) {
        $path = Confined $Root ($entry.path+'c')
        if (Test-Path -LiteralPath $path) { $result += ($entry.path+'c') }
    }
    return $result
}
function AddonConfirm($Plan,[string]$Hash,[string]$Word) {
    if ($ReviewedPlanSha256) {
        if ($ReviewedPlanSha256 -cne $Hash) { throw 'Reviewed plan changed; review again.' }
    } else {
        Write-Output ($Plan | ConvertTo-Json -Depth 12)
        if ((Read-Host ('Review the file plan above. Type '+$Word)) -cne $Word) { throw 'Operation not approved; nothing written.' }
    }
}

try {
    if ($Action -eq 'Launch') {
        $target = Checked ([IO.Path]::Combine($packageRoot,'../../..'))
        if ((Confined $target $package.metadata_folder) -cne $packageRoot) { throw 'Launch from the installed patch only.' }
        NeedDirectory $target
        $receipt = AddonReceipt $target $true
        AddonInputs $target; AddonPayloads $target $false
        if ($ReviewOnly) {
            Write-Output (@{action='Launch';executable=(Confined $target $package.game_executable);language=$package.language;save_policy='game-default';game_started=$false} | ConvertTo-Json)
            exit 0
        }
        # User explicitly invoked Play-Translated.cmd. Preserve normal progress and game behavior.
        $previous = [Environment]::GetEnvironmentVariable('RENPY_LANGUAGE','Process')
        try {
            [Environment]::SetEnvironmentVariable('RENPY_LANGUAGE',$package.language,'Process')
            Start-Process -FilePath (Confined $target $package.game_executable) -WorkingDirectory $target | Out-Null
        } finally { [Environment]::SetEnvironmentVariable('RENPY_LANGUAGE',$previous,'Process') }
        exit 0
    }
    if ($Action -eq 'Remove') {
        if (-not $InstallFolder) { $InstallFolder = $GameFolder }
        if (-not $InstallFolder) { $InstallFolder = SelectFolder 'Select the game folder containing this language patch' }
        $target = Checked $InstallFolder
        if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw 'Existing installed game folder required.' }
        GameClosed $target; NeedDirectory $target
        $receipt = AddonReceipt $target $false
        $blockers = @(AddonBlockers $target)
        $removable = @($receipt.files | Where-Object { -not $_.path.StartsWith($package.metadata_folder+'/',[StringComparison]::OrdinalIgnoreCase) })
        $removalRelative = $package.metadata_folder+'/removal-'+[Guid]::NewGuid().ToString('N')+'.json'
        # A stable reviewed name permits preview then application without overwriting audit history.
        for ($index=1; $index -le 1000; $index++) {
            $candidate = $package.metadata_folder+('/removal-{0:d4}.json' -f $index)
            if (-not (Test-Path -LiteralPath (Confined $target $candidate))) { $removalRelative=$candidate; break }
        }
        $plan = [ordered]@{format_version=3;action='Remove';target=$target;manifest_sha256=$manifestHash;game_identity=$receipt.game_identity;files=$removable;unowned_compiled_sidecars=$blockers;can_remove=($blockers.Count -eq 0);retained_metadata=$package.metadata_folder;removal_receipt=$removalRelative}
        $binding = ($plan | ConvertTo-Json -Depth 12 -Compress)+"`n"+(Digest (Confined $target ($package.metadata_folder+'/receipt.json')))
        $planHash = BytesDigest ([Text.Encoding]::UTF8.GetBytes($binding))
        if ($ReviewOnly) { Write-Output (@{plan=$plan;sha256=$planHash} | ConvertTo-Json -Depth 15); exit 0 }
        if ($blockers.Count) { throw 'Unowned compiled translation .rpyc sidecars exist. Review/remove only those sidecars manually, then retry. No patch file was removed.' }
        AddonConfirm $plan $planHash 'REMOVE'
        GameClosed $target
        if (@(AddonBlockers $target).Count) { throw 'Compiled sidecars appeared after review; nothing removed.' }
        $preserved = @()
        foreach ($entry in $removable) {
            GameClosed $target
            $path = Confined $target $entry.path
            if (-not (Test-Path -LiteralPath $path)) { continue }
            try {
                NeedDirectory ([IO.Path]::GetDirectoryName($path))
                if (-not [RenpyCopyIdentity]::DeleteUnchanged($path,$entry.identity,$entry.sha256)) { $preserved += $entry.path }
            } catch { $preserved += $entry.path }
        }
        $languagePath = Confined $target $languageRelative
        if ((Test-Path -LiteralPath $languagePath) -and $preserved.Count -eq 0) {
            $script:directoryGuards[$languagePath].Dispose(); $script:directoryGuards.Remove($languagePath)
            $null = [RenpyCopyIdentity]::DeleteEmptyDirectory($languagePath,$receipt.language_identity)
        }
        $report = @{status=$(if ($preserved.Count) { 'partial_removal_modified_files_preserved' } else { 'owned_additions_removed_audit_metadata_retained' });target=$target;changed_files_preserved=$preserved;language_directory_retained=(Test-Path -LiteralPath $languagePath);original_files_overwritten=$false;runtime_data_restored=$false;reviewed_plan_sha256=$planHash;removal_receipt=$removalRelative}
        $null = WriteNew $removalRelative ([Text.UTF8Encoding]::new($false).GetBytes(($report | ConvertTo-Json -Depth 6)))
        Write-Output ($report | ConvertTo-Json -Depth 6)
        if ($preserved.Count) { exit 2 }
        exit 0
    }
    if (-not $GameFolder) { $GameFolder = SelectFolder 'Select the ORIGINAL game folder for the language patch (no game copy)' }
    $target = Checked $GameFolder
    if (-not (Test-Path -LiteralPath $target -PathType Container) -or (Overlaps $target $packageRoot)) { throw 'Select the original game and extract the package outside it.' }
    AddonInputs $target; AddonPayloads $packageRoot $true
    $metadataPath = Confined $target $package.metadata_folder
    $languagePath = Confined $target $languageRelative
    if ((Test-Path -LiteralPath $metadataPath) -or (Test-Path -LiteralPath $languagePath)) { throw 'Patch metadata or language namespace exists; nothing overwritten.' }
    $newFiles = @($package.payloads)+@(
        @{path=$package.launcher;sha256=$package.launcher_sha256;bytes=(Get-Item -LiteralPath (Confined $packageRoot $package.launcher)).Length},
        @{path=($package.metadata_folder+'/package.json');sha256=$manifestHash;bytes=$manifestBytes.Length},
        @{path=($package.metadata_folder+'/renpy-copy.ps1');sha256=$package.installer_sha256;bytes=(Get-Item -LiteralPath (Confined $packageRoot 'renpy-copy.ps1')).Length},
        @{path=($package.metadata_folder+'/renpy-additive.ps1');sha256=$package.addon_sha256;bytes=(Get-Item -LiteralPath (Confined $packageRoot 'renpy-additive.ps1')).Length}
    )
    foreach ($entry in $newFiles) {
        if (Test-Path -LiteralPath (Confined $target $entry.path)) { throw 'A patch destination exists; nothing overwritten.' }
    }
    if ((Digest (Confined $packageRoot $package.launcher)) -cne $package.launcher_sha256) { throw 'Launcher hash mismatch.' }
    $gameGuard = [RenpyCopyIdentity]::HoldDirectory($target)
    $gameIdentity = [RenpyCopyIdentity]::ReadHandle($gameGuard); $gameGuard.Dispose()
    $generated = @('install-start.json','reviewed-plan.json','install-journal.jsonl','receipt.json') | ForEach-Object { $package.metadata_folder+'/'+$_ }
    $plan = [ordered]@{format_version=3;action='Install';installation_mode='original-additions';target=$target;game_identity=$gameIdentity;manifest_sha256=$manifestHash;files=$newFiles;generated_files=@($generated);game_files_copied=0;original_files_overwritten=$false;backup_policy='No original file is overwritten; no original-file backup is needed.';runtime_policy=$package.runtime_write_scope;retained_metadata=$package.metadata_folder}
    $planRaw = [Text.UTF8Encoding]::new($false).GetBytes(($plan | ConvertTo-Json -Depth 12 -Compress))
    $planHash = BytesDigest $planRaw
    if ($ReviewOnly) { Write-Output (@{plan=$plan;sha256=$planHash} | ConvertTo-Json -Depth 15); exit 0 }
    AddonConfirm $plan $planHash 'INSTALL'
    NeedDirectory $target
    if ([RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$target]) -cne $gameIdentity) { throw 'Game directory changed after review.' }
    AddonInputs $target
    if ((Test-Path -LiteralPath $metadataPath) -or (Test-Path -LiteralPath $languagePath)) { throw 'A destination appeared after review.' }
    NeedDirectory ([IO.Path]::GetDirectoryName($metadataPath)); [RenpyCopyIdentity]::NewDirectory($metadataPath); NeedDirectory $metadataPath
    NeedDirectory ([IO.Path]::GetDirectoryName($languagePath)); [RenpyCopyIdentity]::NewDirectory($languagePath); NeedDirectory $languagePath
    $journalPath = Confined $target ($package.metadata_folder+'/install-journal.jsonl')
    $script:journalStream = [IO.File]::Open($journalPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $receipt = @{format_version=3;status='installing';target=$target;game_identity=$gameIdentity;package_id=$package.package_id;manifest_sha256=$manifestHash;reviewed_plan_sha256=$planHash;reviewed_plan_file_sha256=(BytesDigest $planRaw);language_identity=([RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$languagePath]));metadata_identity=([RenpyCopyIdentity]::ReadHandle($script:directoryGuards[$metadataPath]));files=@()}
    $start = [Text.UTF8Encoding]::new($false).GetBytes((@{target=$target;game_identity=$gameIdentity;package_id=$package.package_id;manifest_sha256=$manifestHash;reviewed_plan_sha256=$planHash} | ConvertTo-Json -Compress))
    $receipt.installation_start_sha256 = BytesDigest $start
    $receipt.files += WriteNew ($package.metadata_folder+'/install-start.json') $start
    $receipt.files += WriteNew ($package.metadata_folder+'/reviewed-plan.json') $planRaw
    foreach ($entry in $newFiles) {
        GameClosed $target
        $source = if ($payloadPaths.ContainsKey($entry.path.ToLowerInvariant())) { Confined $packageRoot ('payload/'+$entry.path) } elseif ($entry.path -ceq $package.launcher) { Confined $packageRoot $package.launcher } else { Confined $packageRoot ([IO.Path]::GetFileName($entry.path)) }
        if ((Get-Item -LiteralPath $source).Length -ne $entry.bytes) { throw 'Package size changed after review.' }
        $raw = [IO.File]::ReadAllBytes($source)
        if ($raw.Length -ne $entry.bytes -or (BytesDigest $raw) -cne $entry.sha256) { throw 'Package changed after review; incomplete additions retained.' }
        $receipt.files += WriteNew $entry.path $raw
    }
    AddonInputs $target; AddonPayloads $target $false
    $receipt.status = 'installed'
    $null = WriteNew ($package.metadata_folder+'/receipt.json') ([Text.UTF8Encoding]::new($false).GetBytes(($receipt | ConvertTo-Json -Depth 12)))
    Write-Output (@{status='installed';target=$target;installation_mode='original-additions';game_files_copied=0;original_files_overwritten=$false;game_started=$false;receipt=($package.metadata_folder+'/receipt.json')} | ConvertTo-Json)
    exit 0
} finally {
    if ($null -ne $script:journalStream) { $script:journalStream.Dispose() }
    foreach ($handle in $script:directoryGuards.Values) { $handle.Dispose() }
}
