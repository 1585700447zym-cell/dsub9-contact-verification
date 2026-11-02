param([string]$Python = "py", [switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$migrationRepo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location -LiteralPath $migrationRepo
$migrationVenv = Join-Path $migrationRepo ".venv"
$migrationPython = Join-Path $migrationVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $migrationPython)) {
    if ($Python -eq "py") { & py -3.13 -m venv $migrationVenv }
    else { & $Python -m venv $migrationVenv }
    if ($LASTEXITCODE -ne 0) { throw "Creating the Python environment failed." }
}
& $migrationPython -B -c "import sys; assert sys.version_info[:2] == (3,13) and sys.maxsize > 2**32, 'Python 3.13 x64 required'"
if ($LASTEXITCODE -ne 0) { throw "Python version check failed." }
if (-not $SkipInstall) {
    & $migrationPython -m pip install -r (Join-Path $migrationRepo "requirements-migration-20261102.txt")
    if ($LASTEXITCODE -ne 0) { throw "Installing dependencies failed; restore has not started." }
}
& $migrationPython -B -m tools.migration.package
if ($LASTEXITCODE -ne 0) { throw "Migration archive restore failed." }
& $migrationPython -B tools\migration\run_f4000.py --check --compile-model
if ($LASTEXITCODE -ne 0) { throw "State/runtime/model checks failed." }
Write-Output "Migration checks completed. No simulation steps, inference or training were started."
