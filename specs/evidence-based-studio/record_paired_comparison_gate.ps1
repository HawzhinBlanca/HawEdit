# Capture actual frozen inputs and terminal canonical output without writing .gate.
param([ValidateSet('freeze','terminal')][string]$Phase)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path '.').Path
$folder = Join-Path $root 'specs/evidence-based-studio'
$prefix = 'T8-paired'
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function SaveNew([string]$Name, $Value) {
    $path = Join-Path $folder $Name
    if (Test-Path -LiteralPath $path) { throw "Refusing overwrite: $path" }
    $Value | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $path -Encoding utf8
}
$files = @(Get-ChildItem -LiteralPath src,tests,scripts -File -Recurse | Where-Object { $_.Extension -in @('.py','.sh') })
$files += @(Get-Item -LiteralPath README.md,PROGRESS.md,DECISIONS.md,pyproject.toml,AGENTS.md)
$package = & .venv/Scripts/python.exe -c 'from hawedit.wsl_setup import package_digest; print(package_digest())'
if ($LASTEXITCODE -ne 0) { throw 'Package capture failed' }
if ($Phase -eq 'freeze') {
    $runtime = & .venv/Scripts/python.exe -c 'import json,platform,sqlite3,sys,shutil; from importlib.metadata import version; print(json.dumps(dict(python=sys.version,executable=sys.executable,sqlite=sqlite3.sqlite_version,platform=platform.platform(),packages={n:version(n) for n in ("dbos","pytest","ruff","mypy")},ffmpeg=shutil.which("ffmpeg"),ffprobe=shutil.which("ffprobe"))))'
    if ($LASTEXITCODE -ne 0) { throw 'Runtime capture failed' }
    $runtime = $runtime | ConvertFrom-Json
    $media = [ordered]@{}
    foreach ($name in @('ffmpeg','ffprobe')) {
        $path = $runtime.$name
        if ($path) { $media[$name] = @{path=$path; sha256=(Hash $path); version=(& $path -version | Select-Object -First 1)} }
    }
    SaveNew "$prefix-host.json" ([ordered]@{
        observed_at_utc=[DateTime]::UtcNow.ToString('o'); runtime=$runtime; media_executables=$media
        cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
        gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
        host=(Get-CimInstance Win32_ComputerSystem | Select-Object Name,TotalPhysicalMemory)
        operating_system=(Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version)
    })
    SaveNew "$prefix-source-manifest.json" ([ordered]@{
        observed_at_utc=[DateTime]::UtcNow.ToString('o'); head_sha=(git rev-parse HEAD)
        source_package_sha256=$package; uncommitted_source=$true; git_status=@(git status --short)
        files=@($files | ForEach-Object { @{path=$_.FullName; sha256=(Hash $_.FullName)} })
    })
    Write-Output "Frozen $($files.Count) source/test/script/document inputs; package $package"
    exit 0
}
$manifestPath = Join-Path $folder "$prefix-source-manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($package -ne $manifest.source_package_sha256) { throw 'Package drift' }
if (@(Compare-Object @($files.FullName) @($manifest.files.path)).Count) { throw 'Input membership drift' }
foreach ($file in $manifest.files) { if ((Hash $file.path) -ne $file.sha256) { throw "Input drift: $($file.path)" } }
if (@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*--junitxml=*last-test-run.xml*' }).Count) { throw 'Canonical pytest is still running' }
$exitRecord = Get-Content -LiteralPath (Join-Path $folder "$prefix-gate-exit.json") -Raw | ConvertFrom-Json
if ($exitRecord.source_package_sha256 -ne $package) { throw 'Exit identity mismatch' }
$canonical = Join-Path $root '.gate/last-test-run.xml'
if ((Get-Item -LiteralPath $canonical).LastWriteTimeUtc -le [DateTime]::Parse($manifest.observed_at_utc).ToUniversalTime()) { throw 'Stale canonical XML' }
[xml]$report = Get-Content -LiteralPath $canonical -Raw
$cases = @($report.SelectNodes('//testcase'))
if (-not $cases.Count) { throw 'Empty canonical report' }
$failures = @($cases | Where-Object { $_.SelectSingleNode('failure') })
$errors = @($cases | Where-Object { $_.SelectSingleNode('error') })
$skips = @($cases | Where-Object { $_.SelectSingleNode('skipped') })
$groups = [ordered]@{}
foreach ($name in @('comparison_contract','comparison_kit','visual_scorecard','editorial_acceptance','claims')) {
    $selected = @($cases | Where-Object { $_.classname -eq "tests.test_$name" })
    $groups[$name] = @{count=$selected.Count; all_passed_without_skips=($selected.Count -gt 0 -and -not @($selected | Where-Object { $_.SelectSingleNode('failure|error|skipped') }).Count); names=@($selected.name)}
}
$logPath = Join-Path $folder "gate-$prefix.log"
$log = Get-Content -LiteralPath $logPath -Raw
$summary = [regex]::Matches($log, '(?m)^(?:=+ )?[0-9]+ (?:passed|failed|errors?|skipped)[^\r\n]* in (?<seconds>[0-9.]+)s[^\r\n]*\r?$')
if (-not $summary.Count) { throw 'No terminal pytest summary' }
$snapshot = Join-Path $folder "$prefix-junit.xml"
if (Test-Path -LiteralPath $snapshot) { throw 'Refusing XML overwrite' }
Copy-Item -LiteralPath $canonical -Destination $snapshot
$related = [ordered]@{}
$research = @('acceptance_authority_serena.py','serena-T8-authority-research-map.json','serena-T8-authority-research.log','signed-study-adoption-research.md','editorial_split_probe.py','T8-editorial-split-counterexample.json','T8-editorial-split.log','T8-editorial-split-module.log','paired_comparison_posix_probe.py','T8-paired-posix.json','T8-paired-posix.log','T8-paired-posix-existing-env.log')
foreach ($path in $research) { $related[$path] = Hash (Join-Path $folder $path) }
foreach ($path in @('paired-comparison-plan.md','comparison_repair_serena.py','serena-T8-paired-before-map.json','serena-T8-paired-before.log','serena-T8-paired-final-map.json','serena-T8-paired-final.log','serena-T8-paired-final-v2-map.json','serena-T8-paired-final-v2.log','T8-paired-test-first.log','T8-paired-first-implementation.log','T8-paired-fast-initial.log','T8-paired-fast-second.log','T8-paired-fast-final.log','T8-paired-focused.log','T8-paired-focused-junit.xml','T8-paired-focused-final.log','T8-paired-focused-final-junit.xml','acceptance_flags_probe.py','T8-flags-admission-counterexample.json','T8-flags-admission.log',"$prefix-host.json", "$prefix-gate-exit.json", 'record_paired_comparison_gate.ps1')) {
    $related[$path] = Hash (Join-Path $folder $path)
}
SaveNew "$prefix-test-evidence.json" ([ordered]@{
    schema=1; status='unaccepted-engineering-evidence'; observed_at_utc=[DateTime]::UtcNow.ToString('o')
    head_sha=(git rev-parse HEAD); source_package_sha256=$package; uncommitted_source=$true
    gate_command='C:/Program Files/Git/bin/bash.exe scripts/verify.sh'; gate_exit_code=$exitRecord.exit_code
    gate_passed=($exitRecord.exit_code -eq 0 -and $log.Contains('VERIFY OK'))
    lint_types_format_passed=($log.Contains('All checks passed!') -and $log.Contains('Success: no issues found') -and $log.Contains('files already formatted'))
    elapsed_pytest_seconds=[double]::Parse($summary[$summary.Count-1].Groups['seconds'].Value,[Globalization.CultureInfo]::InvariantCulture)
    total_cases=$cases.Count; passed=($cases.Count-$failures.Count-$errors.Count-$skips.Count)
    failures=$failures.Count; errors=$errors.Count; skipped=$skips.Count
    failed_case_names=@(@($failures)+@($errors) | ForEach-Object { "$($_.classname).$($_.name)" })
    verified_groups=$groups; canonical_report_sha256=(Hash $canonical); report_snapshot_sha256=(Hash $snapshot)
    gate_log_sha256=(Hash $logPath); source_manifest_sha256=(Hash $manifestPath); related_sha256=$related
})
Write-Output "Terminal evidence: $($cases.Count) cases; $($failures.Count) failures; $($errors.Count) errors; $($skips.Count) skipped."
