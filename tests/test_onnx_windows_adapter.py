from __future__ import annotations

import numpy as np
import pytest

from scripts.serve_onnx_proposals import (
    CPU_PROVIDER,
    DIRECTML_PROVIDER,
    _postprocess,
    _preprocess,
    _select_providers,
)


def test_directml_is_selected_before_cpu() -> None:
    assert _select_providers([CPU_PROVIDER, DIRECTML_PROVIDER], require_directml=False) == (DIRECTML_PROVIDER, CPU_PROVIDER)


def test_directml_can_be_required_for_production() -> None:
    with pytest.raises(RuntimeError, match="DmlExecutionProvider"):
        _select_providers([CPU_PROVIDER], require_directml=True)


def test_preprocess_is_normalized_nchw_float32() -> None:
    source = np.zeros((8, 12, 4), dtype=np.uint8)
    source[..., :3] = [255, 128, 0]
    tensor = _preprocess(source, 1024)
    assert tensor.shape == (1, 3, 1024, 1024)
    assert tensor.dtype == np.float32
    assert np.isfinite(tensor).all()


def test_logits_are_sigmoided_resized_and_returned_as_alpha() -> None:
    output = np.zeros((1, 1, 2, 2), dtype=np.float32)
    output[..., 0, 0] = 20
    output[..., 1, 1] = -20
    alpha = _postprocess(output, (4, 4), "logits")
    assert alpha.shape == (4, 4)
    assert alpha.dtype == np.uint8
    assert int(alpha.max()) > 200
    assert int(alpha.min()) < 50


def test_unsupported_provider_set_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="no supported providers"):
        _select_providers(["TensorrtExecutionProvider"], require_directml=False)
