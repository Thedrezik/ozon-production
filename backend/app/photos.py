"""Validated image processing; never retain phone originals or metadata."""
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def compress_image(content: bytes, mime: str) -> tuple[bytes, int, int]:
    if mime not in TYPES:
        raise ValueError("Unsupported image type")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != TYPES[mime] or image.width * image.height > 20_000_000:
                    raise ValueError("Invalid image type or dimensions")
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((1600, 1600))
                output = BytesIO()
                image.save(output, format="JPEG", quality=80, optimize=True)
                return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError("Invalid image") from error
