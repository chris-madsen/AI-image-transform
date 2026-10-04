import express from "express";
import multer from "multer";
import { chromium } from "playwright";

const app = express();
const upload = multer({ limits: { fileSize: 100 * 1024 * 1024, files: 7 } });
const port = Number(process.env.PORT || 8787);
const token = process.env.PHOTOPEA_LIVE_API_TOKEN || "";
const skipRoundTrip = process.env.PHOTOPEA_SKIP_ROUNDTRIP === "1";

function authorized(request) {
  return !token || request.get("authorization") === `Bearer ${token}`;
}

function photopeaScript(hasVariants) {
  const variantDocuments = hasVariants ? `
      var artisticDocument = app.documents[3];
      var artisticMaskDocument = app.documents[4];
      var conservativeDocument = app.documents[5];
      var conservativeMaskDocument = app.documents[6];
    ` : "";
  return `
    (function () {
      function cTID(value) {
        return charIDToTypeID(value);
      }
      function copyLayer(from, to, name) {
        app.echoToOE("COPY_START:" + name);
        app.activeDocument = from;
        from.selection.selectAll();
        from.selection.copy();
        app.activeDocument = to;
        var previousLayer = to.activeLayer;
        to.paste();
        // Photopea inserts the pasted layer as the active layer. It is not
        // guaranteed to be layers[0]; renaming layers[0] used to rename an
        // unrelated layer and leave the pasted image as a visible "Layer 1".
        var pastedLayer = to.activeLayer;
        if (!pastedLayer || pastedLayer === previousLayer) {
          throw new Error("paste did not create an active layer: " + name);
        }
        pastedLayer.name = name;
        if (pastedLayer.name !== name) {
          throw new Error("pasted layer rename failed: " + name);
        }
        app.echoToOE("COPY_DONE:" + name);
        return pastedLayer;
      }
      function loadActiveLayerTransparencyAsSelection() {
        var descriptor = new ActionDescriptor();
        var selectionReference = new ActionReference();
        selectionReference.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), selectionReference);
        var transparencyReference = new ActionReference();
        transparencyReference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Trsp"));
        descriptor.putReference(cTID("T   "), transparencyReference);
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function addRasterMaskFromSelection() {
        app.echoToOE("MASK_START");
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        descriptor.putClass(cTID("Nw  "), cTID("Chnl"));
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("At  "), reference);
        descriptor.putEnumerated(cTID("Usng"), cTID("UsrM"), cTID("RvlS"));
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
        app.echoToOE("MASK_CREATED");
      }
      function selectRasterMaskChannel() {
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("null"), reference);
        descriptor.putBoolean(cTID("MkVs"), false);
        executeAction(cTID("slct"), descriptor, DialogModes.NO);
      }
      function selectRgbChannel() {
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("RGB "));
        descriptor.putReference(cTID("null"), reference);
        descriptor.putBoolean(cTID("MkVs"), false);
        executeAction(cTID("slct"), descriptor, DialogModes.NO);
      }
      function addMaskedLayer(artDocument, maskDocument, name, visible) {
        var artworkLayer = copyLayer(artDocument, sourceDocument, name);
        var maskLayer = copyLayer(maskDocument, sourceDocument, name + " MASK");
        sourceDocument.activeLayer = maskLayer;
        loadActiveLayerTransparencyAsSelection();
        sourceDocument.activeLayer = artworkLayer;
        addRasterMaskFromSelection();
        sourceDocument.selection.deselect();
        maskLayer.visible = false;
        artworkLayer.visible = visible;
        selectRgbChannel();
        return artworkLayer;
      }
      function addColorLayer(document, name, red, green, blue) {
        app.echoToOE("FILL_START:" + name);
        app.activeDocument = document;
        var layer = document.artLayers.add();
        layer.name = name;
        document.currentLayer = layer;
        var color = new SolidColor();
        color.rgb.red = red;
        color.rgb.green = green;
        color.rgb.blue = blue;
        app.foregroundColor = color;
        document.selection.selectAll();
        document.selection.fill(app.foregroundColor);
        document.selection.deselect();
        layer.visible = false;
        app.echoToOE("FILL_DONE:" + name);
        return layer;
      }
      function hideAllLayers(document) {
        for (var index = 0; index < document.layers.length; index += 1) {
          document.layers[index].visible = false;
        }
      }
      var sourceDocument = app.documents[0];
      var artworkDocument = app.documents[1];
      var maskDocument = app.documents[2];
      ${variantDocuments}
      sourceDocument.name = "ARTWORK CLEANUP";
      app.echoToOE("DOCS_READY");
      app.activeDocument = sourceDocument;
      app.echoToOE("LAYER_COUNTS:" + sourceDocument.layers.length + ":" + sourceDocument.artLayers.length);
      var sourceLayer = sourceDocument.artLayers[0];
      app.echoToOE("SOURCE_LAYER_READY:" + (sourceLayer ? "yes" : "no"));
      sourceLayer.name = "SOURCE BACKUP";
      sourceLayer.visible = false;
      app.echoToOE("SOURCE_LAYER_NAMED");
      addColorLayer(sourceDocument, "BLACK (COLOR FILL)", 0, 0, 0);
      addColorLayer(sourceDocument, "WHITE (COLOR FILL)", 255, 255, 255);
      addColorLayer(sourceDocument, "GRAY (COLOR FILL)", 119, 119, 119);
      addColorLayer(sourceDocument, "NAVY (COLOR FILL)", 54, 75, 99);
      addColorLayer(sourceDocument, "BLUE JEAN (COLOR FILL)", 110, 142, 174);
      ${hasVariants ? `
      var restored = addMaskedLayer(artworkDocument, maskDocument, "RESTORED", true);
      var withGaps = addMaskedLayer(conservativeDocument, conservativeMaskDocument, "WITH GAPS", false);
      var workingMask = copyLayer(maskDocument, sourceDocument, "WORKING MASK");
      workingMask.visible = false;
      hideAllLayers(sourceDocument);
      restored.visible = true;
      sourceDocument.activeLayer = restored;
      selectRasterMaskChannel();
      app.echoToOE("PHOTOPEA_MASK_VERIFIED");
      selectRgbChannel();
      ` : `
      // Fast/diagnostic input contains one candidate. Duplicate the already
      // masked RESTORED layer instead of uploading another full-resolution
      // candidate. Production jobs send both candidates and use the branch
      // above; this path exists to keep the five-minute PSD smoke path bounded.
      var restored = addMaskedLayer(artworkDocument, maskDocument, "RESTORED", true);
      var withGaps = restored.duplicate();
      withGaps.name = "WITH GAPS";
      withGaps.visible = false;
      var workingMask = copyLayer(maskDocument, sourceDocument, "WORKING MASK");
      workingMask.visible = false;
      app.activeDocument = sourceDocument;
      sourceDocument.activeLayer = restored;
      selectRasterMaskChannel();
      app.echoToOE("PHOTOPEA_MASK_VERIFIED");
      selectRgbChannel();
      `}
      // A transparent document must open with artwork visible and every
      // diagnostic fill/carrier hidden. No accidental pasted layer may remain
      // visible, otherwise Photopea displays a black/opaque canvas.
      hideAllLayers(sourceDocument);
      restored.visible = true; sourceDocument.activeLayer = restored;
      selectRgbChannel();
      app.activeDocument = sourceDocument;
      app.echoToOE("PHOTOPEA_STRUCTURE_BUILT");
      sourceDocument.saveToOE("psd:true");
    })();
  `;
}

function photopeaMaskSessionScript(plan) {
  return `
    (function () {
      var plan = ${JSON.stringify(plan)};
      function cTID(value) { return charIDToTypeID(value); }
      function sTID(value) { return stringIDToTypeID(value); }
      function duplicateLayer(document, layer, name) {
        document.activeLayer = layer;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putEnumerated(cTID("Lyr "), cTID("Ordn"), cTID("Trgt"));
        descriptor.putReference(cTID("null"), reference);
        executeAction(cTID("Dplc"), descriptor, DialogModes.NO);
        var duplicate = document.activeLayer;
        duplicate.name = name;
        return duplicate;
      }
      function selectPolygon(document, polygon, mode) {
        var action = mode === "subtract" ? sTID("subtractFrom") : (mode === "add" ? sTID("addTo") : sTID("set"));
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putProperty(sTID("channel"), sTID("selection"));
        descriptor.putReference(sTID("null"), reference);
        var polygonDescriptor = new ActionDescriptor();
        var points = new ActionList();
        for (var pointIndex = 0; pointIndex <= polygon.length; pointIndex += 1) {
          var point = polygon[pointIndex % polygon.length];
          var pointDescriptor = new ActionDescriptor();
          pointDescriptor.putUnitDouble(sTID("horizontal"), sTID("pixelsUnit"), point[0] * Number(document.width.value || document.width));
          pointDescriptor.putUnitDouble(sTID("vertical"), sTID("pixelsUnit"), point[1] * Number(document.height.value || document.height));
          points.putObject(sTID("paint"), pointDescriptor);
        }
        polygonDescriptor.putList(sTID("points"), points);
        descriptor.putObject(sTID("to"), sTID("polygon"), polygonDescriptor);
        descriptor.putBoolean(sTID("antiAlias"), true);
        executeAction(action, descriptor, DialogModes.NO);
      }
      function deselect(document) {
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), reference);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("None"));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function selectAll(document) {
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), reference);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("Al  "));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function fillForeground(document) {
        var descriptor = new ActionDescriptor();
        descriptor.putEnumerated(sTID("using"), sTID("fillContents"), sTID("foregroundColor"));
        descriptor.putUnitDouble(sTID("opacity"), sTID("percentUnit"), 100);
        descriptor.putEnumerated(sTID("mode"), sTID("blendMode"), sTID("normal"));
        executeAction(sTID("fill"), descriptor, DialogModes.NO);
      }
      function selectPlan(document, includeRemovals) {
        var first = true;
        for (var subjectIndex = 0; subjectIndex < plan.subject_polygons.length; subjectIndex += 1) {
          var polygon = plan.subject_polygons[subjectIndex];
          selectPolygon(document, polygon, first ? "replace" : "add");
          first = false;
        }
        if (includeRemovals) {
          for (var removeIndex = 0; removeIndex < plan.remove_polygons.length; removeIndex += 1) {
            var polygon = plan.remove_polygons[removeIndex];
            selectPolygon(document, polygon, "subtract");
          }
        }
        for (var protectIndex = 0; protectIndex < plan.protect_polygons.length; protectIndex += 1) {
          var polygon = plan.protect_polygons[protectIndex];
          selectPolygon(document, polygon, "add");
        }
        if (plan.feather_px > 0) {
          var featherDescriptor = new ActionDescriptor();
          featherDescriptor.putUnitDouble(cTID("Rds "), cTID("#Pxl"), plan.feather_px);
          executeAction(cTID("Fthr"), featherDescriptor, DialogModes.NO);
        }
      }
      function addRasterMaskFromSelection(document, layer) {
        document.activeLayer = layer;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        descriptor.putClass(cTID("Nw  "), cTID("Chnl"));
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("At  "), reference);
        descriptor.putEnumerated(cTID("Usng"), cTID("UsrM"), cTID("RvlS"));
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
      }
      function fillLayer(document, name, red, green, blue) {
        var layer = document.artLayers.add();
        layer.name = name;
        document.activeLayer = layer;
        var color = new SolidColor();
        color.rgb.red = red; color.rgb.green = green; color.rgb.blue = blue;
        app.foregroundColor = color;
        selectAll(document);
        fillForeground(document);
        deselect(document);
        layer.visible = false;
        return layer;
      }
      function hideAll(document) {
        for (var index = 0; index < document.layers.length; index += 1) {
          document.layers[index].visible = false;
        }
      }
      try {
      var document = app.documents[0];
      document.name = "ARTWORK CLEANUP";
      var source = document.artLayers[0];
      if (!source) throw new Error("source layer is missing");
      source.name = "SOURCE BACKUP";
      source.visible = false;
      var restored = duplicateLayer(document, source, "RESTORED");
      restored.visible = true;
      selectPlan(document, false);
      addRasterMaskFromSelection(document, restored);
      deselect(document);
      var withGaps = duplicateLayer(document, source, "WITH GAPS");
      withGaps.visible = false;
      selectPlan(document, true);
      addRasterMaskFromSelection(document, withGaps);
      deselect(document);
      var workingMask = document.artLayers.add();
      workingMask.name = "WORKING MASK";
      document.activeLayer = workingMask;
      var black = new SolidColor();
      black.rgb.red = 0; black.rgb.green = 0; black.rgb.blue = 0;
      app.foregroundColor = black;
      selectAll(document);
      fillForeground(document);
      deselect(document);
      selectPlan(document, true);
      var white = new SolidColor();
      white.rgb.red = 255; white.rgb.green = 255; white.rgb.blue = 255;
      app.foregroundColor = white;
      fillForeground(document);
      deselect(document);
      workingMask.visible = false;
      fillLayer(document, "BLACK (COLOR FILL)", 0, 0, 0);
      fillLayer(document, "WHITE (COLOR FILL)", 255, 255, 255);
      fillLayer(document, "GRAY (COLOR FILL)", 119, 119, 119);
      fillLayer(document, "NAVY (COLOR FILL)", 54, 75, 99);
      fillLayer(document, "BLUE JEAN (COLOR FILL)", 110, 142, 174);
      hideAll(document);
      restored.visible = true;
      document.activeLayer = restored;
      app.echoToOE("PHOTOPEA_MASK_VERIFIED:" + plan.revision_id);
      app.echoToOE("PHOTOPEA_STRUCTURE_BUILT");
      document.clearHistory();
      document.saveToOE("psd:true");
      } catch (error) {
        app.echoToOE("PHOTOPEA_STRUCTURE_FAILED:session:" + String(error));
      }
    })();
  `;
}

function photopeaRoundTripScript(hasVariants) {
  const variantChecks = hasVariants ? `
        var restored = findLayer("RESTORED");
        var withGaps = findLayer("WITH GAPS");
        if (!restored || !withGaps) throw new Error("missing RESTORED/WITH GAPS layers");
        document.activeLayer = restored;
        selectRasterMaskChannel();
        document.activeLayer = withGaps;
        selectRasterMaskChannel();
      ` : "";
  return `
    (function () {
      function cTID(value) {
        return charIDToTypeID(value);
      }
      function selectRasterMaskChannel() {
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("null"), reference);
        descriptor.putBoolean(cTID("MkVs"), false);
        executeAction(cTID("slct"), descriptor, DialogModes.NO);
      }
      try {
        app.echoToOE("PHOTOPEA_ROUNDTRIP_START");
        var document = app.activeDocument;
        function findLayer(name) {
          for (var index = 0; index < document.layers.length; index += 1) {
            if (document.layers[index].name === name) return document.layers[index];
          }
          return null;
        }
        var artwork = findLayer("RESTORED");
        var mask = findLayer("WORKING MASK");
        var fills = [
          "BLACK (COLOR FILL)",
          "WHITE (COLOR FILL)",
          "GRAY (COLOR FILL)",
          "NAVY (COLOR FILL)",
          "BLUE JEAN (COLOR FILL)"
        ];
        for (var fillIndex = 0; fillIndex < fills.length; fillIndex += 1) {
          var fill = findLayer(fills[fillIndex]);
          if (!fill) throw new Error("missing fill layer: " + fills[fillIndex]);
        }
        var withGaps = findLayer("WITH GAPS");
        if (!artwork || !withGaps || !mask) throw new Error("missing RESTORED/WITH GAPS/WORKING MASK layers");
        app.activeDocument = document;
        document.activeLayer = artwork;
        selectRasterMaskChannel();
        document.activeLayer = withGaps;
        selectRasterMaskChannel();
        ${variantChecks}
        app.echoToOE("PHOTOPEA_ROUNDTRIP_VERIFIED");
      } catch (error) {
        app.echoToOE("PHOTOPEA_STRUCTURE_FAILED:roundtrip:" + String(error));
      }
    })();
  `;
}

async function exportViaPhotopea(files, options = {}) {
  const launchOptions = { headless: true };
  if (process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH;
  }
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage();
    let scriptStarted = false;
    let rejectExport = null;
    page.on("console", (message) => console.log(JSON.stringify({ event_type: "PhotopeaConsole", type: message.type(), text: message.text() })));
    page.on("pageerror", (error) => {
      const message = String(error);
      console.log(JSON.stringify({ event_type: "PhotopeaPageError", message }));
      if (scriptStarted && rejectExport) rejectExport(new Error(`Photopea script failed: ${message}`));
    });
    page.on("requestfailed", (request) => console.log(JSON.stringify({ event_type: "PhotopeaRequestFailed", url: request.url(), error: request.failure()?.errorText })));
    const result = await new Promise(async (resolve, reject) => {
      rejectExport = reject;
      const exportTimeoutMs = Number(options.timeoutMs || process.env.PHOTOPEA_EXPORT_TIMEOUT_MS || 300_000);
      const timer = setTimeout(() => reject(new Error("photopea export timed out")), exportTimeoutMs);
      let structureBuilt = false;
      let maskVerified = false;
      let roundTripStarted = false;
      let returnedPayload = null;
      let binaryBuffer = null;
      let binaryOffset = 0;
      await page.exposeFunction("notePhotopeaScriptStarted", () => { scriptStarted = true; });
      await page.exposeFunction("getPhotopeaFile", (index) => Array.from(files[index].buffer));
      await page.exposeFunction("notePhotopeaStructureBuilt", () => { structureBuilt = true; });
      await page.exposeFunction("notePhotopeaMaskVerified", () => { maskVerified = true; });
      await page.exposeFunction("beginPhotopeaBinary", (length) => {
        binaryBuffer = Buffer.alloc(Number(length));
        binaryOffset = 0;
      });
      await page.exposeFunction("receivePhotopeaBinaryChunk", (values) => {
        const chunk = Buffer.from(values);
        if (!binaryBuffer || binaryOffset + chunk.length > binaryBuffer.length) {
          throw new Error("Photopea binary chunk exceeds declared payload length");
        }
        chunk.copy(binaryBuffer, binaryOffset);
        binaryOffset += chunk.length;
      });
      await page.exposeFunction("finishPhotopeaBinary", async () => {
        if (!binaryBuffer || binaryOffset !== binaryBuffer.length) {
          throw new Error("Photopea binary payload is incomplete");
        }
        const payload = binaryBuffer;
        if (!structureBuilt || !maskVerified) {
          clearTimeout(timer);
          reject(new Error("Photopea returned PSD before structure verification"));
          return;
        }
        if (roundTripStarted) {
          clearTimeout(timer);
          reject(new Error("Photopea returned an unexpected second binary payload"));
          return;
        }
        roundTripStarted = true;
        returnedPayload = payload;
        if (skipRoundTrip) {
          clearTimeout(timer);
          resolve(returnedPayload);
          return;
        }
        await page.evaluate((roundTripLength) => window.startPhotopeaRoundTrip(roundTripLength), payload.length);
      });
      await page.exposeFunction("getPhotopeaRoundTripChunk", (offset, length) => Array.from(returnedPayload.subarray(Number(offset), Number(offset) + Number(length))));
      await page.exposeFunction("receivePhotopeaVerified", () => {
        clearTimeout(timer);
        resolve(returnedPayload);
      });
      await page.exposeFunction("receivePhotopeaFailure", (message) => {
        clearTimeout(timer);
        reject(new Error(message));
      });
      // Photopea needs a real same-origin outer environment. Using about:blank
      // makes its localStorage access fail before it can emit the ready event.
      await page.goto(`http://127.0.0.1:${port}/healthz`);
      await page.setContent(`
        <!doctype html><html><body>
          <iframe id="photopea" style="width:1px;height:1px;border:0"
            src="https://www.photopea.com/#${encodeURIComponent(JSON.stringify({}))}"></iframe>
          <script>
            const frame = document.getElementById('photopea');
            let phase = 'boot';
            let fileIndex = 0;
            async function sendFile(index) {
              const values = await window.getPhotopeaFile(index);
              const buffer = new Uint8Array(values).buffer;
              frame.contentWindow.postMessage(buffer, '*', [buffer]);
            }
            window.addEventListener('message', async (event) => {
              if (event.source !== frame.contentWindow) return;
              if (typeof event.data === 'string') {
                console.log('PHOTOPEA_MESSAGE:' + event.data);
                if (event.data.indexOf('PHOTOPEA_STRUCTURE_FAILED:') === 0) {
                  window.receivePhotopeaFailure(event.data);
                  return;
                }
                if (event.data === 'PHOTOPEA_STRUCTURE_BUILT') window.notePhotopeaStructureBuilt();
                if (event.data.indexOf('PHOTOPEA_MASK_VERIFIED') === 0) window.notePhotopeaMaskVerified();
                if (event.data === 'PHOTOPEA_ROUNDTRIP_VERIFIED') {
                  window.receivePhotopeaVerified();
                  return;
                }
              }
              if (event.data instanceof ArrayBuffer) {
                const chunkSize = 4 * 1024 * 1024;
                window.beginPhotopeaBinary(event.data.byteLength);
                for (let offset = 0; offset < event.data.byteLength; offset += chunkSize) {
                  const length = Math.min(chunkSize, event.data.byteLength - offset);
                  await window.receivePhotopeaBinaryChunk(Array.from(new Uint8Array(event.data, offset, length)));
                }
                await window.finishPhotopeaBinary();
                return;
              }
              if (event.data !== 'done') return;
              if (phase === 'boot') {
                phase = 'files';
                sendFile(fileIndex);
              } else if (phase === 'files' && fileIndex < ${files.length - 1}) {
                fileIndex += 1;
                sendFile(fileIndex);
              } else if (phase === 'files') {
                phase = 'script';
                await window.notePhotopeaScriptStarted();
                frame.contentWindow.postMessage(${JSON.stringify(options.script || photopeaScript(files.length >= 7))}, '*');
              } else if (phase === 'roundtrip-file') {
                phase = 'roundtrip-script';
                frame.contentWindow.postMessage(${JSON.stringify(photopeaRoundTripScript(files.length >= 7))}, '*');
              }
            });
            window.startPhotopeaRoundTrip = async function (length) {
              const values = new Uint8Array(length);
              const chunkSize = 4 * 1024 * 1024;
              for (let offset = 0; offset < length; offset += chunkSize) {
                const chunk = await window.getPhotopeaRoundTripChunk(offset, Math.min(chunkSize, length - offset));
                values.set(chunk, offset);
              }
              const buffer = values.buffer;
              phase = 'roundtrip-file';
              frame.contentWindow.postMessage(buffer, '*', [buffer]);
            };
          </script>
        </body></html>
      `, { waitUntil: "domcontentloaded", timeout: 120_000 });
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
  { name: "variant_artistic", maxCount: 1 },
  { name: "mask_artistic", maxCount: 1 },
  { name: "variant_conservative", maxCount: 1 },
  { name: "mask_conservative", maxCount: 1 },
]), async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const names = ["source", "artwork", "mask", "variant_artistic", "mask_artistic", "variant_conservative", "mask_conservative"];
  const files = names.map((name) => request.files?.[name]?.[0]).filter(Boolean);
  const rawMaskPlan = request.body?.mask_plan;
  let maskPlan = null;
  if (rawMaskPlan) {
    try {
      maskPlan = JSON.parse(rawMaskPlan);
      const polygons = ["subject_polygons", "remove_polygons", "protect_polygons"];
      if (!maskPlan || typeof maskPlan !== "object" || typeof maskPlan.revision_id !== "string" || !Array.isArray(maskPlan.subject_polygons) || !maskPlan.subject_polygons.length) throw new Error("invalid mask plan");
      polygons.forEach((name) => {
        if (!Array.isArray(maskPlan[name]) || maskPlan[name].length > 128) throw new Error("invalid " + name);
        maskPlan[name].forEach((polygon) => {
          if (!Array.isArray(polygon) || polygon.length < 3 || polygon.length > 4096) throw new Error("invalid polygon");
          polygon.forEach((point) => {
            if (!Array.isArray(point) || point.length !== 2 || point.some((value) => typeof value !== "number" || value < 0 || value > 1)) throw new Error("invalid point");
          });
        });
      });
      if (!Number.isInteger(maskPlan.feather_px) || maskPlan.feather_px < 0 || maskPlan.feather_px > 256) throw new Error("invalid feather_px");
    } catch (error) {
      return response.status(400).json({ code: "invalid_photopea_mask_plan", message: String(error) });
    }
  }
  const hasVariants = names.slice(3).every((name) => request.files?.[name]?.[0]);
  if ((maskPlan && files.length !== 1) || (!maskPlan && files.length !== 3 && !hasVariants)) return response.status(400).json({ code: "missing_photopea_inputs" });
  try {
    const psd = await exportViaPhotopea(files, maskPlan ? {
      script: photopeaMaskSessionScript(maskPlan),
      timeoutMs: Number(process.env.PHOTOPEA_SESSION_TIMEOUT_MS || 120_000),
    } : {});
    response.set("X-Photopea-Roundtrip", skipRoundTrip ? "structure-built" : "verified");
    response.type("application/vnd.adobe.photoshop").send(psd);
  } catch (error) {
    response.status(502).json({ code: "photopea_export_failed", message: String(error) });
  }
});

app.listen(port, "127.0.0.1", () => console.log(JSON.stringify({ event_type: "PhotopeaLiveApiStarted", port })));
