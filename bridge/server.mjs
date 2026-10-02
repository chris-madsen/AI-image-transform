import express from "express";
import multer from "multer";
import { chromium } from "playwright";

const app = express();
const upload = multer({ limits: { fileSize: 100 * 1024 * 1024, files: 3 } });
const port = Number(process.env.PORT || 8787);
const token = process.env.PHOTOPEA_LIVE_API_TOKEN || "";

function authorized(request) {
  return !token || request.get("authorization") === `Bearer ${token}`;
}

function dataUrl(file) {
  return `data:${file.mimetype};base64,${file.buffer.toString("base64")}`;
}

function photopeaScript() {
  return `
    (function () {
      if (app.documents.length < 3 || app.activeDocument.__cleanerExported) return;
      var source = app.documents[0];
      var artwork = app.documents[1];
      var mask = app.documents[2];
      source.name = "SOURCE BACKUP";
      artwork.name = "WORKING ART";
      mask.name = "WORKING MASK";
      source.__cleanerExported = true;
      app.activeDocument = source;
      try {
        artwork.activeLayer.duplicate(source);
        mask.activeLayer.duplicate(source);
      } catch (error) {
        app.echoToOE("PHOTOPEA_LAYER_WARNING:" + error.toString());
      }
      app.echoToOE("PHOTOPEA_LAYERS_READY");
      source.saveToOE("psd:true");
    })();
  `;
}

async function exportViaPhotopea(files) {
  const launchOptions = { headless: true };
  if (process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH;
  }
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage();
    const result = await new Promise(async (resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("photopea export timed out")), 180_000);
      await page.exposeFunction("receivePhotopeaBinary", (values) => {
        clearTimeout(timer);
        resolve(Buffer.from(values));
      });
      await page.setContent(`
        <!doctype html><html><body>
          <iframe id="photopea" style="width:1px;height:1px;border:0"
            src="${"https://www.photopea.com/#" + encodeURIComponent(JSON.stringify({
              files: files.map(dataUrl),
              script: photopeaScript(),
            }))}"></iframe>
          <script>
            const frame = document.getElementById('photopea');
            window.addEventListener('message', (event) => {
              if (event.source !== frame.contentWindow) return;
              if (event.data instanceof ArrayBuffer) {
                window.receivePhotopeaBinary(Array.from(new Uint8Array(event.data)));
              }
            });
          </script>
        </body></html>
      `);
    });
    if (!result.subarray(0, 4).equals(Buffer.from("8BPS"))) {
      throw new Error("Photopea returned a non-PSD payload");
    }
    return result;
  } finally {
    await browser.close();
  }
}

app.get("/healthz", (_request, response) => response.json({ status: "ok", provider: "photopea-live" }));

app.post("/v1/photopea/export", upload.fields([
  { name: "source", maxCount: 1 },
  { name: "artwork", maxCount: 1 },
  { name: "mask", maxCount: 1 },
]), async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const files = ["source", "artwork", "mask"].map((name) => request.files?.[name]?.[0]).filter(Boolean);
  if (files.length !== 3) return response.status(400).json({ code: "missing_photopea_inputs" });
  try {
    const psd = await exportViaPhotopea(files);
    response.type("application/vnd.adobe.photoshop").send(psd);
  } catch (error) {
    response.status(502).json({ code: "photopea_export_failed", message: String(error) });
  }
});

app.listen(port, "127.0.0.1", () => console.log(JSON.stringify({ event_type: "PhotopeaLiveApiStarted", port })));
