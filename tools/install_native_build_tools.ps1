# Install the Microsoft compiler/SDK used for native release builds.
# Run interactively: Windows requests administrator approval through UAC.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskConfig = Join-Path $taskRoot 'packaging\native-build.vsconfig'
$taskInstaller = Join-Path $env:TEMP 'kicad-loader-vs-buildtools-2022.exe'
Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vs/17/release/vs_buildtools.exe' -OutFile $taskInstaller
$taskSignature = Get-AuthenticodeSignature -LiteralPath $taskInstaller
if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'The Build Tools installer does not have a valid Microsoft signature.'
}
$taskArguments = '--config "' + $taskConfig + '" --passive --wait --norestart'
$taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList $taskArguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
if ($taskProcess.ExitCode -notin @(0, 3010)) {
    throw ('Build Tools installer returned ' + $taskProcess.ExitCode)
}
if ($taskProcess.ExitCode -eq 3010) {
    Write-Output 'Build Tools installed. Windows reports that a restart is required; no restart was performed.'
} else {
    Write-Output 'Build Tools installed. Open a new terminal before building.'
}
