param(
    [string]$Distribution = ""
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repository ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Run scripts/setup.sh first; the HawEdit host virtual environment is missing."
}
$commandArguments = @("-m", "hawedit.wsl_setup")
if ($Distribution) {
    $commandArguments += @("--distribution", $Distribution)
}
& $python @commandArguments
if ($LASTEXITCODE -ne 0) {
    throw "OmniASR WSL2 setup failed with exit code $LASTEXITCODE"
}
