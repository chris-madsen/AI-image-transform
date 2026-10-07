import crypto from "node:crypto";
import express from "express";
import multer from "multer";
import { inflateSync } from "node:zlib";
import { chromium } from "playwright";

const app = express();
const upload = multer({ limits: { fileSize: 100 * 1024 * 1024, files: 3 } });
const port = Number(process.env.PORT || 8787);
const token = process.env.PHOTOPEA_LIVE_API_TOKEN || "";
const reviewSecret = process.env.PHOTOPEA_REVIEW_SECRET || "";
const transferStore = new Map();
const photopeaSessions = new Map();

function authorized(request) {
  return !token || request.get("authorization") === `Bearer ${token}`;
}

function transfer(buffer, ttlMs = 10 * 60 * 1000) {
  const id = crypto.randomUUID();
  transferStore.set(id, Buffer.from(buffer));
  setTimeout(() => transferStore.delete(id), ttlMs).unref();
  return id;
}

function acceptanceToken(revision) {
  if (!reviewSecret) throw new Error("PHOTOPEA_REVIEW_SECRET is required");
  const message = [revision.source_sha256, revision.revision_id, revision.checkpoint_sha256].join("|");
  return crypto.createHmac("sha256", reviewSecret).update(message).digest("hex");
}

function validAcceptanceToken(revision, value) {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value) || !reviewSecret) return false;
  const expected = acceptanceToken(revision);
  return crypto.timingSafeEqual(Buffer.from(expected, "hex"), Buffer.from(value, "hex"));
}


// Photopea's scripting runtime is Photoshop-compatible ES5. This script is
// intentionally conservative: no DOM selection API, no polygons and no
// client-provided JavaScript cross the bridge boundary.
function photopeaRasterMaskScript({ finalize = true } = {}) {
  return `
    (function () {
      function cTID(value) { return charIDToTypeID(value); }
      function sTID(value) { return stringIDToTypeID(value); }
      function message(value) { app.echoToOE(value); }
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
      function copyLayer(fromDocument, toDocument, name, layer) {
        app.activeDocument = fromDocument;
        fromDocument.activeLayer = layer || fromDocument.artLayers[0];
        fromDocument.selection.selectAll();
        fromDocument.selection.copy();
        app.activeDocument = toDocument;
        toDocument.paste();
        var pasted = toDocument.activeLayer;
        pasted.name = name;
        return pasted;
      }
      function selectAll(document) {
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("Al  "));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function deselect(document) {
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("None"));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function fillColor(document, red, green, blue) {
        var color = new SolidColor();
        color.rgb.red = red; color.rgb.green = green; color.rgb.blue = blue;
        app.foregroundColor = color;
        var descriptor = new ActionDescriptor();
        descriptor.putEnumerated(sTID("using"), sTID("fillContents"), sTID("foregroundColor"));
        descriptor.putUnitDouble(sTID("opacity"), sTID("percentUnit"), 100);
        descriptor.putEnumerated(sTID("mode"), sTID("blendMode"), sTID("normal"));
        executeAction(sTID("fill"), descriptor, DialogModes.NO);
      }
      function addLinkedRasterMask(document, artwork) {
        app.activeDocument = document;
        document.activeLayer = artwork;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        descriptor.putClass(cTID("Nw  "), cTID("Chnl"));
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("At  "), reference);
        descriptor.putEnumerated(cTID("Usng"), cTID("UsrM"), cTID("RvlS"));
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
      }
      function selectLayerLuminance(document, layer) {
        // The carrier is opaque grayscale. With only that layer visible, the
        // document red channel is an exact grayscale selection, including
        // partial values; unlike clipboard-pasting into a mask channel this
        // path is supported by Photopea's Action Manager.
        app.activeDocument = document;
        hideAll(document);
        layer.visible = true;
        document.activeLayer = layer;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        var channel = new ActionReference();
        channel.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Rd  "));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putReference(cTID("T   "), channel);
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function applyRasterMaskFromPixels(document, maskSource, artwork) {
        selectLayerLuminance(document, maskSource);
        addLinkedRasterMask(document, artwork);
        deselect(document);
        maskSource.visible = false;
      }
      function addSolidColorFill(document, name, red, green, blue) {
        // Content layers are editable Solid Color Fill layers, not full-canvas
        // raster layers. If Photopea rejects this descriptor we fail the job;
        // there is no misleading raster fallback.
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putClass(sTID("contentLayer"));
        descriptor.putReference(cTID("null"), reference);
        var content = new ActionDescriptor();
        var solid = new ActionDescriptor();
        var color = new ActionDescriptor();
        color.putDouble(cTID("Rd  "), red);
        color.putDouble(cTID("Grn "), green);
        color.putDouble(cTID("Bl  "), blue);
        solid.putObject(cTID("Clr "), cTID("RGBC"), color);
        content.putObject(cTID("Type"), sTID("solidColorLayer"), solid);
        descriptor.putObject(cTID("Usng"), sTID("contentLayer"), content);
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
        var layer = document.activeLayer;
        layer.name = name;
        layer.visible = false;
        return layer;
      }
      function hideAll(document) {
        app.activeDocument = document;
        for (var index = 0; index < document.layers.length; index += 1) {
          document.layers[index].visible = false;
        }
      }
      function exportPng(document, label) {
        app.activeDocument = document;
        message("PHOTOPEA_EXPORT:" + label);
        document.saveToOE("png");
      }
      function exportLayerView(document, restored, layer, label) {
        hideAll(document);
        layer.visible = true;
        if (restored) restored.visible = true;
        exportPng(document, label);
      }
      function exportMaskView(document, maskLayer, label) {
        hideAll(document);
        maskLayer.visible = true;
        document.activeLayer = maskLayer;
        exportPng(document, label);
      }
      function build() {
        var document = app.documents[0];
        var carrierDocument = app.documents[1];
        var gapsCarrierDocument = app.documents[2];
        if (!document || !carrierDocument || !gapsCarrierDocument) throw new Error("source and two mask carrier documents are required");
        var originalSource = document.artLayers[0];
        var carrier = carrierDocument.artLayers[0];
        if (!originalSource || !carrier) throw new Error("source or mask carrier layer is missing");
        var source = copyLayer(document, document, "SOURCE BACKUP");
        source.visible = false;
        originalSource.visible = false;
        var maskCarrier = copyLayer(carrierDocument, document, "MASK CARRIER", carrier);
        maskCarrier.name = "WORKING MASK";
        maskCarrier.visible = false;
        var gapsCarrier = copyLayer(gapsCarrierDocument, document, "GAPS MASK CARRIER", gapsCarrierDocument.artLayers[0]);
        gapsCarrier.name = "GAPS MASK";
        gapsCarrier.visible = false;
        carrierDocument.close(SaveOptions.DONOTSAVECHANGES);
        gapsCarrierDocument.close(SaveOptions.DONOTSAVECHANGES);
        var restored = duplicateLayer(document, source, "RESTORED");
        applyRasterMaskFromPixels(document, maskCarrier, restored);
        var withGaps = duplicateLayer(document, source, "WITH GAPS");
        applyRasterMaskFromPixels(document, gapsCarrier, withGaps);
        var maskBase = document.artLayers.add();
        maskBase.name = "WORKING MASK BASE";
        maskBase.visible = false;
        selectAll(document); fillColor(document, 0, 0, 0); deselect(document);
        var fills = [
          addSolidColorFill(document, "BLACK (COLOR FILL)", 0, 0, 0),
          addSolidColorFill(document, "NAVY (COLOR FILL)", 54, 75, 99),
          addSolidColorFill(document, "BLUE JEAN (COLOR FILL)", 110, 142, 174)
        ];
        fills[0].move(restored, ElementPlacement.PLACEAFTER);
        fills[1].move(restored, ElementPlacement.PLACEAFTER);
        fills[2].move(restored, ElementPlacement.PLACEAFTER);
        hideAll(document);
        restored.visible = true;
        hideAll(document);
        restored.visible = true;
        document.activeLayer = restored;
        document.name = "SOURCE INPUT";
        message("PHOTOPEA_STRUCTURE_BUILT");
        message("PHOTOPEA_MASK_VERIFIED");
        if (${finalize ? "true" : "false"}) {
          document.clearHistory();
          message("PHOTOPEA_EXPORT:psd");
          document.saveToOE("psd:true");
        }
      }
      try { build(); } catch (error) { message("PHOTOPEA_STRUCTURE_FAILED:" + String(error)); }
    })();
  `;
}

function photopeaRevisionScript(revisionId, { finalize = false } = {}) {
  const safeRevisionId = JSON.stringify(String(revisionId).replace(/[^a-zA-Z0-9_.-]/g, "_"));
  return `
    (function () {
      function cTID(value) { return charIDToTypeID(value); }
      function sTID(value) { return stringIDToTypeID(value); }
      function message(value) { app.echoToOE(value); }
      function findLayer(document, name) {
        var exact = null; var prefixed = null;
        for (var index = document.layers.length - 1; index >= 0; index -= 1) {
          var layerName = String(document.layers[index].name);
          if (!exact && layerName === name) exact = document.layers[index];
          var prefix = name + " ";
          var basePrefix = name + " BASE";
          if (!prefixed && layerName.slice(0, prefix.length) === prefix && layerName.slice(0, basePrefix.length) !== basePrefix) prefixed = document.layers[index];
        }
        return prefixed || exact || null;
      }
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
      function copyLayer(fromDocument, toDocument, name, layer) {
        app.activeDocument = fromDocument;
        fromDocument.activeLayer = layer || fromDocument.artLayers[0];
        fromDocument.selection.selectAll();
        fromDocument.selection.copy();
        app.activeDocument = toDocument;
        toDocument.paste();
        var pasted = toDocument.activeLayer;
        pasted.name = name;
        return pasted;
      }
      function selectAll(document) {
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("Al  "));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function deselect(document) {
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putEnumerated(cTID("T   "), cTID("Ordn"), cTID("None"));
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function fillColor(document, red, green, blue) {
        var color = new SolidColor();
        color.rgb.red = red; color.rgb.green = green; color.rgb.blue = blue;
        app.foregroundColor = color;
        var descriptor = new ActionDescriptor();
        descriptor.putEnumerated(sTID("using"), sTID("fillContents"), sTID("foregroundColor"));
        descriptor.putUnitDouble(sTID("opacity"), sTID("percentUnit"), 100);
        descriptor.putEnumerated(sTID("mode"), sTID("blendMode"), sTID("normal"));
        executeAction(sTID("fill"), descriptor, DialogModes.NO);
      }
      function addLinkedRasterMask(document, artwork) {
        app.activeDocument = document;
        document.activeLayer = artwork;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        descriptor.putClass(cTID("Nw  "), cTID("Chnl"));
        reference.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Msk "));
        descriptor.putReference(cTID("At  "), reference);
        descriptor.putEnumerated(cTID("Usng"), cTID("UsrM"), cTID("RvlS"));
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
      }
      function selectLayerLuminance(document, layer) {
        app.activeDocument = document;
        hideAll(document);
        layer.visible = true;
        document.activeLayer = layer;
        var descriptor = new ActionDescriptor();
        var selection = new ActionReference();
        selection.putProperty(cTID("Chnl"), cTID("fsel"));
        var channel = new ActionReference();
        channel.putEnumerated(cTID("Chnl"), cTID("Chnl"), cTID("Rd  "));
        descriptor.putReference(cTID("null"), selection);
        descriptor.putReference(cTID("T   "), channel);
        executeAction(cTID("setd"), descriptor, DialogModes.NO);
      }
      function applyRasterMaskFromPixels(document, maskSource, artwork) {
        selectLayerLuminance(document, maskSource);
        addLinkedRasterMask(document, artwork);
        deselect(document);
        maskSource.visible = false;
      }
      function addSolidColorFill(document, name, red, green, blue) {
        app.activeDocument = document;
        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putClass(sTID("contentLayer"));
        descriptor.putReference(cTID("null"), reference);
        var content = new ActionDescriptor();
        var solid = new ActionDescriptor();
        var color = new ActionDescriptor();
        color.putDouble(cTID("Rd  "), red); color.putDouble(cTID("Grn "), green); color.putDouble(cTID("Bl  "), blue);
        solid.putObject(cTID("Clr "), cTID("RGBC"), color);
        content.putObject(cTID("Type"), sTID("solidColorLayer"), solid);
        descriptor.putObject(cTID("Usng"), sTID("contentLayer"), content);
        executeAction(cTID("Mk  "), descriptor, DialogModes.NO);
        var layer = document.activeLayer;
        layer.name = name;
        layer.visible = false;
        return layer;
      }
      function hideAll(document) {
        app.activeDocument = document;
        for (var index = 0; index < document.layers.length; index += 1) document.layers[index].visible = false;
      }
      function exportPng(document, label) {
        app.activeDocument = document;
        message("PHOTOPEA_EXPORT:" + label);
        document.saveToOE("png");
      }
      function exportLayerView(document, restored, layer, label) {
        hideAll(document);
        layer.visible = true;
        if (restored) restored.visible = true;
        exportPng(document, label);
      }
      function exportMaskView(document, maskLayer, label) {
        hideAll(document);
        maskLayer.visible = true;
        document.activeLayer = maskLayer;
        exportPng(document, label);
      }
      function buildRevision() {
        var document = null;
        var sourceDocument = null;
        var carrierDocument = null;
        for (var documentIndex = 0; documentIndex < app.documents.length; documentIndex += 1) {
          if (String(app.documents[documentIndex].name) === "SOURCE INPUT") sourceDocument = app.documents[documentIndex];
        }
        for (var carrierIndex = 0; carrierIndex < app.documents.length; carrierIndex += 1) {
          var candidate = app.documents[carrierIndex];
          if (candidate !== sourceDocument && candidate.artLayers && candidate.artLayers.length) carrierDocument = candidate;
        }
        if (!sourceDocument || !carrierDocument) throw new Error("source and revision mask documents are required");
        var source = findLayer(sourceDocument, "SOURCE BACKUP");
        var carrier = carrierDocument.artLayers[0];
        if (!source || !carrier) throw new Error("source or revision carrier layer is missing");
        app.activeDocument = sourceDocument;
        document = sourceDocument;
        source.visible = true;
        var maskCarrier = copyLayer(carrierDocument, document, "MASK CARRIER " + ${safeRevisionId}, carrier);
        source.visible = false;
        maskCarrier.name = "WORKING MASK " + ${safeRevisionId};
        maskCarrier.visible = false;
        carrierDocument.close(SaveOptions.DONOTSAVECHANGES);
        var restored = duplicateLayer(document, source, "RESTORED " + ${safeRevisionId});
        applyRasterMaskFromPixels(document, maskCarrier, restored);
        var maskBase = document.artLayers.add();
        maskBase.name = "WORKING MASK BASE " + ${safeRevisionId}; maskBase.visible = false;
        selectAll(document); fillColor(document, 0, 0, 0); deselect(document);
        var fills = [
          addSolidColorFill(document, "BLACK (COLOR FILL) " + ${safeRevisionId}, 0, 0, 0),
          addSolidColorFill(document, "NAVY (COLOR FILL) " + ${safeRevisionId}, 54, 75, 99),
          addSolidColorFill(document, "BLUE JEAN (COLOR FILL) " + ${safeRevisionId}, 110, 142, 174)
        ];
        fills[0].move(restored, ElementPlacement.PLACEAFTER);
        fills[1].move(restored, ElementPlacement.PLACEAFTER);
        fills[2].move(restored, ElementPlacement.PLACEAFTER);
        hideAll(document); restored.visible = true;
        document.activeLayer = restored;
        message("PHOTOPEA_REVISION_BUILT");
        if (${finalize ? "true" : "false"}) { document.clearHistory(); message("PHOTOPEA_EXPORT:psd"); document.saveToOE("psd:true"); }
      }
      try { buildRevision(); } catch (error) { message("PHOTOPEA_REVISION_FAILED:" + String(error)); }
    })();
  `;
}

function photopeaSavePsdScript() {
  return `
    (function () {
      try {
        var document = app.activeDocument;
        var restored = null;
        for (var index = document.layers.length - 1; index >= 0; index -= 1) {
          var name = String(document.layers[index].name);
          if (name === "RESTORED" || name.indexOf("RESTORED ") === 0) {
            restored = document.layers[index];
            break;
          }
        }
        if (!restored) throw new Error("accepted RESTORED layer is missing");
        for (var layerIndex = 0; layerIndex < document.layers.length; layerIndex += 1) {
          document.layers[layerIndex].visible = false;
        }
        restored.visible = true;
        document.activeLayer = restored;
        app.activeDocument.clearHistory();
        app.echoToOE("PHOTOPEA_EXPORT:psd");
        document.saveToOE("psd:true");
      } catch (error) {
        app.echoToOE("PHOTOPEA_FINALIZE_FAILED:" + String(error));
      }
    })();
  `;
}

function photopeaRoundTripScript(label) {
  const safeLabel = JSON.stringify(String(label));
  return `
    (function () {
      function message(value) { app.echoToOE(value); }
      function matches(layerName, name) {
        return layerName === name || (layerName.slice(0, name.length + 1) === name + " " && layerName.slice(0, name.length + 5) !== name + " BASE");
      }
      function layerIndex(document, name) {
        for (var index = document.layers.length - 1; index >= 0; index -= 1) if (matches(String(document.layers[index].name), name)) return index;
        return -1;
      }
      function showOnly(document, visibleNames, activeName) {
        app.activeDocument = document;
        var activeIndex = layerIndex(document, activeName);
        if (activeIndex < 0) throw new Error("round-trip active layer missing: " + activeName);
        document.activeLayer = document.layers[activeIndex];
        var managedNames = ["RESTORED", "WORKING MASK", "BLACK (COLOR FILL)", "NAVY (COLOR FILL)", "BLUE JEAN (COLOR FILL)"];
        for (var managedIndex = 0; managedIndex < managedNames.length; managedIndex += 1) {
          var managedLayerIndex = layerIndex(document, managedNames[managedIndex]);
          if (managedLayerIndex >= 0 && managedLayerIndex !== activeIndex) document.layers[managedLayerIndex].visible = false;
        }
        for (var visibleIndex = 0; visibleIndex < visibleNames.length; visibleIndex += 1) {
          var visibleLayerIndex = layerIndex(document, visibleNames[visibleIndex]);
          if (visibleLayerIndex < 0) throw new Error("round-trip layer missing: " + visibleNames[visibleIndex]);
          document.layers[visibleLayerIndex].visible = true;
        }
      }
      function exportPng(document, label) {
        message("PHOTOPEA_EXPORT:" + label);
        document.saveToOE("png");
      }
      function exportMaskView(document, maskLayer, label) {
        showOnly(document, [maskLayer], maskLayer);
        exportPng(document, label);
      }
      try {
        var document = app.activeDocument;
        var requiredNames = ["WORKING MASK", "RESTORED", "BLUE JEAN (COLOR FILL)", "NAVY (COLOR FILL)", "BLACK (COLOR FILL)", "WORKING MASK BASE", "WITH GAPS", "SOURCE BACKUP"];
        for (var requiredIndex = 0; requiredIndex < requiredNames.length; requiredIndex += 1) if (layerIndex(document, requiredNames[requiredIndex]) < 0) throw new Error("round-trip required layer missing: " + requiredNames[requiredIndex]);
        var label = ${safeLabel};
        if (label === "artwork") { showOnly(document, ["RESTORED"], "RESTORED"); exportPng(document, label); }
        else if (label === "mask") { showOnly(document, ["WORKING MASK"], "WORKING MASK"); exportPng(document, label); }
        else if (label === "preview_black") { showOnly(document, ["BLACK (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, label); }
        else if (label === "preview_navy") { showOnly(document, ["NAVY (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, label); }
        else if (label === "preview_blue_jean") { showOnly(document, ["BLUE JEAN (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, label); }
        else throw new Error("unsupported round-trip export label: " + label);
      } catch (error) { message("PHOTOPEA_ROUNDTRIP_FAILED:" + String(error)); }
    })();
  `;
}

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

function decodePng(buffer) {
  const input = Buffer.from(buffer);
  if (input.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") throw new Error("not a PNG");
  let offset = 8; let width = 0; let height = 0; let colorType = 0; let bitDepth = 0; const idat = []; let palette = null; let transparency = null;
  while (offset < input.length) {
    const length = input.readUInt32BE(offset); const type = input.subarray(offset + 4, offset + 8).toString("ascii");
    const data = input.subarray(offset + 8, offset + 8 + length); offset += length + 12;
    if (type === "IHDR") { width = data.readUInt32BE(0); height = data.readUInt32BE(4); bitDepth = data[8]; colorType = data[9]; }
    if (type === "PLTE") palette = data;
    if (type === "tRNS") transparency = data;
    if (type === "IDAT") idat.push(data);
    if (type === "IEND") break;
  }
  if (![0, 2, 3, 4, 6].includes(colorType) || ![1, 2, 4, 8, 16].includes(bitDepth) || (colorType === 3 && ![1, 2, 4, 8].includes(bitDepth))) throw new Error(`unsupported PNG encoding: color_type=${colorType}, bit_depth=${bitDepth}`);
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType];
  const bytesPerSample = bitDepth === 16 ? 2 : 1; const bytesPerPixel = colorType === 3 ? 1 : channels * bytesPerSample; const stride = colorType === 3 ? Math.ceil(width * bitDepth / 8) : width * bytesPerPixel; const raw = inflateSync(Buffer.concat(idat)); const rows = Buffer.alloc(height * stride); let cursor = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[cursor++]; const row = rows.subarray(y * stride, (y + 1) * stride); const prior = y ? rows.subarray((y - 1) * stride, y * stride) : null;
    for (let x = 0; x < stride; x += 1) {
      const left = x >= bytesPerPixel ? row[x - bytesPerPixel] : 0; const up = prior ? prior[x] : 0; const upLeft = prior && x >= bytesPerPixel ? prior[x - bytesPerPixel] : 0;
      const value = raw[cursor++]; row[x] = (value + (filter === 1 ? left : filter === 2 ? up : filter === 3 ? Math.floor((left + up) / 2) : filter === 4 ? paeth(left, up, upLeft) : 0)) & 255;
    }
  }
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i += 1) {
    const target = i * 4;
    if (colorType === 3) {
      const pixelX = i % width; const pixelY = Math.floor(i / width); const packed = rows[pixelY * stride + Math.floor(pixelX * bitDepth / 8)]; const shift = 8 - bitDepth - ((pixelX * bitDepth) % 8); const index = (packed >> shift) & ((1 << bitDepth) - 1); const paletteOffset = index * 3;
      rgba[target] = palette?.[paletteOffset] ?? 0; rgba[target + 1] = palette?.[paletteOffset + 1] ?? 0; rgba[target + 2] = palette?.[paletteOffset + 2] ?? 0; rgba[target + 3] = transparency?.[index] ?? 255;
      continue;
    }
    const source = i * bytesPerPixel; const sample = (position) => rows[position];
    if (colorType === 6) { rgba[target] = sample(source); rgba[target + 1] = sample(source + bytesPerSample); rgba[target + 2] = sample(source + bytesPerSample * 2); rgba[target + 3] = sample(source + bytesPerSample * 3); }
    else if (colorType === 2) { rgba[target] = sample(source); rgba[target + 1] = sample(source + bytesPerSample); rgba[target + 2] = sample(source + bytesPerSample * 2); rgba[target + 3] = 255; }
    else if (colorType === 4) { rgba[target] = sample(source); rgba[target + 1] = sample(source); rgba[target + 2] = sample(source); rgba[target + 3] = sample(source + bytesPerSample); }
    else { const value = sample(source); rgba[target] = value; rgba[target + 1] = value; rgba[target + 2] = value; rgba[target + 3] = 255; }
  }
  return { width, height, rgba };
}

function sha256(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
function maskValue(image, offset) {
  const red = image.rgba[offset]; const green = image.rgba[offset + 1]; const blue = image.rgba[offset + 2]; const alpha = image.rgba[offset + 3];
  if (red === green && green === blue && alpha === 255) return red;
  if (red === 255 && green === 255 && blue === 255) return alpha;
  throw new Error(`unsupported submitted mask pixel representation at ${offset / 4}: rgba=${red},${green},${blue},${alpha}`);
}
function rasterMaskHash(carrierBytes) {
  const carrier = decodePng(carrierBytes);
  const mask = Buffer.alloc(carrier.width * carrier.height);
  for (let index = 0; index < mask.length; index += 1) mask[index] = maskValue(carrier, index * 4);
  return sha256(mask);
}

function parseRasterRevision(raw) {
  const revision = typeof raw === "string" ? JSON.parse(raw || "{}") : raw;
  const hashFields = ["source_sha256", "base_mask_sha256", "result_mask_sha256"];
  if (revision && typeof revision === "object" && ["subject_polygons", "remove_polygons", "add_polygons", "selection_path"].some((field) => Object.prototype.hasOwnProperty.call(revision, field))) throw new Error("polygon mask plans are unsupported");
  const initial = revision && (revision.parent_revision_id === null || revision.parent_revision_id === undefined);
  const checkpointValid = initial ? (revision.checkpoint_sha256 === "" || revision.checkpoint_sha256 === undefined || revision.checkpoint_sha256 === null) : /^[0-9a-f]{64}$/.test(String(revision?.checkpoint_sha256 || ""));
  if (!revision || typeof revision !== "object" || typeof revision.revision_id !== "string" || !revision.revision_id || revision.operation !== "replace_mask" || !checkpointValid || hashFields.some((field) => !/^[0-9a-f]{64}$/.test(String(revision[field] || ""))) || typeof revision.confidence !== "number" || revision.confidence < 0 || revision.confidence > 1) throw new Error("invalid raster mask revision");
  return revision;
}
function comparePixels(left, right, tolerance = 0) {
  if (left.width !== right.width || left.height !== right.height || left.rgba.length !== right.rgba.length) return { equal: false, changed: -1 };
  let changed = 0;
  for (let index = 0; index < left.rgba.length; index += 1) if (Math.abs(left.rgba[index] - right.rgba[index]) > tolerance) changed += 1;
  return { equal: changed === 0, changed };
}

function expectedComposite(source, carrier, background) {
  const rgba = Buffer.alloc(source.rgba.length);
  for (let index = 0; index < source.width * source.height; index += 1) {
    const sourceOffset = index * 4;
    const alpha = maskValue(carrier, sourceOffset) / 255;
    rgba[sourceOffset] = Math.round(source.rgba[sourceOffset] * alpha + background[0] * (1 - alpha));
    rgba[sourceOffset + 1] = Math.round(source.rgba[sourceOffset + 1] * alpha + background[1] * (1 - alpha));
    rgba[sourceOffset + 2] = Math.round(source.rgba[sourceOffset + 2] * alpha + background[2] * (1 - alpha));
    rgba[sourceOffset + 3] = 255;
  }
  return { width: source.width, height: source.height, rgba };
}

function canonicalMaskValue(image, offset) {
  const red = image.rgba[offset]; const green = image.rgba[offset + 1]; const blue = image.rgba[offset + 2]; const alpha = image.rgba[offset + 3];
  if (red === green && green === blue && alpha === 255) return red;
  if (red === 255 && green === 255 && blue === 255) return alpha;
  throw new Error(`unsupported mask pixel representation at ${offset / 4}: rgba=${red},${green},${blue},${alpha}`);
}

function validatePixelEvidence(inputFiles, checkpoints, roundTrip, revision) {
  const source = decodePng(inputFiles.source);
  const carrier = decodePng(inputFiles.mask);
  const required = ["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"];
  for (const label of required) if (!checkpoints[label] || !roundTrip[label]) throw new Error(`missing pixel evidence: ${label}`);
  const mask = checkpoints.mask;
  const rtMask = roundTrip.mask;
  const maskCompare = comparePixels(mask, rtMask, 0);
  if (!maskCompare.equal) throw new Error("reopened WORKING MASK pixels differ from checkpoint");
  if (source.width !== carrier.width || source.height !== carrier.height || source.width !== mask.width || source.height !== mask.height) throw new Error("Photopea pixel dimensions differ");
  for (let index = 0; index < source.width * source.height; index += 1) {
    const acceptedMaskValue = maskValue(carrier, index * 4);
    const exportedMaskValue = canonicalMaskValue(mask, index * 4);
    if (acceptedMaskValue !== exportedMaskValue) throw new Error(`WORKING MASK pixels differ from submitted raster mask at ${index}: submitted=${acceptedMaskValue}, canonical_mask=${exportedMaskValue}`);
    const artworkOffset = index * 4;
    const exportedArtwork = checkpoints.artwork.rgba;
    const exportedAlpha = exportedArtwork[artworkOffset + 3];
    const expectedRgb = acceptedMaskValue === 0 ? [0, 0, 0] : Array.from(source.rgba.subarray(artworkOffset, artworkOffset + 3));
    const rgbMatches = expectedRgb.every((channel, channelIndex) => exportedArtwork[artworkOffset + channelIndex] === channel);
    const alphaMatches = acceptedMaskValue === exportedAlpha;
    if (!rgbMatches || !alphaMatches || (acceptedMaskValue === 0 && exportedAlpha !== 0)) {
      throw new Error(`transparent artwork mismatch at ${index}: source=${Array.from(source.rgba.subarray(artworkOffset, artworkOffset + 4)).join(",")}, exported=${Array.from(exportedArtwork.subarray(artworkOffset, artworkOffset + 4)).join(",")}, accepted_mask=${acceptedMaskValue}`);
    }
  }
  const expectedPreviews = {
    preview_black: [0, 0, 0],
    preview_navy: [54, 75, 99],
    preview_blue_jean: [110, 142, 174],
  };
  for (const [label, background] of Object.entries(expectedPreviews)) {
    const previewCheck = comparePixels(expectedComposite(source, carrier, background), checkpoints[label], 3);
    if (!previewCheck.equal) throw new Error(`${label} pixels differ from accepted source/mask render: ${previewCheck.changed}`);
  }
  for (const label of required) if (!comparePixels(checkpoints[label], roundTrip[label], 0).equal) throw new Error(`reopened ${label} pixels differ from checkpoint`);
  return {
    source_sha256: revision.source_sha256,
    result_mask_sha256: revision.result_mask_sha256,
    checkpoint_sha256: sha256(Buffer.concat(required.map((label) => checkpoints[label].rgba))),
    artwork_sha256: sha256(checkpoints.artwork.rgba),
    preview_sha256: ["preview_black", "preview_navy", "preview_blue_jean"].map((label) => sha256(checkpoints[label].rgba)),
    reopened: true,
    required_layers: ["SOURCE BACKUP", "RESTORED", "WITH GAPS", "WORKING MASK", "BLACK (COLOR FILL)", "NAVY (COLOR FILL)", "BLUE JEAN (COLOR FILL)"],
  };
}

function photopeaCheckpointExportScript(label) {
  const safeLabel = JSON.stringify(String(label));
  return `
    (function () {
      function message(value) { app.echoToOE(value); }
      function matches(layerName, name) {
        return layerName === name || (layerName.slice(0, name.length + 1) === name + " " && layerName.slice(0, name.length + 5) !== name + " BASE");
      }
      function layerIndex(document, name) {
        for (var index = document.layers.length - 1; index >= 0; index -= 1) if (matches(String(document.layers[index].name), name)) return index;
        return -1;
      }
      function hideAll(document) {
        app.activeDocument = document;
        for (var index = 0; index < document.layers.length; index += 1) document.layers[index].visible = false;
      }
      function showOnly(document, visibleNames, activeName) {
        app.activeDocument = document;
        var activeIndex = layerIndex(document, activeName);
        if (activeIndex < 0) throw new Error("active checkpoint layer missing: " + activeName);
        document.activeLayer = document.layers[activeIndex];
        var managedNames = ["RESTORED", "WORKING MASK", "BLACK (COLOR FILL)", "NAVY (COLOR FILL)", "BLUE JEAN (COLOR FILL)"];
        for (var managedIndex = 0; managedIndex < managedNames.length; managedIndex += 1) {
          var managedLayerIndex = layerIndex(document, managedNames[managedIndex]);
          if (managedLayerIndex >= 0 && managedLayerIndex !== activeIndex) document.layers[managedLayerIndex].visible = false;
        }
        for (var visibleIndex = 0; visibleIndex < visibleNames.length; visibleIndex += 1) {
          var visibleLayerIndex = layerIndex(document, visibleNames[visibleIndex]);
          if (visibleLayerIndex < 0) throw new Error("checkpoint layer missing: " + visibleNames[visibleIndex]);
          document.layers[visibleLayerIndex].visible = true;
        }
      }
      function exportPng(document, name) {
        message("PHOTOPEA_EXPORT:" + name);
        document.saveToOE("png");
      }
      try {
        var document = app.activeDocument;
        var name = ${safeLabel};
        if (name === "artwork") { showOnly(document, ["RESTORED"], "RESTORED"); exportPng(document, name); }
        else if (name === "mask") { showOnly(document, ["WORKING MASK"], "WORKING MASK"); exportPng(document, name); }
        else if (name === "preview_black") { showOnly(document, ["BLACK (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, name); }
        else if (name === "preview_navy") { showOnly(document, ["NAVY (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, name); }
        else if (name === "preview_blue_jean") { showOnly(document, ["BLUE JEAN (COLOR FILL)", "RESTORED"], "RESTORED"); exportPng(document, name); }
        else throw new Error("unsupported checkpoint label: " + name);
      } catch (error) { message("PHOTOPEA_STRUCTURE_FAILED:" + String(error)); }
    })();
  `;
}

function photopeaOuterPage(resultToken, inputTokens, initialScript, authorization) {
  return `
    <!doctype html><html><body><iframe id="photopea" style="width:1px;height:1px;border:0" src="https://www.photopea.com/#${encodeURIComponent(JSON.stringify({}))}"></iframe>
    <script>
      const frame = document.getElementById('photopea');
      let phase = 'boot'; let fileIndex = 0; let exportLabels = []; let pendingScript = null; let roundtripIndex = 0;
      const bridgeAuthorization = ${JSON.stringify(authorization || '')};
      const initialUrls = ['/v1/photopea/blob/${inputTokens.source}', '/v1/photopea/blob/${inputTokens.mask}', '/v1/photopea/blob/${inputTokens.withGapsMask}'];
      let revisionUrls = [];
      const initialScript = ${JSON.stringify(initialScript)};
      const checkpointScripts = ${JSON.stringify(["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"].map((label) => photopeaCheckpointExportScript(label)))};
      const roundtripScripts = ${JSON.stringify(["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"].map((label) => photopeaRoundTripScript(label)))};
      let checkpointIndex = 0; let checkpointBinaryPosted = false;
      function advanceCheckpointExport() {
        if (!checkpointBinaryPosted) return;
        checkpointBinaryPosted = false;
        checkpointIndex += 1;
        if (checkpointIndex < checkpointScripts.length) setTimeout(() => frame.contentWindow.postMessage(checkpointScripts[checkpointIndex], '*'), 2000);
        else phase = 'checkpoint-complete';
      }
      async function sendFile(index) { const buffer = await fetch(initialUrls[index]).then((response) => response.arrayBuffer()); frame.contentWindow.postMessage(buffer, '*', [buffer]); }
      function internalHeaders(contentType) { const headers = { 'Content-Type': contentType }; if (bridgeAuthorization) headers.Authorization = bridgeAuthorization; return headers; }
      async function receiveBinary(buffer) {
        const binaryLabel = exportLabels.shift() || '';
        try { await fetch('/v1/photopea/result/${resultToken}', { method: 'POST', headers: Object.assign(internalHeaders('application/octet-stream'), { 'X-Photopea-Label': binaryLabel }), body: buffer }); } catch (_) {}
        if (phase === 'checkpoint-export' || phase === 'revision-export') {
          checkpointBinaryPosted = true;
          advanceCheckpointExport();
          return;
        }
        if (phase === 'roundtrip-export') {
          if (roundtripIndex < roundtripScripts.length - 1) {
            roundtripIndex += 1;
            frame.contentWindow.postMessage(roundtripScripts[roundtripIndex], '*');
          } else {
            phase = 'roundtrip-verify';
            frame.contentWindow.postMessage('app.echoToOE("PHOTOPEA_ROUNDTRIP_VERIFIED");', '*');
          }
        }
      }
      async function signal(path, body) { await fetch('/v1/photopea/' + path + '/${resultToken}', { method: 'POST', headers: internalHeaders('text/plain'), body: body || '' }); }
      window.startPhotopeaRoundTrip = async function (id) { const buffer = await fetch('/v1/photopea/blob/' + id).then((response) => response.arrayBuffer()); phase = 'roundtrip-file'; frame.contentWindow.postMessage(buffer, '*', [buffer]); };
      async function sendRevisionFile(index) { const buffer = await fetch(revisionUrls[index]).then((response) => response.arrayBuffer()); frame.contentWindow.postMessage(buffer, '*', [buffer]); }
      window.startRevision = async function (maskId, script) { pendingScript = script; revisionUrls = ['/v1/photopea/blob/' + maskId]; phase = 'revision-mask'; };
      window.startFinal = function (script) { phase = 'final-script'; frame.contentWindow.postMessage(script, '*'); };
      window.addEventListener('message', async (event) => {
        if (event.source !== frame.contentWindow) return;
        if (typeof event.data === 'string') {
          console.log('PHOTOPEA_MESSAGE:' + event.data);
          if (/^PHOTOPEA_(STRUCTURE|REVISION|FINALIZE|ROUNDTRIP)_FAILED:/.test(event.data)) { await signal('failure', event.data); return; }
          if (event.data.indexOf('PHOTOPEA_EXPORT:') === 0) { exportLabels.push(event.data.slice('PHOTOPEA_EXPORT:'.length)); return; }
          if (event.data === 'PHOTOPEA_STRUCTURE_BUILT' || event.data === 'PHOTOPEA_REVISION_BUILT') { checkpointIndex = 0; checkpointBinaryPosted = false; exportLabels = []; phase = event.data === 'PHOTOPEA_STRUCTURE_BUILT' ? 'checkpoint-export' : 'revision-export'; frame.contentWindow.postMessage(checkpointScripts[0], '*'); return; }
          if (event.data === 'PHOTOPEA_CHECKPOINT_READY') { return; }
          if (event.data === 'PHOTOPEA_ROUNDTRIP_VERIFIED') { await signal('done'); return; }
        }
        if (event.data instanceof ArrayBuffer) { await receiveBinary(event.data); return; }
        if (event.data !== 'done') return;
        if (phase === 'boot') { phase = 'files'; await sendFile(fileIndex); }
        else if (phase === 'files' && fileIndex < 2) { fileIndex += 1; await sendFile(fileIndex); }
        else if (phase === 'files') { phase = 'script'; frame.contentWindow.postMessage(initialScript, '*'); }
        else if (phase === 'revision-mask') { phase = 'revision-script'; await sendRevisionFile(0); }
        else if (phase === 'revision-script') { frame.contentWindow.postMessage(pendingScript, '*'); }
        else if (phase === 'checkpoint-export' || phase === 'revision-export') { return; }
        else if (phase === 'roundtrip-file') { phase = 'roundtrip-export'; roundtripIndex = 0; frame.contentWindow.postMessage(roundtripScripts[roundtripIndex], '*'); }
      });
    </script></body></html>`;
}

class PhotopeaLiveSession {
  constructor(browser, page, resultToken, inputFiles, revision, timeoutMs) {
    this.browser = browser; this.page = page; this.resultToken = resultToken;
    this.inputFiles = inputFiles; this.currentRevision = revision; this.timeoutMs = timeoutMs;
    this.checkpoints = {}; this.checkpointBytes = {}; this.roundTrip = {}; this.psd = null; this.phase = "boot"; this.checkpointReadyScheduled = false;
    this.checkpointSequence = 0; this.checkpointWaiters = []; this.doneWaiters = []; this.doneSignaled = false;
  }

  static async open(inputFiles, revision, options = {}) {
    if (sha256(inputFiles.source) !== revision.source_sha256) throw new Error("source hash does not match raster revision");
    if (!inputFiles.withGapsMask) inputFiles.withGapsMask = inputFiles.mask;
    const launchOptions = { headless: true };
    if (process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PHOTOPEA_CHROMIUM_EXECUTABLE_PATH;
    const browser = await chromium.launch(launchOptions);
    const timeoutMs = Number(options.timeoutMs || process.env.PHOTOPEA_EXPORT_TIMEOUT_MS || 300_000);
    const resultToken = crypto.randomUUID();
    try {
      const page = await browser.newPage();
      const session = new PhotopeaLiveSession(browser, page, resultToken, inputFiles, revision, timeoutMs);
      await session.start();
      return session;
    } catch (error) { await browser.close(); throw error; }
  }

  async start() {
    const timer = setTimeout(() => this.fail(new Error("photopea session timed out")), this.timeoutMs);
    this.timer = timer;
    this.page.on("console", (message) => console.log(JSON.stringify({ event_type: "PhotopeaConsole", type: message.type(), text: message.text() })));
    this.page.on("pageerror", (error) => { const message = String(error); console.log(JSON.stringify({ event_type: "PhotopeaPageError", message, stack: error.stack })); });
    this.page.on("requestfailed", (request) => console.log(JSON.stringify({ event_type: "PhotopeaRequestFailed", url: request.url(), error: request.failure()?.errorText })));
    app.on(`photopea:${this.resultToken}:binary`, this.onBinary = ({ label, buffer }) => this.handleBinary(label, buffer));
    app.on(`photopea:${this.resultToken}:checkpoint`, this.onCheckpoint = () => this.markCheckpointReady());
    app.on(`photopea:${this.resultToken}:failure`, this.onFailure = (message) => this.fail(new Error(message)));
    app.on(`photopea:${this.resultToken}:done`, this.onDone = () => this.signalDone());
    await this.page.goto(`http://127.0.0.1:${port}/healthz`, { waitUntil: "domcontentloaded", timeout: 120_000 });
    const inputTokens = { source: transfer(this.inputFiles.source), mask: transfer(this.inputFiles.mask), withGapsMask: transfer(this.inputFiles.withGapsMask || this.inputFiles.mask) };
    const checkpoint = this.waitForCheckpoint(0);
    const initialScript = photopeaRasterMaskScript({ finalize: false });
    await this.page.setContent(photopeaOuterPage(this.resultToken, inputTokens, initialScript, token ? `Bearer ${token}` : ""), { waitUntil: "domcontentloaded", timeout: 120_000 });
    await checkpoint;
  }

  handleBinary(label, buffer) {
    console.log(JSON.stringify({ event_type: "PhotopeaBinaryReceived", label, phase: this.phase, bytes: buffer.length }));
    if (label === "psd") {
      this.psd = buffer; this.phase = "roundtrip-file";
      const psdToken = transfer(buffer);
      this.page.evaluate((id) => window.startPhotopeaRoundTrip(id), psdToken).catch((error) => this.fail(error));
    } else {
      const labels = ["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"];
      const checkpointStillArriving = this.checkpointPending || labels.some((item) => !this.checkpoints[item]);
      const isRoundTrip = (this.phase === "roundtrip-file" || this.phase === "roundtrip-export" || this.phase === "roundtrip-verify") && !checkpointStillArriving;
      if (isRoundTrip) {
        this.roundTrip[label] = decodePng(buffer);
        if (labels.every((item) => this.roundTrip[item])) this.signalDone();
      } else {
        this.checkpoints[label] = decodePng(buffer);
        this.checkpointBytes[label] = Buffer.from(buffer);
        if (labels.every((item) => this.checkpoints[item]) && !this.checkpointPending && !this.checkpointReadyScheduled) {
          this.checkpointReadyScheduled = true;
          setTimeout(() => { this.checkpointReadyScheduled = false; this.markCheckpointReady(); }, 3000);
        }
      }
    }
    this.maybeSignalCheckpoint();
  }

  markCheckpointReady() {
    this.checkpointPending = true;
    this.maybeSignalCheckpoint();
  }

  maybeSignalCheckpoint() {
    if (!this.checkpointPending) return;
    const labels = ["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"];
    if (labels.some((label) => !this.checkpoints[label])) return;
    this.checkpointPending = false;
    this.checkpointSequence += 1;
    const waiters = this.checkpointWaiters.splice(0);
    for (const waiter of waiters) waiter.resolve(this.checkpointSequence);
  }

  signalDone() {
    this.doneSignaled = true;
    console.log(JSON.stringify({ event_type: "PhotopeaRoundTripReady", result_token: this.resultToken }));
    const waiters = this.doneWaiters.splice(0);
    for (const waiter of waiters) waiter.resolve();
  }

  fail(error) {
    const value = error instanceof Error ? error : new Error(String(error));
    for (const waiter of this.checkpointWaiters.splice(0)) waiter.reject(value);
    for (const waiter of this.doneWaiters.splice(0)) waiter.reject(value);
  }

  waitForCheckpoint(afterSequence) {
    if (this.checkpointSequence > afterSequence) return Promise.resolve(this.checkpointSequence);
    return new Promise((resolve, reject) => this.checkpointWaiters.push({ resolve, reject }));
  }

  waitForDone() {
    if (this.doneSignaled) return Promise.resolve();
    return new Promise((resolve, reject) => this.doneWaiters.push({ resolve, reject }));
  }

  checkpointSummary(revision, sessionId = null) {
    const labels = ["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"];
    if (labels.some((label) => !this.checkpoints[label])) throw new Error("Photopea checkpoint is incomplete");
    return {
      revision_id: revision.revision_id,
      source_sha256: revision.source_sha256,
      checkpoint_sha256: sha256(Buffer.concat(labels.map((label) => this.checkpoints[label].rgba))),
      mask_sha256: sha256(this.checkpoints.mask.rgba),
      artwork_sha256: sha256(this.checkpoints.artwork.rgba),
      artifact_urls: sessionId ? Object.assign({ source: `/v1/photopea/sessions/${sessionId}/checkpoints/source` }, Object.fromEntries(labels.map((label) => [label, `/v1/photopea/sessions/${sessionId}/checkpoints/${label}`]))) : {},
    };
  }

  checkpointArtifact(label) {
    const allowed = ["artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"];
    if (label === "source") return this.inputFiles.source;
    if (!allowed.includes(label) || !this.checkpointBytes[label]) throw new Error("checkpoint artifact is unavailable");
    return this.checkpointBytes[label];
  }

  async applyRevision(mask, revision) {
    if (revision.source_sha256 !== this.currentRevision.source_sha256) throw new Error("revision source hash mismatch");
    if (revision.parent_revision_id !== this.currentRevision.revision_id) throw new Error("revision parent mismatch");
    const previous = this.checkpointSequence;
    this.inputFiles.mask = mask; this.currentRevision = revision; this.checkpoints = {}; this.checkpointBytes = {}; this.roundTrip = {}; this.checkpointReadyScheduled = false;
    const checkpoint = this.waitForCheckpoint(previous);
    const maskToken = transfer(mask);
    await this.page.evaluate(({ maskId, script }) => window.startRevision(maskId, script), { maskId: maskToken, script: photopeaRevisionScript(revision.revision_id) });
    await checkpoint;
    return this.checkpointSummary(revision);
  }

  async finalize(revision) {
    this.currentRevision = revision; this.roundTrip = {}; this.psd = null;
    const done = this.waitForDone();
    console.log(JSON.stringify({ event_type: "PhotopeaFinalizeStage", stage: "script_started", result_token: this.resultToken }));
    await this.page.evaluate((script) => window.startFinal(script), photopeaSavePsdScript());
    await done;
    console.log(JSON.stringify({ event_type: "PhotopeaFinalizeStage", stage: "roundtrip_ready", result_token: this.resultToken }));
    const evidence = validatePixelEvidence(this.inputFiles, this.checkpoints, this.roundTrip, revision);
    console.log(JSON.stringify({ event_type: "PhotopeaFinalizeStage", stage: "pixel_evidence_verified", result_token: this.resultToken }));
    if (!this.psd || !this.psd.subarray(0, 4).equals(Buffer.from("8BPS"))) throw new Error("Photopea returned a non-PSD payload");
    return { psd: this.psd, evidence };
  }

  async close() {
    clearTimeout(this.timer);
    app.off(`photopea:${this.resultToken}:binary`, this.onBinary);
    app.off(`photopea:${this.resultToken}:checkpoint`, this.onCheckpoint);
    app.off(`photopea:${this.resultToken}:failure`, this.onFailure);
    app.off(`photopea:${this.resultToken}:done`, this.onDone);
    await this.browser.close();
  }
}

async function exportViaPhotopea(inputFiles, revision, options = {}) {
  const session = await PhotopeaLiveSession.open(inputFiles, revision, options);
  try { return await session.finalize(revision); }
  finally { await session.close(); }
}

app.use(express.json({ limit: "64kb" }));
app.use(express.raw({ type: "application/octet-stream", limit: "200mb" }));
app.get("/healthz", (_request, response) => response.json({ status: "ok", provider: "photopea-live" }));
app.get("/v1/photopea/blob/:id", (request, response) => {
  const payload = transferStore.get(request.params.id);
  if (!payload) return response.status(404).end();
  return response.type("application/octet-stream").send(payload);
});
app.post("/v1/photopea/result/:id", (request, response) => {
  if (!authorized(request)) return response.status(401).end();
  const payload = Buffer.isBuffer(request.body) ? request.body : Buffer.from(request.body || []);
  transferStore.set(request.params.id, { label: request.get("X-Photopea-Label") || "", buffer: payload });
  app.emit(`photopea:${request.params.id}:binary`, { label: request.get("X-Photopea-Label") || "", buffer: payload });
  return response.status(204).end();
});
app.post("/v1/photopea/failure/:id", express.text({ type: "*/*", limit: "8kb" }), (request, response) => {
  app.emit(`photopea:${request.params.id}:failure`, String(request.body));
  return response.status(204).end();
});
app.post("/v1/photopea/checkpoint/:id", express.text({ type: "*/*", limit: "1kb" }), (request, response) => {
  app.emit(`photopea:${request.params.id}:checkpoint`);
  return response.status(204).end();
});
app.post("/v1/photopea/done/:id", (request, response) => {
  app.emit(`photopea:${request.params.id}:done`);
  return response.status(204).end();
});

function sessionResponse(sessionId, record) {
  const checkpoint = record.live.checkpointSummary(record.revision, sessionId);
  return {
    session_id: sessionId,
    status: record.status,
    revision: record.revision,
    checkpoint,
    expires_at: record.expiresAt,
  };
}

app.post("/v1/photopea/sessions", upload.fields([
  { name: "source", maxCount: 1 },
  { name: "mask", maxCount: 1 },
  { name: "with_gaps_mask", maxCount: 1 },
]), async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const source = request.files?.source?.[0]?.buffer;
  const mask = request.files?.mask?.[0]?.buffer;
  const withGapsMask = request.files?.with_gaps_mask?.[0]?.buffer || mask;
  if (!source || !mask) return response.status(400).json({ code: "missing_source_or_mask" });
  let revision;
  try { revision = parseRasterRevision(request.body?.mask_revision); }
  catch (error) { return response.status(400).json({ code: "invalid_photopea_mask_revision", message: String(error) }); }
  try {
    if (rasterMaskHash(mask) !== revision.result_mask_sha256) throw new Error("initial raster mask hash mismatch");
    const live = await PhotopeaLiveSession.open({ source, mask, withGapsMask }, revision, { timeoutMs: Number(process.env.PHOTOPEA_SESSION_TIMEOUT_MS || 300_000) });
    const sessionId = crypto.randomUUID();
    const initialCheckpoint = live.checkpointSummary(revision);
    const effectiveRevision = Object.assign({}, revision, { checkpoint_sha256: initialCheckpoint.checkpoint_sha256 });
    const record = { live, revision: effectiveRevision, checkpoint: live.checkpointSummary(effectiveRevision), status: "checkpoint_ready", expiresAt: new Date(Date.now() + 300_000).toISOString() };
    const timer = setTimeout(() => { const current = photopeaSessions.get(sessionId); if (current) { current.live.close().catch(() => {}); photopeaSessions.delete(sessionId); } }, 300_000);
    timer.unref(); record.timer = timer;
    photopeaSessions.set(sessionId, record);
    return response.status(201).json(sessionResponse(sessionId, record));
  } catch (error) { console.log(JSON.stringify({ event_type: "PhotopeaSessionOpenFailed", message: String(error), stack: error?.stack })); return response.status(502).json({ code: "photopea_session_failed", message: String(error) }); }
});

app.get("/v1/photopea/sessions/:id", (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const record = photopeaSessions.get(request.params.id);
  if (!record) return response.status(404).json({ code: "photopea_session_not_found" });
  return response.json(sessionResponse(request.params.id, record));
});

app.get("/v1/photopea/sessions/:id/checkpoints/:label", (request, response) => {
  if (!authorized(request)) return response.status(401).end();
  const record = photopeaSessions.get(request.params.id);
  if (!record) return response.status(404).json({ code: "photopea_session_not_found" });
  try { return response.type("image/png").send(record.live.checkpointArtifact(request.params.label)); }
  catch (_error) { return response.status(404).json({ code: "checkpoint_artifact_not_found" }); }
});

app.post("/v1/photopea/sessions/:id/revisions", upload.single("mask"), async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const record = photopeaSessions.get(request.params.id);
  if (!record) return response.status(404).json({ code: "photopea_session_not_found" });
  if (!request.file?.buffer) return response.status(400).json({ code: "missing_mask" });
  let revision;
  try { revision = parseRasterRevision(request.body?.mask_revision); }
  catch (error) { return response.status(400).json({ code: "invalid_photopea_mask_revision", message: String(error) }); }
  if (revision.source_sha256 !== record.revision.source_sha256) return response.status(409).json({ code: "stale_source_revision" });
  if (revision.parent_revision_id !== record.revision.revision_id) return response.status(409).json({ code: "stale_parent_revision" });
  if (revision.checkpoint_sha256 !== record.checkpoint.checkpoint_sha256) return response.status(409).json({ code: "stale_checkpoint_revision" });
  try {
    if (rasterMaskHash(request.file.buffer) !== revision.result_mask_sha256) throw new Error("raster mask hash mismatch");
    const checkpoint = await record.live.applyRevision(request.file.buffer, revision);
    record.revision = revision; record.checkpoint = checkpoint; record.status = "checkpoint_ready";
    return response.json(sessionResponse(request.params.id, record));
  } catch (error) { record.status = "review_required"; return response.status(502).json({ code: "photopea_revision_failed", message: String(error) }); }
});

app.post("/v1/photopea/sessions/:id/finalize", async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  const record = photopeaSessions.get(request.params.id);
  if (!record) return response.status(404).json({ code: "photopea_session_not_found" });
  if (!validAcceptanceToken(record.revision, request.body?.acceptance_token)) return response.status(409).json({ code: "review_acceptance_required" });
  try {
    const result = await record.live.finalize(record.revision);
    if (result.evidence.checkpoint_sha256 !== record.checkpoint.checkpoint_sha256) throw new Error("final PSD evidence does not match the accepted checkpoint");
    clearTimeout(record.timer); photopeaSessions.delete(request.params.id);
    response.set("X-Photopea-Roundtrip", "verified");
    response.set("X-Photopea-Evidence", JSON.stringify(result.evidence));
    return response.type("application/vnd.adobe.photoshop").send(result.psd);
  } catch (error) { console.log(JSON.stringify({ event_type: "PhotopeaFinalizeFailed", message: String(error), stack: error.stack })); record.status = "review_required"; return response.status(502).json({ code: "photopea_finalize_failed", message: String(error) }); }
});

app.delete("/v1/photopea/sessions/:id", async (request, response) => {
  if (!authorized(request)) return response.status(401).end();
  const record = photopeaSessions.get(request.params.id);
  if (record) { clearTimeout(record.timer); photopeaSessions.delete(request.params.id); await record.live.close(); }
  return response.status(204).end();
});

app.post("/v1/photopea/export", upload.fields([
  { name: "source", maxCount: 1 },
  { name: "mask", maxCount: 1 },
]), async (request, response) => {
  if (!authorized(request)) return response.status(401).json({ code: "unauthorized" });
  return response.status(409).json({ code: "photopea_session_required", message: "one-shot export is disabled; use the reviewed session workflow" });
  const source = request.files?.source?.[0]?.buffer;
  const mask = request.files?.mask?.[0]?.buffer;
  if (!source || !mask) return response.status(400).json({ code: "missing_source_or_mask" });
  let revision;
  try {
    revision = parseRasterRevision(request.body?.mask_revision);
  } catch (error) { return response.status(400).json({ code: "invalid_photopea_mask_revision", message: String(error) }); }
  if (!validAcceptanceToken(revision, request.body?.acceptance_token)) return response.status(409).json({ code: "review_acceptance_required" });
  try {
    if (rasterMaskHash(mask) !== revision.result_mask_sha256) return response.status(409).json({ code: "raster_mask_hash_mismatch" });
    const result = await exportViaPhotopea({ source, mask }, revision, { timeoutMs: Number(process.env.PHOTOPEA_SESSION_TIMEOUT_MS || 300_000) });
    response.set("X-Photopea-Roundtrip", "verified");
    response.set("X-Photopea-Evidence", JSON.stringify(result.evidence));
    return response.type("application/vnd.adobe.photoshop").send(result.psd);
  } catch (error) {
    return response.status(502).json({ code: "photopea_export_failed", message: String(error) });
  }
});

app.listen(port, "127.0.0.1", () => console.log(JSON.stringify({ event_type: "PhotopeaLiveApiStarted", port })));
