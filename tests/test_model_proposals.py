from __future__ import annotations

import hashlib
import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

from printify_artwork_cleaner.adapters.model_proposals import (
    ConsensusMattingProvider,
    derive_mask_tuning,
    HttpMattingProvider,
    ModelProposalUnavailable,
    ProposalResponse,
    SAM21ProtectionProvider,
    configured_consensus_provider,
)
from printify_artwork_cleaner.domain.image_math import canonical_rgba_png_bytes
from printify_artwork_cleaner.domain.models import ModelEvidence, ProcessingPolicy


class _Provider:
    def __init__(self, name: str, alpha: np.ndarray) -> None:
        self.response = ProposalResponse(
            alpha=alpha,
            protection=alpha > 0,
            uncertainty=np.zeros_like(alpha),
            evidence=ModelEvidence(name, name, "pinned", "declared", "a" * 64, hashlib.sha256(alpha.tobytes()).hexdigest()),
        )

    def propose(self, source, policy):
        return self.response


def test_consensus_requires_two_independent_model_proposals() -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    first = _Provider("birefnet", np.array([[0, 100], [200, 255]], dtype=np.uint8))
    second = _Provider("ben2", np.array([[0, 120], [180, 255]], dtype=np.uint8))
    result = ConsensusMattingProvider(first, second).propose(source, ProcessingPolicy())
    assert result.evidence[0].provider == "birefnet"
    assert result.evidence[1].provider == "ben2"
    assert result.resolved_masks.proposed_alpha.tolist() == [[0, 110], [190, 255]]
    assert result.resolved_masks.provenance == ("birefnet", "ben2", "consensus")


def test_mask_tuning_uses_per_artwork_model_transition() -> None:
    source = np.full((8, 8, 4), [71, 101, 121, 255], dtype=np.uint8)
    source[2:6, 2:6, :3] = [77, 107, 127]
    alpha = np.zeros((8, 8), dtype=np.uint8)
    alpha[2:6, 2:6] = 128

    tuning = derive_mask_tuning(source, alpha, "a" * 64)

    assert tuning.background_tolerance == 6
    assert tuning.source_sha256 == "a" * 64
    assert tuning.decision_id.startswith("model-preflight-")


def test_http_provider_rejects_response_without_alpha(monkeypatch) -> None:
    provider = HttpMattingProvider(
        provider="test",
        model="test-model",
        endpoint="http://model.test",
        version="1",
        license="test-license",
        weights_sha256="a" * 64,
    )

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({}).encode()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.model_proposals.urlopen", lambda *_args, **_kwargs: _Response())
    with pytest.raises(ModelProposalUnavailable, match="alpha_png_base64"):
        provider.propose(np.zeros((2, 2, 4), dtype=np.uint8), ProcessingPolicy())


def test_http_provider_requires_explicit_model_metadata(monkeypatch) -> None:
    provider = HttpMattingProvider(
        provider="test",
        model="test-model",
        endpoint="http://model.test",
        version="1",
        license="test-license",
        weights_sha256="a" * 64,
    )

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"alpha_png_base64": "placeholder"}).encode()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.model_proposals.urlopen", lambda *_args, **_kwargs: _Response())
    with pytest.raises(ModelProposalUnavailable, match="explicit model metadata"):
        provider.propose(np.zeros((2, 2, 4), dtype=np.uint8), ProcessingPolicy())


def test_configured_provider_fails_closed_without_a_valid_weights_hash(monkeypatch) -> None:
    monkeypatch.setenv("BIREFNET_ENDPOINT", "http://birefnet.test")
    monkeypatch.setenv("BEN2_ENDPOINT", "http://ben2.test")
    monkeypatch.setenv("BIREFNET_WEIGHTS_SHA256", "not-a-sha256")
    monkeypatch.setenv("BEN2_WEIGHTS_SHA256", "b" * 64)
    assert configured_consensus_provider() is None


def test_configured_provider_requires_independent_metadata_pins(monkeypatch) -> None:
    monkeypatch.setenv("BIREFNET_ENDPOINT", "http://birefnet.test")
    monkeypatch.setenv("BEN2_ENDPOINT", "http://ben2.test")
    monkeypatch.setenv("BIREFNET_MODEL_VERSION", "birefnet-v1")
    monkeypatch.setenv("BIREFNET_MODEL_LICENSE", "apache-2.0")
    monkeypatch.setenv("BIREFNET_WEIGHTS_SHA256", "a" * 64)
    monkeypatch.setenv("BEN2_MODEL_VERSION", "ben2-v1")
    monkeypatch.setenv("BEN2_MODEL_LICENSE", "apache-2.0")
    monkeypatch.setenv("BEN2_WEIGHTS_SHA256", "b" * 64)
    provider = configured_consensus_provider()
    assert provider is not None
    assert provider.primary.version == "birefnet-v1"
    assert provider.secondary.version == "ben2-v1"


def test_consensus_wires_optional_sam2_protection(monkeypatch) -> None:
    for name, value in {
        "BIREFNET_ENDPOINT": "http://birefnet.test",
        "BIREFNET_MODEL_VERSION": "birefnet-v1",
        "BIREFNET_MODEL_LICENSE": "apache-2.0",
        "BIREFNET_WEIGHTS_SHA256": "a" * 64,
        "BEN2_ENDPOINT": "http://ben2.test",
        "BEN2_MODEL_VERSION": "ben2-v1",
        "BEN2_MODEL_LICENSE": "apache-2.0",
        "BEN2_WEIGHTS_SHA256": "b" * 64,
        "SAM2_ENDPOINT": "http://sam2.test",
        "SAM2_MODEL_VERSION": "sam2-v1",
        "SAM2_MODEL_LICENSE": "apache-2.0",
        "SAM2_WEIGHTS_SHA256": "c" * 64,
    }.items():
        monkeypatch.setenv(name, value)
    provider = configured_consensus_provider()
    assert provider is not None
    assert isinstance(provider.protection_provider, SAM21ProtectionProvider)


def test_sam2_protection_provider_is_source_and_weight_bound(monkeypatch) -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    stream = io.BytesIO()
    Image.fromarray(np.zeros((2, 2), dtype=np.uint8), mode="L").save(stream, format="PNG")
    response = {
        "model": "SAM 2.1",
        "version": "sam2-v1",
        "license": "apache-2.0",
        "weights_sha256": "c" * 64,
        "source_sha256": hashlib.sha256(canonical_rgba_png_bytes(source)).hexdigest(),
        "protection_png_base64": base64.b64encode(stream.getvalue()).decode("ascii"),
        "uncertainty_png_base64": base64.b64encode(stream.getvalue()).decode("ascii"),
    }

    class _Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(response).encode()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.model_proposals.urlopen", lambda *_args, **_kwargs: _Response())
    provider = SAM21ProtectionProvider("http://sam2.test", version="sam2-v1", license="apache-2.0", weights_sha256="c" * 64)
    result = provider.propose(source, ProcessingPolicy())
    assert result.protection.shape == (2, 2)
    assert result.evidence.provider == "sam2"
