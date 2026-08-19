[CmdletBinding()]
param(
    [switch]$Fix,
    [switch]$SkipAudit,
    [switch]$SkipSecrets
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
$uvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    throw "uv is required. Run ./scripts/bootstrap.ps1 first."
}

Push-Location $repoRoot
try {
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("lock", "--check")
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("sync", "--locked")

    if ($Fix) {
        Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "ruff", "format", ".")
        Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "ruff", "check", ".", "--fix")
    }
    else {
        Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "ruff", "format", "--check", ".")
        Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "ruff", "check", ".")
    }

    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "mypy", "src")
    Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "pytest")

    if (-not $SkipAudit) {
        Invoke-NativeCommand -FilePath $uvCommand.Source -Arguments @("run", "pip-audit")
    }

    if (-not $SkipSecrets) {
        $gitleaksCommand = Get-Command "gitleaks" -ErrorAction SilentlyContinue
        if ($null -eq $gitleaksCommand) {
            Write-Warning "Gitleaks is not installed locally; secret scanning remains mandatory in CI."
        }
        else {
            Invoke-NativeCommand -FilePath $gitleaksCommand.Source -Arguments @(
                "detect", "--source", $repoRoot, "--redact", "--no-banner"
            )
        }
    }

    $gitCommand = Get-Command "git" -ErrorAction SilentlyContinue
    if ($null -ne $gitCommand) {
        Invoke-NativeCommand -FilePath $gitCommand.Source -Arguments @("diff", "--check")
    }
}
finally {
    Pop-Location
}

Write-Host "All requested quality checks passed."
