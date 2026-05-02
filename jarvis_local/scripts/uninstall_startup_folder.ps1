$StartupDir = [Environment]::GetFolderPath("Startup")
$Targets = @(
    (Join-Path $StartupDir "Jarvis Local Assistant.bat"),
    (Join-Path $StartupDir "Jarvis Local Assistant.vbs")
)

foreach ($Target in $Targets) {
    if (Test-Path $Target) {
        Remove-Item $Target -Force
        Write-Host "Removed $Target"
    }
}

if (-not ($Targets | Where-Object { Test-Path $_ })) {
    Write-Host "Startup launcher was not installed."
}
