# Capture terminal canonical evidence without writing the gate's protected outputs.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path '.').Path
$folder = Join-Path $root 'specs/evidence-based-studio'
$manifestPath = Join-Path $folder 'T3-private-journal-source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($file in $manifest.files) {
    $actual = (Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $file.sha256) { throw "Frozen file drift: $($file.path)" }
}
$actualPackage = & .venv/Scripts/python.exe -c 'from hawedit.wsl_setup import package_digest; print(package_digest())'
if ($LASTEXITCODE -ne 0 -or $actualPackage -ne $manifest.source_package_sha256) {
    throw 'Frozen package identity changed'
}
$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*--junitxml=*last-test-run.xml*'
})
if ($running.Count) { throw 'Canonical pytest process still running' }
$canonical = Join-Path $root '.gate/last-test-run.xml'
if ((Get-Item -LiteralPath $canonical).LastWriteTimeUtc -le [DateTime]::Parse($manifest.observed_at_utc).ToUniversalTime()) {
    throw 'Canonical JUnit is not fresh for this frozen unit'
}
[xml]$report = Get-Content -LiteralPath $canonical -Raw
$cases = @($report.SelectNodes('//testcase'))
if (-not $cases.Count) { throw 'Empty canonical report' }
$failed = @($cases | Where-Object { $_.SelectSingleNode('failure') })
$errors = @($cases | Where-Object { $_.SelectSingleNode('error') })
$skipped = @($cases | Where-Object { $_.SelectSingleNode('skipped') })
$groups = [ordered]@{}
foreach ($name in @('studio_private','studio_billing','studio_submissions','studio_queue','studio_uploads','studio_generation','studio_artifacts','studio_history','studio_ui','claims')) {
    $selected = @($cases | Where-Object { $_.classname -eq "tests.test_$name" })
    $bad = @($selected | Where-Object { $_.SelectSingleNode('failure|error|skipped') })
    $groups[$name] = [ordered]@{
        count = $selected.Count
        names = @($selected | ForEach-Object { $_.name })
        all_passed_without_skips = $selected.Count -gt 0 -and $bad.Count -eq 0
    }
}
$logPath = Join-Path $folder 'gate-T3-private-journal.log'
$log = Get-Content -LiteralPath $logPath -Raw
$summary = [regex]::Matches($log, '(?m)^(?:=+ )?[0-9]+ (?:passed|failed|errors?|skipped)[^\r\n]* in (?<seconds>[0-9.]+)s[^\r\n]*\r?$')
if (-not $summary.Count) { throw 'No terminal pytest summary' }
$elapsed = [double]::Parse($summary[$summary.Count - 1].Groups['seconds'].Value, [Globalization.CultureInfo]::InvariantCulture)
$snapshot = Join-Path $folder 'T3-private-journal-junit.xml'
$destination = Join-Path $folder 'T3-private-journal-test-evidence.json'
if ((Test-Path -LiteralPath $snapshot) -or (Test-Path -LiteralPath $destination)) {
    throw 'Refusing to overwrite an existing terminal evidence record'
}
Copy-Item -LiteralPath $canonical -Destination $snapshot
$runtime = (Get-Content -LiteralPath (Join-Path $folder 'T3-private-journal-host.json') -Raw | ConvertFrom-Json).runtime
$related = @('T3-private-journal-host.json','T3-private-journal-posix-final.json','T3-private-journal-posix-final.log','private_journal_posix_probe.py','serena-T3-private-final-map.json','serena-T3-private-final.log','private_journal_serena.py','record_private_journal_gate.ps1','T3-private-journal-test-first.log','T3-private-journal-focused.log','T3-private-journal-focused-final.log','T3-private-journal-focused-junit.xml','T3-private-journal-fast-final-v2.log')
$relatedHashes = [ordered]@{}
foreach ($path in $related) {
    $relatedHashes[$path] = (Get-FileHash -LiteralPath (Join-Path $folder $path) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result = [ordered]@{
    schema = 1
    status = 'unaccepted-engineering-evidence'
    observed_at_utc = [DateTime]::UtcNow.ToString('o')
    head_sha = (git rev-parse HEAD)
    uncommitted_source = $true
    source_package_sha256 = $actualPackage
    python = $runtime.python
    sqlite = $runtime.sqlite
    libraries = $runtime.libraries
    gate_command = 'C:/Program Files/Git/bin/bash.exe scripts/verify.sh'
    gate_exit_code = 1
    gate_passed = $false
    lint_types_format_passed = $log.Contains('270 files already formatted') -and $log.Contains('Success: no issues found in 270 source files')
    lint_types_format_file_count = 270
    elapsed_pytest_seconds = $elapsed
    total_cases = $cases.Count
    passed = $cases.Count - $failed.Count - $errors.Count - $skipped.Count
    failures = $failed.Count
    errors = $errors.Count
    skipped = $skipped.Count
    failed_case_names = @(@($failed) + @($errors) | ForEach-Object { "$($_.classname).$($_.name)" })
    verified_groups = $groups
    canonical_report_sha256 = (Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash.ToLowerInvariant()
    report_snapshot = 'T3-private-journal-junit.xml'
    report_snapshot_sha256 = (Get-FileHash -LiteralPath $snapshot -Algorithm SHA256).Hash.ToLowerInvariant()
    gate_log = 'gate-T3-private-journal.log'
    gate_log_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
    source_file_manifest = 'T3-private-journal-source-manifest.json'
    source_file_manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    related_evidence_sha256 = $relatedHashes
    limits = @(
        'Terminal process/exit code must be verified independently before running this recorder; no gate outputs were edited.',
        'Windows canonical gate, not a Linux gate. POSIX standalone probe is separately version/filesystem bound.',
        'Journal-only privacy and transport-lifetime binding, not persisted supervisor authority or whole-studio storage/authentication.',
        'Local protocol and actual SQLite/native filesystem tests, not provider access, cap/invoice semantics or paid-call authorization.',
        'No model inference, real creator/editor/reel-quality/performance study, publication, release or 10/10 acceptance.',
        'No ledger flip or current-SHA CI; clean build, staged font absent from HEAD archive and current qualified VEX remain open.'
    )
}
if ($failed.Count + $errors.Count -eq 0) { throw 'Unexpected green pytest: review actual gate exit/grading before recording' }
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $destination -Encoding utf8
Write-Output "$($result.passed) passed; $($result.failures) failed; $($result.errors) errors; $($result.skipped) skipped; $elapsed seconds"
foreach ($key in $groups.Keys) { Write-Output "$key`: $($groups[$key].count), all passed=$($groups[$key].all_passed_without_skips)" }
