$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartupDir = [Environment]::GetFolderPath("Startup")
$OldBat = Join-Path $StartupDir "Jarvis Local Assistant.bat"
$Target = Join-Path $StartupDir "Jarvis Local Assistant.vbs"
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "pythonw.exe" }

@"
" Hidden launcher for Jarvis Local Assistant
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "$ProjectDir"
shell.Run Chr(34) & "$Python" & Chr(34) & " " & Chr(34) & "$ProjectDir\main.py" & Chr(34), 0, False
"@ | Set-Content -Path $Target -Encoding ASCII

if (Test-Path $OldBat) {
    Remove-Item $OldBat -Force
}

Write-Host "Installed Startup folder launcher:"
Write-Host $Target
