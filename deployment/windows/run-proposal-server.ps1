param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path,
    [string]$VenvPath = (Join-Path $RepoRoot ".venv-directml"),
    [string]$ModelPath,
    [string]$ModelKind = "BiRefNet HR-matting",
    [string]$ModelVersion,
    [string]$ModelLicense = "MIT",
    [string]$WeightsSha256,
    [ValidateSet(1024, 2048)][int]$InputSize = 1024,
    [ValidateSet("logits", "alpha", "foreground")][string]$OutputMode = "logits",
    [int]$Port = 8012,
    [switch]$AllowCpuFallback
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $ModelPath -or -not $ModelVersion -or -not $WeightsSha256) {
    throw "ModelPath, ModelVersion and WeightsSha256 are required; never start an unpinned model server."
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { throw "DirectML virtualenv not found. Run setup-directml.ps1 first." }

$env:MODEL_PATH = $ModelPath
$env:MODEL_KIND = $ModelKind
$env:MODEL_VERSION = $ModelVersion
$env:MODEL_LICENSE = $ModelLicense
$env:MODEL_WEIGHTS_SHA256 = $WeightsSha256.ToLowerInvariant()
$env:MODEL_INPUT_SIZE = [string]$InputSize
$env:MODEL_OUTPUT_MODE = $OutputMode
$env:MODEL_REQUIRE_DIRECTML = if ($AllowCpuFallback) { "0" } else { "1" }
$env:HOST = "0.0.0.0"
$env:PORT = [string]$Port

Push-Location $RepoRoot
try {
    & $VenvPython -m uvicorn scripts.serve_onnx_proposals:app --host $env:HOST --port $Port --workers 1
    if ($LASTEXITCODE -ne 0) { throw "ONNX proposal server exited with code $LASTEXITCODE" }
}
finally { Pop-Location }
