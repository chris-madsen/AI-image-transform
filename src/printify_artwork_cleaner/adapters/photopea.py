from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image


class PhotopeaLiveApiUnavailable(RuntimeError):
    """The external Photopea Live outer environment is unavailable."""


def _png_bytes(rgba: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


class PhotopeaLiveApiAdapter:
    """Request PSD construction from a Photopea Live API outer environment."""

    def __init__(self, api_url: str, token: str | None = None, timeout: float = 180.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def export(self, source: np.ndarray, artwork: np.ndarray, mask: np.ndarray) -> bytes:
        boundary = "----photopea-live-api"
        fields = {
            "request_json": json.dumps({
                "layers": ["SOURCE BACKUP", "WORKING ART", "WORKING MASK", "BLACK", "WHITE", "GRAY", "NAVY", "BLUE JEAN #6E8EAE"],
                "format": "psd:true",
            }),
        }
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
        for name, filename, content in (
            ("source", "source.png", _png_bytes(source)),
            ("artwork", "artwork.png", _png_bytes(artwork)),
            ("mask", "mask.png", _png_bytes(np.repeat(mask[..., None], 4, axis=-1))),
        ):
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(), b"Content-Type: image/png\r\n\r\n", content, b"\r\n"])
        parts.append(f"--{boundary}--\r\n".encode())
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/octet-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urlopen(Request(f"{self.api_url}/v1/photopea/export", data=b"".join(parts), headers=headers, method="POST"), timeout=self.timeout) as response:
                payload = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise PhotopeaLiveApiUnavailable(str(exc)) from exc
        if not payload.startswith(b"8BPS"):
            raise PhotopeaLiveApiUnavailable("Photopea Live API adapter returned non-PSD data")
        return payload
