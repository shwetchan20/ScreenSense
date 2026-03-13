from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from PIL import Image


def encode_png_base64(frame_rgb: np.ndarray) -> str:
    image = Image.fromarray(frame_rgb)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def decode_png_base64(data: str) -> np.ndarray:
    png_bytes = base64.b64decode(data.encode("ascii"))
    image = Image.open(BytesIO(png_bytes)).convert("RGB")
    return np.array(image)

