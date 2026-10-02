# Photopea Live PSD bridge

This service is the only PSD writer in the project. It does not construct PSD
bytes in Python. It opens Photopea in a browser outer environment, passes the
three candidate PNGs and a JavaScript layer-building script through the Live
Messaging API, then returns the binary result of
`app.activeDocument.saveToOE("psd:true")`.

The bridge requires Node.js, npm dependencies and a Playwright Chromium
runtime. It is intentionally separate from the domain service so that
Photopea/browser concerns cannot leak into the functional image core.

If the Playwright-managed browser cannot be installed, set
`PHOTOPEA_CHROMIUM_EXECUTABLE_PATH` to a compatible Chromium binary. The PSD
still comes from Photopea Live API; no local Python PSD writer is used.
