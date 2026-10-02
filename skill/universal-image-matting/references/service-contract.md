# Service contract

The Skill adapter calls the local or tunneled service:

```text
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/artifacts
GET  /v1/artifacts/{job_id}/{name}
```

`POST /v1/jobs` is multipart with `source`, `policy_json` and optional
`manifest_json`. The response is `202` with `job_id` and `poll_url`.

Terminal statuses:

- `passed`: artifacts can be used, subject to report review.
- `review_required`: download artifacts for manual mask review; do not claim automatic completion.
- `refused`: the service safely declined the candidate.
- `failed`: processing failed and must be retried or diagnosed.

The service returns PNG variants, masks, black/white/gray/navy/Blue Jean
previews, DTG-underbase preview, editable PSD and `report.json`.
