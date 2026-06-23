#!/usr/bin/env python3
"""Compress images in a directory below a target size.

Generated images are written to an ``output`` subdirectory. Source images are
moved to an ``original`` subdirectory only after a smaller output file has been
successfully created.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageOps, features
except ModuleNotFoundError:  # pragma: no cover - dependency guard
    Image = None
    ImageOps = None
    features = None


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
SKIP_DIRS = {"original", "output"}
DEFAULT_MAX_BYTES = 50_000
DEFAULT_FORMAT = "jpeg"
QUALITY_STEPS = (85, 75, 65, 55, 45, 35, 25, 15)
MIN_DIMENSION = 32
SCALE_FACTOR = 0.85


@dataclass
class Result:
    source: Path
    output: Path | None
    original: Path | None
    status: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compress image files from a directory to below a size limit, "
            "then move sources to an original/ folder and generated files to "
            "an output/ folder."
        )
    )
    parser.add_argument("directory", type=Path, help="Directory containing images.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Maximum generated file size. Default: {DEFAULT_MAX_BYTES}.",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "webp", "jpeg"),
        default=DEFAULT_FORMAT,
        help=(
            "Generated image format. Default: jpeg, which works in Google "
            "Docs. Use auto to prefer WebP."
        ),
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Process image files recursively. Default: true.",
    )
    return parser.parse_args()


def require_pillow() -> None:
    if Image is None:
        print(
            "Pillow is required. Install it with: python3 -m pip install Pillow",
            file=sys.stderr,
        )
        raise SystemExit(2)


def is_inside_managed_dir(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in SKIP_DIRS


def find_images(directory: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in directory.glob(pattern)
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and not is_inside_managed_dir(path, directory)
    )


def output_format(requested: str, has_alpha: bool) -> tuple[str, str]:
    if requested == "webp":
        if not features.check("webp"):
            raise RuntimeError("This Pillow build does not support WebP output.")
        return "WEBP", ".webp"
    if requested == "jpeg":
        if has_alpha:
            return "JPEG", ".jpg"
        return "JPEG", ".jpg"
    if features.check("webp"):
        return "WEBP", ".webp"
    if has_alpha:
        raise RuntimeError(
            "This Pillow build does not support WebP output, which is needed "
            "to preserve transparent images. Re-run with --format jpeg to "
            "flatten transparency to white."
        )
    return "JPEG", ".jpg"


def image_has_alpha(image: Image.Image) -> bool:
    return image.mode in {"LA", "PA", "RGBA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def prepare_image(image: Image.Image, save_format: str, has_alpha: bool) -> Image.Image:
    if save_format == "JPEG":
        if has_alpha:
            background = Image.new("RGB", image.size, "white")
            alpha = image.convert("RGBA").getchannel("A")
            background.paste(image.convert("RGBA"), mask=alpha)
            return background
        return image.convert("RGB")

    if save_format == "WEBP":
        return image.convert("RGBA" if has_alpha else "RGB")

    return image


def encode_image(image: Image.Image, save_format: str, quality: int) -> bytes:
    buffer = io.BytesIO()
    save_args = {"format": save_format, "optimize": True}
    if save_format in {"JPEG", "WEBP"}:
        save_args["quality"] = quality
        save_args["method"] = 6 if save_format == "WEBP" else None
    save_args = {key: value for key, value in save_args.items() if value is not None}
    image.save(buffer, **save_args)
    return buffer.getvalue()


def compressed_bytes(
    source: Path,
    max_bytes: int,
    requested_format: str,
) -> tuple[bytes, str]:
    with Image.open(source) as opened:
        opened.seek(0)
        image = ImageOps.exif_transpose(opened)
        has_alpha = image_has_alpha(image)
        save_format, extension = output_format(requested_format, has_alpha)

        width, height = image.size
        current = prepare_image(image, save_format, has_alpha)

        while width >= MIN_DIMENSION and height >= MIN_DIMENSION:
            for quality in QUALITY_STEPS:
                data = encode_image(current, save_format, quality)
                if len(data) <= max_bytes:
                    return data, extension

            width = max(MIN_DIMENSION, int(width * SCALE_FACTOR))
            height = max(MIN_DIMENSION, int(height * SCALE_FACTOR))
            if current.size == (width, height):
                break
            current = current.resize((width, height), Image.Resampling.LANCZOS)

    raise RuntimeError(f"could not compress below {max_bytes} bytes")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"could not find an available path for {path}")


def process_image(
    source: Path,
    root: Path,
    output_dir: Path,
    original_dir: Path,
    max_bytes: int,
    requested_format: str,
) -> Result:
    relative = source.relative_to(root)
    output_parent = output_dir / relative.parent
    original_parent = original_dir / relative.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    original_parent.mkdir(parents=True, exist_ok=True)

    try:
        data, extension = compressed_bytes(source, max_bytes, requested_format)
    except Exception as exc:  # noqa: BLE001 - report and continue per file
        return Result(source, None, None, "failed", str(exc))

    source_size = source.stat().st_size
    output_path = unique_path(output_parent / f"{source.stem}{extension}")
    original_path = unique_path(original_parent / source.name)

    output_path.write_bytes(data)
    if output_path.stat().st_size > max_bytes:
        output_path.unlink(missing_ok=True)
        return Result(
            source,
            None,
            None,
            "failed",
            f"generated file exceeded {max_bytes} bytes",
        )

    shutil.move(str(source), str(original_path))
    return Result(
        source,
        output_path,
        original_path,
        "ok",
        f"{source_size} -> {output_path.stat().st_size} bytes",
    )


def main() -> int:
    args = parse_args()

    root = args.directory.expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    if args.max_bytes <= 0:
        print("--max-bytes must be greater than 0", file=sys.stderr)
        return 2

    require_pillow()

    output_dir = root / "output"
    original_dir = root / "original"
    output_dir.mkdir(exist_ok=True)
    original_dir.mkdir(exist_ok=True)

    images = find_images(root, args.recursive)
    if not images:
        print(f"No image files found in {root}")
        return 0

    results = [
        process_image(
            image,
            root,
            output_dir,
            original_dir,
            args.max_bytes,
            args.format,
        )
        for image in images
    ]

    for result in results:
        relative_source = result.source.relative_to(root)
        if result.status == "ok":
            print(f"OK     {relative_source} -> {result.output.relative_to(root)} ({result.detail})")
        else:
            print(f"FAILED {relative_source}: {result.detail}")

    failed = sum(result.status != "ok" for result in results)
    completed = len(results) - failed
    print(f"Done: {completed} compressed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
