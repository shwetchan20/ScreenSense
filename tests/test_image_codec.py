import numpy as np

from screensense.inference.image_codec import decode_png_base64, encode_png_base64


def test_encode_decode_png_base64_roundtrip_shape() -> None:
    frame = np.zeros((12, 8, 3), dtype=np.uint8)
    frame[2, 3] = [255, 10, 20]
    encoded = encode_png_base64(frame)
    decoded = decode_png_base64(encoded)
    assert decoded.shape == frame.shape
    assert int(decoded[2, 3, 0]) == 255

