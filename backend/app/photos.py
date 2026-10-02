"""Validated image processing; never retain phone originals or metadata."""
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
WEBP_MAX_PIXELS = 10_000_000


def _webp_dimensions(content: bytes) -> tuple[int, int]:
    """Size guard before Pillow allocates WebP canvases; Pillow validates the image.

    https://developers.google.com/speed/webp/docs/riff_container
    """
    kind = content[12:16]
    size = int.from_bytes(content[16:20], "little")
    if kind == b"VP8L" and len(content) >= 25 and size >= 5 and content[20] == 0x2F:
        bits = int.from_bytes(content[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if len(content) >= 30 and size >= 10:
        if kind == b"VP8X":
            return int.from_bytes(content[24:27], "little") + 1, int.from_bytes(content[27:30], "little") + 1
        if kind == b"VP8 " and content[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(content[26:28], "little") & 0x3FFF, int.from_bytes(content[28:30], "little") & 0x3FFF
    raise ValueError("Invalid WebP image")


def compress_image(content: bytes, mime: str) -> tuple[bytes, int, int]:
    if mime not in TYPES:
        raise ValueError("Unsupported image type")
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        width, height = _webp_dimensions(content)
        if mime != "image/webp" or not width or not height or width * height > WEBP_MAX_PIXELS:
            raise ValueError("WebP must be at most 10 million pixels")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                pixel_limit = WEBP_MAX_PIXELS if image.format == "WEBP" else 20_000_000
                if image.format != TYPES[mime] or image.width * image.height > pixel_limit:
                    raise ValueError("Invalid image type or dimensions")
                # JPEG can downsample while decoding. Validate original dimensions
                # first, and resize before RGB conversion to avoid full-size copies.
                image.draft("RGB", (1600, 1600))
                image.load()
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail((1600, 1600))
                image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=80, optimize=True)
                return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError("Invalid image") from error
