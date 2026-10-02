# Keep generated verification evidence outside the clean candidate checkout.
param([ValidateSet('freeze','terminal')][string]$Phase, [string]$Directory)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path '.').Path
$head = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify committed candidate' }
if (@(git status --porcelain=v1 --untracked-files=all).Count) { throw 'Candidate checkout is not clean' }
$package = & .venv/Scripts/python.exe -c 'from hawedit.wsl_setup import package_digest; print(package_digest())'
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify source package' }
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function SaveNew([string]$Name, $Value) {
    $path = Join-Path $Directory $Name
    if (Test-Path -LiteralPath $path) { throw "Refusing evidence overwrite: $path" }
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding utf8
}
if ($Phase -eq 'freeze') {
    if ($Directory) { throw 'Freeze selects a fresh private installation-local directory' }
    $Directory = & .venv/Scripts/python.exe -c 'import os,sys; from pathlib import Path; from hawedit.studio_private import PrivateDirectory; parent=PrivateDirectory(Path(os.environ["LOCALAPPDATA"])/"HawEditEvidence"); print(parent.child("studio-commit-"+sys.argv[1],create=True).path)' $head
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create actual private evidence directory' }
    if (@(Get-ChildItem -LiteralPath $Directory -Force).Count) { throw 'Evidence directory is not fresh' }
    $paths = @(git ls-files)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate committed source' }
    SaveNew 'source-manifest.json' ([ordered]@{
        observed_at_utc=[DateTime]::UtcNow.ToString('o'); head_sha=$head; branch=(git branch --show-current)
        source_package_sha256=$package; source_is_committed=$true; clean_checkout=$true
        files=@($paths | ForEach-Object { @{path=$_; sha256=(Hash (Join-Path $root $_))} })
        ignored_generated_trace=@{path='specs/evidence-based-studio/T3-billing-schema-red.log'; sha256=(Hash (Join-Path $root 'specs/evidence-based-studio/T3-billing-schema-red.log'))}
    })
    Copy-Item -LiteralPath specs/evidence-based-studio/T8-authority-host.json -Destination (Join-Path $Directory 'prior-host-observation.json')
    SaveNew 'runtime.json' ((& .venv/Scripts/python.exe -c 'import json,platform,sys,sqlite3; from importlib.metadata import version; print(json.dumps(dict(python=sys.version,platform=platform.platform(),executable=sys.executable,sqlite=sqlite3.sqlite_version,packages={n:version(n) for n in ("dbos","pytest","ruff","mypy")})))') | ConvertFrom-Json)
    Write-Output $Directory
    exit 0
}
if (-not $Directory) { throw 'Terminal capture requires the actual frozen evidence directory' }
& .venv/Scripts/python.exe -c 'import sys; from pathlib import Path; from hawedit.studio_private import PrivateDirectory; PrivateDirectory(Path(sys.argv[1])).verify()' $Directory
if ($LASTEXITCODE -ne 0) { throw 'Evidence directory privacy/identity was refused' }
$manifestPath = Join-Path $Directory 'source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($head -ne $manifest.head_sha -or $package -ne $manifest.source_package_sha256) { throw 'Candidate identity drift' }
if (@(Compare-Object @(git ls-files) @($manifest.files.path)).Count) { throw 'Tracked input membership drift' }
foreach ($item in $manifest.files) { if ((Hash (Join-Path $root $item.path)) -ne $item.sha256) { throw "Tracked input drift: $($item.path)" } }
if (@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*--junitxml=*last-test-run.xml*' }).Count) { throw 'Canonical pytest is still live' }
$exitPath = Join-Path $Directory 'gate-exit.json'
$result = Get-Content -LiteralPath $exitPath -Raw | ConvertFrom-Json
if ($result.head_sha -ne $head -or $result.source_package_sha256 -ne $package) { throw 'Terminal exit identity drift' }
$canonical = Join-Path $root '.gate/last-test-run.xml'
if ((Get-Item -LiteralPath $canonical).LastWriteTimeUtc -le [DateTime]::Parse($manifest.observed_at_utc).ToUniversalTime()) { throw 'Canonical report is stale' }
[xml]$report = Get-Content -LiteralPath $canonical -Raw
$cases = @($report.SelectNodes('//testcase'))
if (-not $cases.Count) { throw 'Empty canonical report' }
$failures = @($cases | Where-Object { $_.SelectSingleNode('failure') })
$errors = @($cases | Where-Object { $_.SelectSingleNode('error') })
$skips = @($cases | Where-Object { $_.SelectSingleNode('skipped') })
$groups = [ordered]@{}
foreach ($name in @('acceptance_authority','comparison_contract','comparison_kit','visual_scorecard','editorial_acceptance','claims','build','git_distribution','release')) {
    $selected = @($cases | Where-Object { $_.classname -eq "tests.test_$name" })
    $groups[$name] = @{count=$selected.Count; all_passed_without_skips=($selected.Count -gt 0 -and -not @($selected | Where-Object { $_.SelectSingleNode('failure|error|skipped') }).Count)}
}
$logPath = Join-Path $Directory 'gate.log'
$log = Get-Content -LiteralPath $logPath -Raw
$summary = [regex]::Matches($log, '(?m)^(?:=+ )?[0-9]+ (?:passed|failed|errors?|skipped)[^\r\n]* in (?<seconds>[0-9.]+)s[^\r\n]*\r?$')
if (-not $summary.Count) { throw 'No actual terminal pytest summary' }
$snapshot = Join-Path $Directory 'junit.xml'
if (Test-Path -LiteralPath $snapshot) { throw 'Refusing report overwrite' }
Copy-Item -LiteralPath $canonical -Destination $snapshot
SaveNew 'test-evidence.json' ([ordered]@{
    schema=1; status='unaccepted-committed-engineering-evidence'; observed_at_utc=[DateTime]::UtcNow.ToString('o')
    head_sha=$head; branch=(git branch --show-current); source_package_sha256=$package; clean_checkout=$true
    command='C:/Program Files/Git/bin/bash.exe scripts/verify.sh'; exit_code=$result.exit_code
    gate_passed=($result.exit_code -eq 0 -and $log.Contains('VERIFY OK')); required_hosted_ci_verified=$false
    lint_types_format_passed=($log.Contains('All checks passed!') -and $log.Contains('Success: no issues found') -and $log.Contains('files already formatted'))
    elapsed_pytest_seconds=[double]::Parse($summary[$summary.Count-1].Groups['seconds'].Value,[Globalization.CultureInfo]::InvariantCulture)
    total_cases=$cases.Count; passed=($cases.Count-$failures.Count-$errors.Count-$skips.Count)
    failures=$failures.Count; errors=$errors.Count; skipped=$skips.Count; verified_groups=$groups
    failed_case_names=@(@($failures)+@($errors) | ForEach-Object { "$($_.classname).$($_.name)" })
    canonical_report_sha256=(Hash $canonical); report_snapshot_sha256=(Hash $snapshot)
    gate_log_sha256=(Hash $logPath); source_manifest_sha256=(Hash $manifestPath); exit_record_sha256=(Hash $exitPath)
    runtime_sha256=(Hash (Join-Path $Directory 'runtime.json')); host_observation_sha256=(Hash (Join-Path $Directory 'prior-host-observation.json'))
})
Write-Output "Terminal clean-commit evidence: $($cases.Count) cases; $($failures.Count) failures; $($errors.Count) errors; $($skips.Count) skipped."
