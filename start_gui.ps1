param([string]$Workspace = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$gui = Join-Path $PSScriptRoot 'scripts\import_gui.py'
if (Test-Path -LiteralPath $localPython) {
    & $localPython $gui --workspace $Workspace
} else {
    & python $gui --workspace $Workspace
}
exit $LASTEXITCODE
