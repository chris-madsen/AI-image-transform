# Photopea Live PSD bridge

This service is the only PSD writer in the project. It does not construct PSD
bytes in Python. It opens Photopea in a browser outer environment, passes the
frozen source image and a validated typed mask plan through the Live Messaging
API, then returns the binary result of
`app.activeDocument.saveToOE("psd:true")`.

The primary workflow is one Photopea document: the source is opened once,
layers and masks are authored in that document, and the plan is never accepted
as arbitrary JavaScript. The old multi-PNG endpoint remains only as a legacy
compatibility path and is not the domain workflow.

Photopea script errors are returned immediately. The session path uses
`PHOTOPEA_SESSION_TIMEOUT_MS` (120 seconds by default); it does not leave a
hung browser request running for the general five-minute export limit.

The bridge requires Node.js, npm dependencies and a Playwright Chromium
runtime. It is intentionally separate from the domain service so that
Photopea/browser concerns cannot leak into the functional image core.

If the Playwright-managed browser cannot be installed, set
`PHOTOPEA_CHROMIUM_EXECUTABLE_PATH` to a compatible Chromium binary. The PSD
still comes from Photopea Live API; no local Python PSD writer is used.
