from __future__ import annotations

from pathlib import Path


BRIDGE = (Path(__file__).parents[1] / "bridge" / "server.mjs").read_text()


def test_photopea_revision_keeps_the_source_document_open() -> None:
    assert "phase = 'revision-close'" not in BRIDGE
    assert "while (app.documents.length > 0) app.documents[0].close" not in BRIDGE
    assert "window.startRevision = async function (maskId, script)" in BRIDGE
    assert "document.name = \"SOURCE INPUT\"" in BRIDGE


def test_photopea_initial_build_has_independent_restored_and_gaps_carriers() -> None:
    assert "files: 3" in BRIDGE
    assert "with_gaps_mask" in BRIDGE
    assert 'var gapsCarrierDocument = app.documents[2];' in BRIDGE
    assert 'var gapsCarrier = copyLayer(gapsCarrierDocument' in BRIDGE
    assert 'applyRasterMaskFromPixels(document, gapsCarrier, withGaps);' in BRIDGE


def test_photopea_finalize_requires_review_acceptance_token() -> None:
    assert "PHOTOPEA_REVIEW_SECRET" in BRIDGE
    assert "review_acceptance_required" in BRIDGE
    assert "validAcceptanceToken(record.revision, request.body?.acceptance_token)" in BRIDGE


def test_photopea_final_psd_restores_the_accepted_artwork_visibility() -> None:
    assert 'name === "RESTORED" || name.indexOf("RESTORED ") === 0' in BRIDGE
    assert 'if (!restored) throw new Error("accepted RESTORED layer is missing")' in BRIDGE
    assert 'document.saveToOE("psd:true")' in BRIDGE


def test_initial_revision_checkpoint_is_created_by_bridge() -> None:
    assert 'const initialCheckpoint = live.checkpointSummary(revision);' in BRIDGE
    assert 'checkpoint_sha256: initialCheckpoint.checkpoint_sha256' in BRIDGE
