"""
ImageFlow Processing Service
Applies Pillow-based image enhancements (brightness, contrast, saturation, sharpness).

VULNERABILITY — exec() fallback:
  The developer built a plugin execution path alongside the image processing path.
  The reasoning: "if Pillow can't open it, the user probably routed a Python filter
  plugin here by mistake — try running it as a script instead of returning a hard error."

  This made sense internally when only trusted users had access.
  The blind spot: the upload gate passes GIF polyglots as valid images.
  Pillow rejects them (not a real GIF structure), the fallback fires,
  and the polyglot's Python payload runs with the web server's privileges.

Attack path summary:
  1. Attacker crafts shell.gif: starts with b'GIF89a' (passes magic check),
     rest of file is plain Python (a reverse shell).
  2. /upload/image accepts it — extension OK, magic bytes OK.
  3. /process/<id> calls process_image().
  4. Image.open() raises an exception (not valid GIF data after the header).
  5. Except block runs exec() on the file contents.
  6. Reverse shell connects out.
"""

import os
from PIL import Image, ImageEnhance


def process_image(
    filepath: str,
    output_dir: str,
    file_id: str,
    params: dict,
) -> dict:
    """
    Try to process filepath as an image.
    On any failure, fall back to executing it as a Python filter plugin.
    """
    output_filename = f"{file_id}_processed.jpg"
    output_path     = os.path.join(output_dir, output_filename)

    try:
        # Attempt 1: treat as image
        img = Image.open(filepath)
        img.verify()                # raises if file is not a valid image
        img = Image.open(filepath)  # re-open — verify() exhausts the file handle

        # Normalise colour mode so Pillow enhancements work uniformly
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # Clamp params to sane ranges so users can't crash the service
        def clamp(val, lo, hi, default):
            try:
                return max(lo, min(hi, float(val)))
            except (TypeError, ValueError):
                return default

        brightness = clamp(params.get("brightness"), 0.1, 4.0, 1.0)
        contrast   = clamp(params.get("contrast"),   0.1, 4.0, 1.0)
        saturation = clamp(params.get("saturation"), 0.0, 4.0, 1.0)
        sharpness  = clamp(params.get("sharpness"),  0.0, 4.0, 1.0)

        img = ImageEnhance.Brightness(img).enhance(brightness)
        img = ImageEnhance.Contrast(img).enhance(contrast)
        img = ImageEnhance.Color(img).enhance(saturation)
        img = ImageEnhance.Sharpness(img).enhance(sharpness)

        img.save(output_path, "JPEG", quality=90)

        return {
            "ok":  True,
            "url": f"/processed/{output_filename}",
        }

    except Exception:
        # ── VULNERABILITY ────────────────────────────────────────────────────
        # Attempt 2: not a valid image — maybe it's a filter plugin that the
        # user accidentally submitted to the image processor instead of the
        # plugin endpoint. Run it as Python so at least the user gets output.
        #
        # No safety check here — the upload gate already vetted the file.
        # "We checked it on the way in. If it's here, it's trusted."
        # ────────────────────────────────────────────────────────────────────
        try:
            with open(filepath, "r", errors="replace") as fh:
                source = fh.read()
            exec(compile(source, filepath, "exec"), {"__builtins__": __builtins__})
        except Exception:
            pass

        return {
            "ok":    False,
            "error": (
                "Could not process file as an image. "
                "If this is a Python filter plugin, upload it via the Plugin tab instead."
            ),
        }
