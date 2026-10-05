# Photopea Live PSD bridge

This service is the only PSD writer in the project. It does not construct PSD
bytes in Python. It opens Photopea in a browser outer environment, passes the
frozen source image, one grayscale/alpha mask carrier and a validated hash-bound
raster mask revision through the Live Messaging
API, then returns the binary result of
`app.activeDocument.saveToOE("psd:true")`.

The workflow is one Photopea document: the source is opened once, the raster
carrier is used to author linked masks, and no client-provided JavaScript or
polygon plan is accepted. For an interactive review, use the bounded session
protocol:

```text
POST /v1/photopea/sessions             source + mask + revision
  -> checkpoint_ready + session_id
POST /v1/photopea/sessions/{id}/revisions  next raster mask + parent revision
  -> checkpoint_ready
POST /v1/photopea/sessions/{id}/finalize
  -> PSD + pixel round-trip evidence
```

The revision endpoint keeps the same browser and Photopea document alive. It
rejects stale source/checkpoint/parent hashes and does not accept polygons or
arbitrary scripts. Session expiry and all Photopea calls are bounded by the
configured five-minute budget.

Photopea script errors are returned immediately. The session path uses
`PHOTOPEA_SESSION_TIMEOUT_MS` (300 seconds by default); it does not leave a
hung browser request running beyond the general five-minute export limit.

The bridge requires Node.js, npm dependencies and a Playwright Chromium
runtime. It is intentionally separate from the domain service so that
Photopea/browser concerns cannot leak into the functional image core.

If the Playwright-managed browser cannot be installed, set
`PHOTOPEA_CHROMIUM_EXECUTABLE_PATH` to a compatible Chromium binary. The PSD
still comes from Photopea Live API; no local Python PSD writer is used.
