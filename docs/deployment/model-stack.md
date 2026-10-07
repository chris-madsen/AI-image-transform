# Specialized Proposal Stack

The service accepts model output only from explicitly pinned deployment
adapters. It does not download weights, call a hosted fallback, or silently
replace a missing model with a color heuristic.

## Required production topology

```text
source + frozen intent
  -> BiRefNet HR-matting endpoint (proposal alpha)
  -> BEN2 endpoint (independent proposal alpha)
  -> SAM 2.1 endpoint or adapter (protected subject/detail regions)
  -> optional ViTMatte refinement endpoint
  -> consensus/uncertainty + deterministic exterior-only constraints
```

BiRefNet and BEN2 are implemented as independent HTTP proposal ports in
`printify_artwork_cleaner.adapters.model_proposals`. Their endpoint response
must echo the exact configured model name, version, license and SHA-256 hash of
the loaded weights. The service rejects any mismatch.

## Deployment configuration

The following variables are mandatory before the consensus provider can be
constructed. Missing variables or non-hex-64 weights hashes disable the
provider and make jobs fail closed with `review_required`.

```text
BIREFNET_ENDPOINT=https://matting.internal/birefnet
BIREFNET_MODEL_VERSION=<deployment-pinned-version>
BIREFNET_MODEL_LICENSE=<license-recorded-with-the-weight-release>
BIREFNET_WEIGHTS_SHA256=<64-lowercase-hex-characters>

BEN2_ENDPOINT=https://matting.internal/ben2
BEN2_MODEL_VERSION=<deployment-pinned-version>
BEN2_MODEL_LICENSE=<license-recorded-with-the-weight-release>
BEN2_WEIGHTS_SHA256=<64-lowercase-hex-characters>

SAM2_ENDPOINT=https://matting.internal/sam2-protection
SAM2_MODEL_VERSION=<deployment-pinned-version>
SAM2_MODEL_LICENSE=<license-recorded-with-the-weight-release>
SAM2_WEIGHTS_SHA256=<64-lowercase-hex-characters>
```

SAM 2.1 and optional ViTMatte are separate protection/refinement ports. SAM
2.1 is wired through `SAM2_ENDPOINT` and the typed `SAM21ProtectionProvider`;
its endpoint returns only a source-bound protection/uncertainty carrier. The
deployment adapter is `scripts/serve_sam2_protection.py`. It excludes
border-touching automatic masks and never emits final alpha. SAM must be
enabled only after its endpoint, version, license and weights manifest is
recorded. ViTMatte remains an optional refinement port and is not represented
by fake defaults in the core.

## Evidence required to promote a stack

For each model release, store outside Git or in the deployment registry:

1. exact upstream release/commit;
2. license and redistribution decision;
3. downloaded weights SHA-256;
4. image and mask input/output contract;
5. independent Panther golden acceptance result;
6. latency and memory measurements for the five-minute job budget.

The repository contains the adapter contracts and deployment-only serving
scripts, but model endpoints and weight files remain external runtime
resources. Therefore model deployment and visual acceptance must not be
marked complete until those resources are supplied and the golden fixture
passes.

## Reproducible local proposal server

`scripts/serve_model_proposals.py` is the deployment-only HTTP adapter for the
two pinned open model paths. It loads weights from an external directory,
checks the configured SHA-256 before startup, and exposes:

```text
GET  /healthz
POST /v1/proposal       # request body: source image bytes
```

The response contains alpha, protection and uncertainty PNG carriers plus
explicit model metadata, source-bound tuning, and a deliberately low-confidence
`model-preflight-not-approval` visual assessment. It cannot authorize a passed
job without the independent checkpoint reviewer.

Example Panther deployment values used for the 2026-10-06 local smoke:

```text
BiRefNet HR-matting
  upstream commit: ZhengPeng7/BiRefNet repository commit ebcc0bc8ec7fe919cec829f2dea656b3078acddc
  model snapshot: 5d6b6f8adcb5b417c871b1d84ceaae9871355b7f
  license: MIT
  model.safetensors SHA-256: a5a4de698739ea5e0e8bbab28e1b293dde95092b87a442d566cbc585c53cef55

BEN2
  upstream commit: PramaLLC/BEN2 repository commit 2c99a5da477b5523585bfa5c893888a6e818a8f
  license: MIT
  model.safetensors SHA-256: ea8b7907176a09667c86343dc7d00de6a6d871076cb90bb5f753618fd6fb3ebb
```

The local CPU smoke produced 31.1 seconds for BiRefNet and 17.1 seconds for
BEN2 at 1024 input before Photopea. It is evidence that the real adapters load
and answer; it is not a production latency claim. The generated Panther
consensus was visually inspected and rejected because the models retained a
visible halo and removed owner-approved decorative perimeter detail. Its report
therefore remains `review_required`.

## Windows DirectML deployment

The Windows inference host is implemented in `deployment/windows/` and
`scripts/serve_onnx_proposals.py`. It is the supported deployment path for the
Radeon RX Vega 56: native Windows ONNX Runtime is configured with
`DmlExecutionProvider` first and `CPUExecutionProvider` second. The session is
sequential, memory-pattern allocation is disabled, and the server runs one
request at a time. It does not use ROCm or WSL2.

```powershell
.\deployment\windows\setup-directml.ps1 -ConfigureFirewall
.\deployment\windows\run-proposal-server.ps1 `
  -ModelPath 'C:\models\birefnet_hr_matting_1024.onnx' `
  -ModelVersion 'birefnet-export-<commit>' `
  -WeightsSha256 '<64-lowercase-hex-characters>'
```

The setup script fails if DirectML is not visible. CPU fallback is available
only through the explicit `-AllowCpuFallback` diagnostic switch. The server
requires a pinned local ONNX file, model version, license and SHA-256; it never
downloads weights or calls a paid API. It exposes the same `/v1/proposal`
contract as the existing HTTP proposal adapters and returns provider, input
size, source hash, proposal hash and inference timing in every response.

The benchmark script runs batch-size-one measurements at 1024 and 2048. A
fixed-size export is expected to reject a different input size; a separate
2048 export is required rather than silently changing model geometry. The
4500×5400 artwork is resized inside the adapter, and the returned alpha is
resized back to source dimensions before deterministic processing.
