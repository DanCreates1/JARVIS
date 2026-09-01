[CmdletBinding()]
param(
    [string]$Model = "nemotron-3-nano:4b"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (
    $Model.Length -gt 128 -or
    $Model -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
) {
    throw "Model must be a valid Ollama model name, for example nemotron-3-nano:4b."
}

$ollamaCommand = Get-Command "ollama" -ErrorAction SilentlyContinue
if ($null -eq $ollamaCommand) {
    throw "Ollama is required. Install it from https://ollama.com/download/windows and rerun this script."
}

Write-Host "Downloading Ollama model '$Model'. Model weights remain outside this repository."
& $ollamaCommand.Source "pull" $Model
if ($LASTEXITCODE -ne 0) {
    throw "Ollama could not pull model '$Model'. Confirm that Ollama is running and the model name is valid."
}

Write-Host "Verifying model metadata..."
& $ollamaCommand.Source "show" $Model
if ($LASTEXITCODE -ne 0) {
    throw "Ollama downloaded the model but could not read its metadata."
}

Write-Host "Model '$Model' is ready."
Write-Host "Set JARVIS_OLLAMA_MODEL=$Model when this is not the configured default."
Write-Host "Next: uv run jarvis doctor"
