# Windows DirectML inference host

This deployment is the local, non-paid proposal host required by the review.
It is intended for the Windows PC with the Radeon RX Vega 56. It uses native
Windows ONNX Runtime with `DmlExecutionProvider` first and an explicit CPU
fallback only when diagnostics permit it. It does not use ROCm or WSL2.

## Setup

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deployment\windows\setup-directml.ps1 -ConfigureFirewall
```

The setup script verifies that DirectML is visible before the environment is
considered ready. No model weights are downloaded by the repository.

## Run a pinned model

```powershell
.\deployment\windows\run-proposal-server.ps1 `
  -ModelPath 'C:\models\birefnet_hr_matting_1024.onnx' `
  -ModelVersion 'birefnet-export-<commit>' `
  -WeightsSha256 '<64-lowercase-hex-characters>'
```

The server exposes `GET /healthz` and `POST /v1/proposal`. The response is
compatible with the Linux `BiRefNetHRMattingProvider`/`BEN2MattingProvider`
ports and includes model metadata, provider, input size, timing, source hash,
proposal hash, alpha, protection and uncertainty carriers. The server is
single-worker and serializes inference requests to avoid DirectML memory
pressure.

The ONNX export must have this contract:

- input: `float32`, `NCHW`, RGB, ImageNet normalization;
- output: one `HxW` alpha/logit plane (`MODEL_OUTPUT_MODE` selects conversion);
- fixed input size 1024 or 2048, recorded in the deployment manifest;
- local model file hash must equal `MODEL_WEIGHTS_SHA256`.

## Benchmark

```powershell
.\deployment\windows\benchmark-directml.ps1 `
  -ModelPath 'C:\models\birefnet_hr_matting_1024.onnx' `
  -ModelVersion 'birefnet-export-<commit>' `
  -WeightsSha256 '<64-lowercase-hex-characters>'
```

The benchmark attempts batch-size-one runs at 1024 and 2048 and records
provider, min/median/max inference time and failures. A fixed 1024 export is
expected to reject the 2048 case; that failure is evidence that a separate
2048 export is required, not permission to silently resize the model.

The 4500×5400 source is resized only inside the proposal adapter. The returned
alpha is resized to source dimensions and then remains a non-authoritative
proposal. Photopea, semantic protection, checkpoint review and golden
validation remain mandatory downstream stages.
