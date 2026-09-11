[CmdletBinding()]
param(
    [switch]$InstallUv,
    [switch]$InstallPython,
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

function Find-OfficialPython311 {
    $candidates = [Collections.Generic.List[string]]::new()
    $launcher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        $launcherOutput = & $launcher.Source -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($line in @($launcherOutput)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$line)) {
                    $candidates.Add(([string]$line).Trim())
                }
            }
        }
    }
    $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"))
    $candidates.Add((Join-Path $env:ProgramFiles "Python311\python.exe"))

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $metadata = [Diagnostics.FileVersionInfo]::GetVersionInfo($resolved)
        if ($metadata.CompanyName -ne "Python Software Foundation") {
            continue
        }
        $version = & $resolved -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and ([string]$version).Trim() -eq "3.11") {
            return $resolved
        }
    }
    return $null
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

$pythonPath = Find-OfficialPython311
if ($null -eq $pythonPath -and $InstallPython) {
    $wingetCommand = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($null -eq $wingetCommand) {
        throw "Official CPython 3.11 is missing and winget is unavailable. Install Python.Python.3.11 and rerun this script."
    }
    Write-Host "Installing official CPython 3.11 through Windows Package Manager..."
    Invoke-NativeCommand -FilePath $wingetCommand.Source -Arguments @(
        "install",
        "--id", "Python.Python.3.11",
        "--exact",
        "--scope", "user",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )
    $pythonPath = Find-OfficialPython311
}
if ($null -eq $pythonPath) {
    throw "Official Python Software Foundation CPython 3.11 is required. Install it with winget install --id Python.Python.3.11 --exact --scope user, or rerun with -InstallPython."
}

Push-Location $repoRoot
try {
    Write-Host "Using official CPython 3.11: $pythonPath"

    Write-Host "Synchronizing the locked environment..."
    # OneDrive-backed Windows checkouts can reject cache hardlinks with OS error 396.
    # Copies preserve lock enforcement without coupling the environment to cache files.
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @(
        "sync", "--locked", "--link-mode", "copy",
        "--python", $pythonPath,
        "--no-managed-python", "--no-python-downloads"
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
