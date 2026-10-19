param([string]$Workspace = (Split-Path -Parent $PSScriptRoot))
& (Join-Path (Split-Path -Parent $PSScriptRoot) 'start_gui.ps1') -Workspace $Workspace
exit $LASTEXITCODE
