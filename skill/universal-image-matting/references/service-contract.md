# Service contract

The Skill adapter calls the local or tunneled service:

```text
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/artifacts
GET  /v1/artifacts/{job_id}/{name}
```

`POST /v1/jobs` is multipart with `source`, `policy_json`, optional
`manifest_json`, and optional pixel masks: `semantic_protection_mask`,
`removal_mask` and `uncertainty_mask`. Text labels without corresponding pixel
masks cannot produce an automatic `passed` result.

Canvas fields `canvas_width`, `canvas_height`, `canvas_margin` and `canvas_dpi`
may be supplied in policy for 4200x4800, 4500x5400 or custom transparent
canvases. The response is `202` with `job_id` and `poll_url`.

Terminal statuses:

- `passed`: AI mask, PNG validation, Photopea processing and PSD structure
  validation all passed; artifacts can be used.
- `review_required`: download artifacts for manual mask review; do not claim automatic completion.
- `refused`: the service safely declined the candidate.
- `failed`: processing failed and must be retried or diagnosed.

The service returns PNG variants, masks, black/white/gray/navy/Blue Jean
previews, a labeled DTG-underbase approximation, editable PSD and
`report.json`. The report exposes `ai_mask_status`,
`photopea_processing_status`, `psd_validation_status`, `png_validation_status`
and `overall_status`.
