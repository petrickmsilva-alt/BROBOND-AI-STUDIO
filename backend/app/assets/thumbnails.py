"""PR013 — V4.0.1: image probing and thumbnail rendering.

Pillow is imported lazily (module level), matching the convention already
used by `app.preprocessing`: the dependency is pinned in requirements.txt,
but importing it at the top of a module that the API imports eagerly would
slow every cold start for a feature used on a fraction of requests.

Honesty rule baked into the API surface: these helpers return ``None``
whenever the bytes cannot be decoded or thumbnailed. They never raise for
corrupt input and they never return dimensions that were not actually
read. The service layer translates the ``None`` into "no thumbnail" /
"unknown resolution", which the UI renders as a film-kind tile and an em
dash — never as an invented frame or a fake number.

Video is deliberately out of scope: extracting a poster frame from MP4/MOV
requires ffmpeg (listed as absent in docs/LIMITATIONS.md). Claiming a
poster we did not create is exactly the kind of fabrication this
repository guards against in test_frontend_honesty.py.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

#: Long edge of the library thumbnail, in pixels. Small enough that the
#: grid paints instantly from the local adapter, large enough that the
#: lightbox backdrop still reads as the asset before the full image loads.
THUMBNAIL_MAX_SIDE_PX = 320

#: The thumbnail container. PNG keeps alpha and is lossless at this size;
#: the Render Engine made the same choice for its render thumbnails
#: (`render/asset_pipeline.py`), so both libraries behave identically.
THUMBNAIL_FORMAT = "PNG"


@dataclass(frozen=True)
class ImageProbe:
    """What Pillow could actually read from the bytes."""

    width: int
    height: int
    format: str  # "PNG" | "JPEG" | "WEBP" | ...


def _load_image(data: bytes):
    """Open bytes as an image, or return None when they are not one."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is pinned; defensive
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:  # noqa: BLE001 - any decode failure means "not an image"
        return None
    return image


def probe_image(data: bytes) -> ImageProbe | None:
    """Read real dimensions from image bytes. ``None`` = could not decode."""
    image = _load_image(data)
    if image is None:
        return None
    return ImageProbe(width=image.width, height=image.height, format=image.format or "")


def build_image_thumbnail(data: bytes, max_side: int = THUMBNAIL_MAX_SIDE_PX) -> bytes | None:
    """Render a PNG thumbnail of at most ``max_side`` on the long edge.

    Returns ``None`` when the input is not a decodable image. The aspect
    ratio is preserved; images already smaller than the box are thumbnailed
    anyway so the stored derivative always has the declared format and the
    strip of EXIF/ancillary chunks that re-encoding implies.
    """
    image = _load_image(data)
    if image is None:
        return None
    try:
        from PIL import Image, ImageOps

        # EXIF orientation is honoured before scaling: a sideways phone
        # photograph must not get a sideways thumbnail.
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info or image.mode == "P" else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, format=THUMBNAIL_FORMAT, optimize=True)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 - a bad resize must not fail the upload
        return None
