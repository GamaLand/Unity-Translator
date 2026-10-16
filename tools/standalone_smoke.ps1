param(
    [string]$PackageRoot = $PSScriptRoot,
    [string]$OutputRoot = $env:TEMP
)
$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackageRoot).Path
$executable = Join-Path $package 'UnityTranslator.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Standalone executable missing' }
$output = [IO.Path]::GetFullPath($OutputRoot)
$run = Join-Path $output ('UnityTranslatorSmoke-' + [Guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $run) { throw 'Smoke output must be new' }
$pythonAvailable = [bool](Get-Command python, py -ErrorAction SilentlyContinue)
$compilerAvailable = [bool](Get-Command cl, csc, dotnet -ErrorAction SilentlyContinue)
New-Item -ItemType Directory -Path $run | Out-Null
$game = Join-Path $run 'synthetic-game'
New-Item -ItemType Directory -Path $game | Out-Null
$project = Join-Path $run 'synthetic-project'
$env:PYTHONHOME = ''
$env:PYTHONPATH = ''
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
$env:QT_QPA_PLATFORM = 'offscreen'
$env:UNITYTRANSLATOR_UI_LANGUAGE = 'tr'
$env:TEMP = $run
$env:TMP = $run
& $executable --verify-ui $game $project | Out-File -LiteralPath (Join-Path $run 'stdout.txt') -Encoding utf8
$exitCode = $LASTEXITCODE
$reportPath = Join-Path $project 'reports\ui-verification.json'
$passed = $false
if (Test-Path -LiteralPath $reportPath) {
    $report = Get-Content -LiteralPath $reportPath -Encoding utf8 -Raw | ConvertFrom-Json
    $passed = $exitCode -eq 0 -and $report.passed -and $report.rows_in_model -eq 200 -and $report.source_records -eq 601 -and $report.plural_editor_verified -and $report.plural_prompt_present -and $report.editor_unicode_preserved -and $report.draft_autosave_verified -and $report.game_process_verified -and $report.windows_process_api_verified -and $report.runtime_export_verified -and $report.installation_verified -and $report.batch_approval_verified -and $report.worker_invalid_stdin_verified
}
$summary = @{
    passed = [bool]$passed
    exit_code = $exitCode
    external_python_available_before_test = $pythonAvailable
    external_compiler_available_before_test = $compilerAvailable
    clean_machine_claim = $false
    executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    os_version = [Environment]::OSVersion.VersionString
    test = 'synthetic Qt paging, manual edit, approval, modal plural editor, prompt resource, draft close/reopen, game status, Windows own-PID API, screenshot; isolated PATH'
}
$summary | ConvertTo-Json | Out-File -LiteralPath (Join-Path $run 'smoke-summary.json') -Encoding utf8
Write-Output $run
if (-not $passed) { exit 1 }
exit 0
