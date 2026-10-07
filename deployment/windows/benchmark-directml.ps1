param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path,
    [string]$VenvPath = (Join-Path $RepoRoot ".venv-directml"),
    [string]$Source = (Join-Path $RepoRoot "artifacts\Panther_4500x5400_300DPI.png"),
    [string]$ModelPath,
    [string]$ModelKind = "BiRefNet HR-matting",
    [string]$ModelVersion,
    [string]$ModelLicense = "MIT",
    [string]$WeightsSha256,
    [switch]$AllowCpuFallback
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $ModelPath -or -not $ModelVersion -or -not $WeightsSha256) {
    throw "ModelPath, ModelVersion and WeightsSha256 are required."
}
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$env:MODEL_PATH = $ModelPath
$env:MODEL_KIND = $ModelKind
$env:MODEL_VERSION = $ModelVersion
$env:MODEL_LICENSE = $ModelLicense
$env:MODEL_WEIGHTS_SHA256 = $WeightsSha256.ToLowerInvariant()
$env:MODEL_OUTPUT_MODE = "logits"
$env:MODEL_REQUIRE_DIRECTML = if ($AllowCpuFallback) { "0" } else { "1" }

Push-Location $RepoRoot
try {
    & $VenvPython scripts\benchmark_onnx_proposals.py $Source --sizes 1024 2048 --warmup 1 --runs 3
    if ($LASTEXITCODE -ne 0) { throw "One or more ONNX benchmark sizes failed." }
}
finally { Pop-Location }
