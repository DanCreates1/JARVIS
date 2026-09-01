[CmdletBinding()]
param(
    [switch]$InstallUv,
    [switch]$InstallModel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
$lockPath = Join-Path $repoRoot "uv.lock"

if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
    throw "pyproject.toml was not found at the repository root."
}
if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
    throw "uv.lock is required for reproducible setup and was not found."
}

$uvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
if ($null -eq $uvCommand -and $InstallUv) {
    $wingetCommand = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($null -eq $wingetCommand) {
        throw "uv is missing and winget is unavailable. Install uv from https://docs.astral.sh/uv/ and rerun this script."
    }

    Write-Host "Installing uv through Windows Package Manager..."
    Invoke-NativeCommand -FilePath $wingetCommand.Source -Arguments @(
        "install",
        "--id", "astral-sh.uv",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )
    $uvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($null -eq $uvCommand) {
        throw "uv was installed but is not visible in this PowerShell session. Open a new terminal and rerun ./scripts/bootstrap.ps1."
    }
}

if ($null -eq $uvCommand) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/ or rerun with -InstallUv when winget is available."
}

Push-Location $repoRoot
try {
    Write-Host "Provisioning Python 3.11..."
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("python", "install", "3.11")

    Write-Host "Synchronizing the locked environment..."
    # OneDrive-backed Windows checkouts can reject cache hardlinks with OS error 396.
    # Copies preserve lock enforcement without coupling the environment to cache files.
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @(
        "sync", "--locked", "--link-mode", "copy"
    )

    if ($InstallModel) {
        & (Join-Path $PSScriptRoot "setup-model.ps1")
    }
}
finally {
    Pop-Location
}

Write-Host "JARVIS dependencies are ready."
Write-Host "Next: uv run jarvis doctor"
Write-Host "Chat: uv run jarvis chat"
