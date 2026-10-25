param([ValidateRange(1,16)][int]$Jobs = 4, [string]$Resume, [string]$BuildRoot)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $taskVswhere)) { throw 'Install the native-build.vsconfig prerequisites first.' }
$taskVs = & $taskVswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $taskVs) { throw 'Visual Studio C++ Build Tools were not found.' }
$taskDeveloper = Join-Path $taskVs 'Common7\Tools\VsDevCmd.bat'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create the application .venv first.' }
$taskLocal = Join-Path $taskRoot '.native-build'
New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
$taskBatch = Join-Path $taskLocal ('invoke-native-' + [guid]::NewGuid().ToString('N') + '.cmd')
$taskResumeArgument = ''
if ($Resume) {
    $taskResolvedResume = (Resolve-Path -LiteralPath $Resume).Path
    $taskResumeArgument = ' --resume "' + $taskResolvedResume + '"'
}
$taskBuildRootArgument = ''
if ($BuildRoot) {
    $taskResolvedBuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
    $taskBuildRootArgument = ' --build-root "' + $taskResolvedBuildRoot + '"'
}
$taskLines = @(
    '@echo off',
    ('call "' + $taskDeveloper + '" -arch=x64 -host_arch=x64'),
    'if errorlevel 1 exit /b %errorlevel%',
    ('"' + $taskPython + '" "' + (Join-Path $PSScriptRoot 'build_native_step.py') + '" --generator Ninja --jobs ' + $Jobs + $taskResumeArgument + $taskBuildRootArgument),
    'exit /b %errorlevel%'
)
Set-Content -LiteralPath $taskBatch -Value $taskLines -Encoding ascii
try {
    & $env:ComSpec /d /c $taskBatch
    $taskResult = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $taskBatch -Force
}
exit $taskResult
