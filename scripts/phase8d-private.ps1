[CmdletBinding()]
param(
    [ValidateSet("Preflight", "Run", "Status", "Stop")]
    [string]$Action = "Preflight",
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [switch]$AcknowledgeCertificateTransparency,
    [switch]$AcknowledgePrivateGrant
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = Join-Path $repoRoot "runtime\phase8d-private"
$statusPath = Join-Path $runtimeRoot "tailscale-status.json"
$markerPath = Join-Path $runtimeRoot "active-deployment.json"

function Get-TailscaleCommand {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    $installed = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if (Test-Path -LiteralPath $installed -PathType Leaf) {
        return $installed
    }
    throw "Tailscale is not installed. Install official Tailscale.Tailscale package first."
}

function Invoke-Tailscale {
    param(
        [Parameter(Mandatory)]
        [string]$Executable,
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & $Executable @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "Tailscale command failed with exit code $exitCode`: $($output -join ' ')"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
}

function Get-PrivatePlan {
    param(
        [Parameter(Mandatory)]
        [string]$Tailscale,
        [Parameter(Mandatory)]
        [int]$BackendPort
    )

    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    $status = Invoke-Tailscale -Executable $Tailscale -Arguments @("status", "--json")
    [IO.File]::WriteAllLines($statusPath, $status.Output)
    try {
        $rendered = & uv run jarvis remote deployment-plan `
            --tailscale-status-json $statusPath `
            --backend-port $BackendPort
        if ($LASTEXITCODE -ne 0) {
            throw "JARVIS rejected current Tailscale deployment state."
        }
        return ($rendered -join [Environment]::NewLine | ConvertFrom-Json)
    }
    finally {
        Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue
    }
}

function Assert-NoPublicFunnel {
    param([Parameter(Mandatory)][string]$Tailscale)

    $result = Invoke-Tailscale -Executable $Tailscale -Arguments @("funnel", "status", "--json") -AllowFailure
    $text = $result.Output -join [Environment]::NewLine
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($text)) {
        return
    }
    try {
        $config = $text | ConvertFrom-Json
    }
    catch {
        throw "Unable to parse Tailscale Funnel status safely."
    }
    $allowFunnel = $config.PSObject.Properties["AllowFunnel"]
    $enabledCount = 0
    if ($null -ne $allowFunnel) {
        $enabledCount = @(
            $allowFunnel.Value.PSObject.Properties |
                Where-Object { [bool]$_.Value }
        ).Count
    }
    if ($enabledCount -gt 0) {
        throw "Public Tailscale Funnel is configured. Disable it before JARVIS deployment."
    }
}

function Assert-LoopbackListenerBoundary {
    param([Parameter(Mandatory)][int]$BackendPort)

    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue)
    $unsafe = @($listeners | Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") })
    if ($unsafe.Count -gt 0) {
        throw "Port $BackendPort has a non-loopback listener. Refusing private deployment."
    }
    return $listeners
}

function Assert-BackendPortFree {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$Listeners,
        [Parameter(Mandatory)]
        [int]$BackendPort
    )

    if ($Listeners.Count -gt 0) {
        throw "Port $BackendPort is already occupied. Stop the existing backend before Run."
    }
}

function Get-ServeStatusText {
    param([Parameter(Mandatory)][string]$Tailscale)

    $result = Invoke-Tailscale -Executable $Tailscale -Arguments @("serve", "status") -AllowFailure
    return ($result.Output -join [Environment]::NewLine)
}

function Get-ServeStatusJson {
    param([Parameter(Mandatory)][string]$Tailscale)

    $result = Invoke-Tailscale -Executable $Tailscale -Arguments @("serve", "status", "--json") -AllowFailure
    $text = $result.Output -join [Environment]::NewLine
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    try {
        return ($text | ConvertFrom-Json)
    }
    catch {
        throw "Unable to parse Tailscale Serve status safely."
    }
}

function Assert-OwnedServeConfig {
    param(
        [Parameter(Mandatory)]
        [object]$Config,
        [Parameter(Mandatory)]
        [object]$Marker
    )

    $markerNames = @($Marker.PSObject.Properties.Name | Sort-Object)
    $expectedMarkerNames = @("backend_url", "created_at", "https_port", "origin", "topology") | Sort-Object
    if (($markerNames -join "|") -ne ($expectedMarkerNames -join "|")) {
        throw "Deployment marker shape changed; refusing to remove Serve configuration."
    }
    if (
        [string]$Marker.topology -ne "tailscale-serve" -or
        [int]$Marker.https_port -ne 443 -or
        [string]$Marker.backend_url -notmatch '^http://127\.0\.0\.1:[1-9][0-9]{0,4}$'
    ) {
        throw "Deployment marker is invalid; refusing to remove Serve configuration."
    }
    $origin = $null
    if (-not [Uri]::TryCreate([string]$Marker.origin, [UriKind]::Absolute, [ref]$origin)) {
        throw "Deployment marker origin is invalid; refusing to remove Serve configuration."
    }
    if ($origin.Scheme -ne "https" -or $origin.Port -ne 443 -or -not $origin.Host.EndsWith(".ts.net")) {
        throw "Deployment marker origin is not private Tailscale HTTPS."
    }

    $topLevelNames = @($Config.PSObject.Properties.Name | Sort-Object)
    if (($topLevelNames -join "|") -ne ((@("TCP", "Web") | Sort-Object) -join "|")) {
        throw "Current Serve configuration changed; refusing to remove it."
    }
    $tcpProperties = @($Config.TCP.PSObject.Properties)
    $webProperties = @($Config.Web.PSObject.Properties)
    $authority = "$($origin.DnsSafeHost):443"
    if ($tcpProperties.Count -ne 1 -or $tcpProperties[0].Name -ne "443") {
        throw "Current Serve TCP configuration changed; refusing to remove it."
    }
    $tcp443 = $tcpProperties[0].Value
    $tcp443Names = @($tcp443.PSObject.Properties.Name)
    if ($tcp443Names.Count -ne 1 -or $tcp443Names[0] -ne "HTTPS" -or $tcp443.HTTPS -ne $true) {
        throw "Current Serve HTTPS configuration changed; refusing to remove it."
    }
    if ($webProperties.Count -ne 1 -or $webProperties[0].Name -ne $authority) {
        throw "Current Serve web authority changed; refusing to remove it."
    }
    $handlers = $webProperties[0].Value.Handlers
    $handlerProperties = @($handlers.PSObject.Properties)
    if (
        $handlerProperties.Count -ne 1 -or
        $handlerProperties[0].Name -ne "/" -or
        [string]$handlerProperties[0].Value.Proxy -ne [string]$Marker.backend_url
    ) {
        throw "Current Serve handler changed; refusing to remove it."
    }
}

function Stop-OwnedServe {
    param([Parameter(Mandatory)][string]$Tailscale)

    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "No Phase 8D deployment marker exists; refusing to alter Serve configuration."
    }
    $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding utf8 | ConvertFrom-Json
    $serveConfig = Get-ServeStatusJson -Tailscale $Tailscale
    if ($null -eq $serveConfig) {
        throw "Current Serve configuration is unavailable; refusing to remove it."
    }
    Assert-OwnedServeConfig -Config $serveConfig -Marker $marker
    Invoke-Tailscale -Executable $Tailscale -Arguments @("serve", "--https=443", "off") | Out-Null
    Remove-Item -LiteralPath $markerPath -Force
    Write-Host "Private JARVIS Serve route stopped."
}

$tailscale = Get-TailscaleCommand

if ($Action -eq "Stop") {
    Stop-OwnedServe -Tailscale $tailscale
    exit 0
}

$plan = Get-PrivatePlan -Tailscale $tailscale -BackendPort $Port
Assert-NoPublicFunnel -Tailscale $tailscale
$backendListeners = @(Assert-LoopbackListenerBoundary -BackendPort $Port)
$serveStatus = Get-ServeStatusText -Tailscale $tailscale

if ($Action -eq "Status") {
    [pscustomobject]@{
        topology = $plan.topology
        origin = $plan.origin
        backend_url = "http://127.0.0.1:$Port"
        loopback_only = $true
        public_exposure = $false
        funnel_allowed = $false
        backend_listening = $backendListeners.Count -gt 0
        deployment_marker = Test-Path -LiteralPath $markerPath -PathType Leaf
        serve_status = $serveStatus
    } | ConvertTo-Json -Depth 5
    exit 0
}

Assert-BackendPortFree -Listeners $backendListeners -BackendPort $Port

if ($Action -eq "Preflight") {
    Write-Host "Phase 8D preflight passed."
    Write-Host "Origin: $($plan.origin)"
    Write-Host "Backend: http://127.0.0.1:$Port"
    Write-Host "No public Funnel detected; no non-loopback backend listener detected."
    exit 0
}

if (-not $AcknowledgeCertificateTransparency) {
    throw "Run requires -AcknowledgeCertificateTransparency; the exact *.ts.net hostname enters public Certificate Transparency logs."
}
if (-not $AcknowledgePrivateGrant) {
    throw "Run requires -AcknowledgePrivateGrant after tailnet access is restricted to the intended user/device and TCP 443."
}
if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
    throw "Phase 8D deployment marker already exists. Use Status or Stop."
}
if ($serveStatus -match "(?im)^https?://|(?im)^tcp://") {
    throw "Existing Tailscale Serve configuration found. Refusing to overwrite unrelated routes."
}

$backendUrl = "http://127.0.0.1:$Port"
Invoke-Tailscale -Executable $tailscale -Arguments @("serve", "--bg", "--yes", $backendUrl) | Out-Null
$verifiedServe = Get-ServeStatusText -Tailscale $tailscale
if ($verifiedServe -notmatch [regex]::Escape($backendUrl)) {
    throw "Tailscale Serve did not report the exact loopback backend target."
}

[pscustomobject]@{
    topology = "tailscale-serve"
    origin = $plan.origin
    backend_url = $backendUrl
    https_port = 443
    created_at = [DateTimeOffset]::Now.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding utf8

$previousHost = $env:JARVIS_WEB_HOST
$previousPort = $env:JARVIS_WEB_PORT
$previousOrigins = $env:JARVIS_TRUSTED_BROWSER_ORIGINS
$previousPythonIoEncoding = $env:PYTHONIOENCODING
try {
    $env:JARVIS_WEB_HOST = "127.0.0.1"
    $env:JARVIS_WEB_PORT = [string]$Port
    $env:JARVIS_TRUSTED_BROWSER_ORIGINS = ConvertTo-Json -InputObject @($plan.origin) -Compress
    $env:PYTHONIOENCODING = "utf-8"
    & uv run jarvis doctor
    if ($LASTEXITCODE -ne 0) {
        throw "JARVIS diagnostics failed; private listener not started."
    }
    Write-Host "Private PWA: $($plan.origin)/app/"
    Write-Host "Press Ctrl+C to stop JARVIS; Serve rollback runs automatically."
    & uv run jarvis serve
    if ($LASTEXITCODE -ne 0) {
        throw "JARVIS server exited with code $LASTEXITCODE."
    }
}
finally {
    $env:JARVIS_WEB_HOST = $previousHost
    $env:JARVIS_WEB_PORT = $previousPort
    $env:JARVIS_TRUSTED_BROWSER_ORIGINS = $previousOrigins
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
    if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
        Stop-OwnedServe -Tailscale $tailscale
    }
}
