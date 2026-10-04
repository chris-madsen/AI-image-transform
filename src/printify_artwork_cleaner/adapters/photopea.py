from __future__ import annotations

import io
import json
from dataclasses import asdict, is_dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from typing import Mapping


class PhotopeaLiveApiUnavailable(RuntimeError):
    """The external Photopea Live outer environment is unavailable."""


def _png_bytes(rgba: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _mask_png_bytes(mask: np.ndarray) -> bytes:
    values = np.asarray(mask, dtype=np.uint8)
    rgba = np.empty(values.shape + (4,), dtype=np.uint8)
    # The carrier layer must be white RGB with the calculated mask in alpha.
    # Photopea loads that alpha as the source selection for the linked raster
    # mask; putting the values in RGB would create the wrong transparency
    # semantics after copy/paste.
    rgba[..., :3] = 255
    rgba[..., 3] = values
    return _png_bytes(rgba)


class PhotopeaLiveApiAdapter:
    """Request PSD construction from a Photopea Live API outer environment."""

    supports_variants = True
    supports_photopea_session = True

    def __init__(self, api_url: str, token: str | None = None, timeout: float = 300.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.round_trip_verified = False

    def export(
        self,
        source: np.ndarray,
        artwork: np.ndarray,
        mask: np.ndarray,
        variants: Mapping[str, np.ndarray] | None = None,
        mask_plan: Mapping[str, object] | object | None = None,
    ) -> bytes:
        if mask_plan is not None:
            return self.export_session(source, mask_plan)
        boundary = "----photopea-live-api"
        fields = {
            "request_json": json.dumps({
                "layers": ["SOURCE BACKUP", "RESTORED", "WITH GAPS", "WORKING MASK", "BLACK", "WHITE", "GRAY", "NAVY", "BLUE JEAN #6E8EAE"],
                "format": "psd:true",
            }),
        }
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
        opaque_artwork = np.asarray(artwork, dtype=np.uint8).copy()
        opaque_artwork[..., 3] = 255
        for name, filename, content in (
            ("source", "source.png", _png_bytes(source)),
            ("artwork", "artwork.png", _png_bytes(opaque_artwork)),
            ("mask", "mask.png", _mask_png_bytes(mask)),
        ):
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(), b"Content-Type: image/png\r\n\r\n", content, b"\r\n"])
        for variant_name in ("artistic", "conservative"):
            variant = None if variants is None else variants.get(variant_name)
            if variant is None:
                continue
            opaque_variant = np.asarray(variant, dtype=np.uint8).copy()
            opaque_variant[..., 3] = 255
            for name, filename, content in (
                (f"variant_{variant_name}", f"{variant_name}.png", _png_bytes(opaque_variant)),
                (f"mask_{variant_name}", f"{variant_name}_mask.png", _mask_png_bytes(variant[..., 3])),
            ):
                parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(), b"Content-Type: image/png\r\n\r\n", content, b"\r\n"])
        parts.append(f"--{boundary}--\r\n".encode())
        return self._post_multipart(boundary, parts)

    def export_session(self, source: np.ndarray, mask_plan: Mapping[str, object] | object) -> bytes:
        """Create the mask and editable layers inside one Photopea document."""
        boundary = "----photopea-live-api"
        plan = asdict(mask_plan) if is_dataclass(mask_plan) else dict(mask_plan)
        fields = {
            "request_json": json.dumps({"format": "psd:true", "workflow": "photopea_mask_session"}),
            "mask_plan": json.dumps(plan),
        }
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
        parts.extend([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="source"; filename="source.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            _png_bytes(source),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        return self._post_multipart(boundary, parts)

    def _post_multipart(self, boundary: str, parts: list[bytes]) -> bytes:
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/octet-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urlopen(Request(f"{self.api_url}/v1/photopea/export", data=b"".join(parts), headers=headers, method="POST"), timeout=self.timeout) as response:
                payload = response.read()
                headers = getattr(response, "headers", {})
                self.round_trip_verified = headers.get("X-Photopea-Roundtrip") == "verified"
        except (HTTPError, URLError, TimeoutError) as exc:
            raise PhotopeaLiveApiUnavailable(str(exc)) from exc
        if not payload.startswith(b"8BPS"):
            raise PhotopeaLiveApiUnavailable("Photopea Live API adapter returned non-PSD data")
        return payload
