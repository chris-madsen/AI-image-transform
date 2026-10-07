param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path,
    [string]$VenvPath = (Join-Path $RepoRoot ".venv-directml"),
    [string]$Python = "py",
    [switch]$ConfigureFirewall,
    [int]$Port = 8012
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "Creating Windows DirectML environment at $VenvPath"
& $Python -3.12 -m venv $VenvPath
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $RepoRoot
& $VenvPython -m pip install -r (Join-Path $RepoRoot "deployment\windows\requirements-directml.txt")

$Providers = & $VenvPython -c "import onnxruntime as ort; print(','.join(ort.get_available_providers()))"
Write-Host "ONNX Runtime providers: $Providers"
if ($Providers -notmatch "DmlExecutionProvider") {
    throw "DmlExecutionProvider is unavailable. Install a DirectX 12 driver or use explicit CPU-only diagnostics; do not claim GPU inference."
}

if ($ConfigureFirewall) {
    $RuleName = "Printify Artwork Cleaner DirectML $Port"
    Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet | Out-Null
    Write-Host "Allowed TCP/$Port from LocalSubnet only."
}

Write-Host "Environment ready. Copy deployment\windows\model.env.example, fill model metadata, then run run-proposal-server.ps1."
