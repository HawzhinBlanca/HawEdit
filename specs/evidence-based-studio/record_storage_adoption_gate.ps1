# Capture actual terminal evidence; never write the gate's protected outputs.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path '.').Path
$folder = Join-Path $root 'specs/evidence-based-studio'
$manifestPath = Join-Path $folder 'T3-storage-source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$current = @(Get-ChildItem -LiteralPath src,tests,scripts -File -Recurse | Where-Object { $_.Extension -in @('.py','.sh') })
$current += @(Get-Item -LiteralPath README.md,PROGRESS.md,DECISIONS.md,pyproject.toml,AGENTS.md)
$setDrift = @(Compare-Object -ReferenceObject @($manifest.files | ForEach-Object { $_.path }) -DifferenceObject @($current | ForEach-Object { $_.FullName }))
if ($setDrift.Count) { throw 'Frozen source/test/script/document membership changed' }
foreach ($file in $manifest.files) {
    if ((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Frozen file drift: $($file.path)"
    }
}
$package = & .venv/Scripts/python.exe -c 'from hawedit.wsl_setup import package_digest; print(package_digest())'
if ($LASTEXITCODE -ne 0 -or $package -ne $manifest.source_package_sha256) {
    throw 'Frozen package identity changed'
}
$hostRecord = Get-Content -LiteralPath (Join-Path $folder 'T3-storage-host.json') -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath tests/fixtures/kurdish-speech-3cuts.mp4 -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hostRecord.fixture_sha256) {
    throw 'Actual upload fixture changed after host/input capture'
}
if ((Get-FileHash -LiteralPath $hostRecord.runtime.ffmpeg_path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hostRecord.runtime.ffmpeg_sha256) {
    throw 'Actual decoded-media executable changed after capture'
}
$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*--junitxml=*last-test-run.xml*'
})
if ($running.Count) { throw 'Canonical pytest is still running' }
$exitPath = Join-Path $folder 'T3-storage-gate-exit.json'
$exitRecord = Get-Content -LiteralPath $exitPath -Raw | ConvertFrom-Json
if ($exitRecord.source_package_sha256 -ne $package) { throw 'Gate exit identity mismatch' }
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
foreach ($name in @('studio_storage','studio_private','studio_billing','studio_submissions','studio_queue','studio_uploads','studio_generation','studio_artifacts','studio_history','studio_ui','claims')) {
    $selected = @($cases | Where-Object { $_.classname -eq "tests.test_$name" })
    $bad = @($selected | Where-Object { $_.SelectSingleNode('failure|error|skipped') })
    $groups[$name] = [ordered]@{
        count = $selected.Count
        names = @($selected | ForEach-Object { $_.name })
        all_passed_without_skips = $selected.Count -gt 0 -and $bad.Count -eq 0
    }
}
$logPath = Join-Path $folder 'gate-T3-storage.log'
$log = Get-Content -LiteralPath $logPath -Raw
$summary = [regex]::Matches($log, '(?m)^(?:=+ )?[0-9]+ (?:passed|failed|errors?|skipped)[^\r\n]* in (?<seconds>[0-9.]+)s[^\r\n]*\r?$')
if (-not $summary.Count) { throw 'No terminal pytest summary' }
$elapsed = [double]::Parse($summary[$summary.Count - 1].Groups['seconds'].Value, [Globalization.CultureInfo]::InvariantCulture)
$types = [regex]::Match($log, 'Success: no issues found in (?<count>[0-9]+) source files')
$format = [regex]::Match($log, '(?<count>[0-9]+) files already formatted')
$snapshot = Join-Path $folder 'T3-storage-junit.xml'
$destination = Join-Path $folder 'T3-storage-test-evidence.json'
if ((Test-Path -LiteralPath $snapshot) -or (Test-Path -LiteralPath $destination)) {
    throw 'Refusing to overwrite terminal evidence'
}
Copy-Item -LiteralPath $canonical -Destination $snapshot
$related = @('T3-storage-host.json','T3-storage-posix.json','T3-storage-posix.log','storage_adoption_posix_probe.py','T3-storage-posix-wal.json','T3-storage-posix-wal.log','private_journal_posix_probe.py','serena-T3-storage-final-map.json','serena-T3-storage-final.log','storage_adoption_serena.py','record_storage_adoption_gate.ps1','T3-storage-test-first.log','T3-storage-container-test-first.log','T3-storage-focused-final.log','T3-storage-focused-final-junit.xml','T3-storage-security-final.log','T3-storage-security-final-junit.xml','T3-storage-security-v2.log','T3-storage-security-v2-junit.xml','T3-storage-fast-final.log','T3-storage-gate-exit.json')
$relatedHashes = [ordered]@{}
$related += @('T3-storage-tool-runtime.json','T8-current-scorecard-counterexample.json','acceptance_current_probe.py','serena-T8-current-map.json','serena-T8-current.log','acceptance_serena.py','http-owner-boundary-research.md')
foreach ($path in $related) {
    $relatedHashes[$path] = (Get-FileHash -LiteralPath (Join-Path $folder $path) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result = [ordered]@{
    schema = 1
    status = 'unaccepted-engineering-evidence'
    observed_at_utc = [DateTime]::UtcNow.ToString('o')
    head_sha = (git rev-parse HEAD)
    uncommitted_source = $true
    source_package_sha256 = $package
    runtime_host_record = 'T3-storage-host.json'
    gate_command = 'C:/Program Files/Git/bin/bash.exe scripts/verify.sh'
    gate_exit_code = $exitRecord.exit_code
    gate_passed = $exitRecord.exit_code -eq 0 -and $log.Contains('VERIFY OK')
    lint_types_format_passed = $log.Contains('All checks passed!') -and $types.Success -and $format.Success
    lint_types_file_count = $types.Groups['count'].Value
    format_file_count = $format.Groups['count'].Value
    elapsed_pytest_seconds = $elapsed
    total_cases = $cases.Count
    passed = $cases.Count - $failed.Count - $errors.Count - $skipped.Count
    failures = $failed.Count
    errors = $errors.Count
    skipped = $skipped.Count
    failed_case_names = @(@($failed) + @($errors) | ForEach-Object { "$($_.classname).$($_.name)" })
    verified_groups = $groups
    canonical_report_sha256 = (Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash.ToLowerInvariant()
    report_snapshot = 'T3-storage-junit.xml'
    report_snapshot_sha256 = (Get-FileHash -LiteralPath $snapshot -Algorithm SHA256).Hash.ToLowerInvariant()
    gate_log = 'gate-T3-storage.log'
    gate_log_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
    source_file_manifest = 'T3-storage-source-manifest.json'
    source_file_manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    related_evidence_sha256 = $relatedHashes
    limits = @(
        'Actual terminal exit is separately captured; gate outputs were never edited.',
        'Windows canonical gate; separate Linux probe is not a Linux gate or production mount certificate.',
        'Bounded private upload/outbox/billing checks, not complete race elimination or authenticated studio authority.',
        'Real fixture decoding and native HTTP, not paid/model execution, a media sandbox or reel-quality acceptance.',
        'No current-SHA CI, ledger completion, published deliverable, independent study or 10/10 verdict.'
    )
}
if ($result.gate_passed -and ($failed.Count + $errors.Count + $skipped.Count)) {
    throw 'Inconsistent successful gate claim'
}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $destination -Encoding utf8
Write-Output "$($result.passed) passed; $($result.failures) failed; $($result.errors) errors; $($result.skipped) skipped; $elapsed seconds; gate exit=$($result.gate_exit_code)"
foreach ($key in $groups.Keys) { Write-Output "$key`: $($groups[$key].count), all passed=$($groups[$key].all_passed_without_skips)" }
