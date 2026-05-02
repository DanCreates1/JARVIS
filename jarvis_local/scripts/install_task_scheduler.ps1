$ErrorActionPreference = "Stop"

$TaskName = "JarvisLocalAssistant"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$MainPy = Join-Path $ProjectDir "main.py"
$VenvPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$Pythonw = if (Test-Path $VenvPythonw) {
    $VenvPythonw
} else {
    (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}

if (-not $Pythonw) {
    throw "pythonw.exe was not found on PATH. Install Python 3.11 and enable 'Add python.exe to PATH', or edit this script with the full pythonw.exe path."
}

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$MainPy`"" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Starts Jarvis Local Assistant at Windows logon." `
    -Force

Write-Host "Installed scheduled task: $TaskName"
