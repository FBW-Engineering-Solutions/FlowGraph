"""Workflow nodes that read, transform, write, and convert Pillow images."""

import gzip
import io
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from Muscat.MeshTools.ConstantRectilinearMeshTools import CreateConstantRectilinearMesh
from PIL import Image as PillowImage
from PIL import UnidentifiedImageError
from PIL.Image import Image

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import FLOAT, IMAGE, IMAGEJ, MESH_DOCUMENT, ParameterKind

LOGGER = logging.getLogger(__name__)


class ImageLoadError(RuntimeError):
    """Raised when a selected image file cannot be loaded by Pillow."""


class ImageWriteError(RuntimeError):
    """Raised when a Pillow image cannot be written to a destination."""


class ImageMeshError(RuntimeError):
    """Raised when a Pillow image cannot be converted into a mesh document."""


class ImageOperationError(RuntimeError):
    """Raised when a Pillow image transformation cannot be completed."""


class ImageJConversionError(RuntimeError):
    """Raised when a Pillow image cannot be converted to an ImageJ NumPy array."""


class ImageFluencyError(RuntimeError):
    """Raised when image fluency metrics cannot be computed."""


def _require_image(inputs: Mapping[str, Any]) -> Image:
    """Return the required Pillow image input or raise an actionable error."""
    image = inputs["image"]
    if not isinstance(image, Image):
        raise ImageOperationError("Image input must be a PIL.Image.Image instance")
    return image


def _pillow_to_imagej(
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Convert a Pillow image to a detached NumPy array suitable for ImageJ."""
    image = inputs["image"]
    if not isinstance(image, Image):
        raise ImageJConversionError("Image input must be a PIL.Image.Image instance")
    return {"image": np.array(image, copy=True)}


def _metric_channels(image: Image) -> tuple[np.ndarray, ...]:
    """Return image channels as float arrays, ignoring alpha channels."""
    if image.mode == "L":
        return (np.asarray(image, dtype=np.float64),)
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    return tuple(rgb[:, :, index] for index in range(3))


def _rms_contrast(image: Image) -> float:
    """Return the upstream imagefluency weighted per-channel RMS contrast."""
    channels = _metric_channels(image)
    weights = (1.0,) if len(channels) == 1 else (0.2989, 0.5870, 0.1140)
    return float(
        sum(weight * np.std(channel / 255.0, ddof=1) for weight, channel in zip(weights, channels))
    )


def _bmp_bytes(image: Image) -> bytes:
    """Serialize an image to an uncompressed BMP for complexity measurement."""
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    return buffer.getvalue()


def _compression_complexity(image: Image, rotate: bool) -> float:
    """Return gzip-compressed BMP size divided by uncompressed BMP size."""
    source = image if image.mode in {"L", "RGB"} else image.convert("RGB")
    original = _bmp_bytes(source)
    compressed_sizes = [len(gzip.compress(original, compresslevel=9, mtime=0))]
    if rotate:
        compressed_sizes.append(
            len(gzip.compress(_bmp_bytes(source.rotate(90, expand=True)), compresslevel=9, mtime=0))
        )
    return float(min(compressed_sizes) / len(original))


def _normalise_for_fft(channel: np.ndarray) -> np.ndarray:
    """Convert a channel to finite floating-point values for the FFT."""
    values = np.asarray(channel, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ImageFluencyError("Image contains non-finite pixel values")
    return values


def _self_similarity_channel(channel: np.ndarray, full: bool) -> float:
    """Return the imagefluency-compatible log-log power-spectrum score."""
    height, width = channel.shape
    if min(height, width) < 22:
        raise ImageFluencyError(
            "Self-similarity requires an image with at least 22 pixels in both dimensions"
        )
    size = min(height, width)
    if size % 2:
        size -= 1
    square = (
        PillowImage.fromarray(np.asarray(channel, dtype=np.float32), mode="F").resize(
            # Historical OpenImageR releases called this operation bilinear, but
            # their 1536-to-1024 output is pixel-equivalent to Pillow's BOX filter.
            (size, size),
            resample=PillowImage.Resampling.BOX,
        )
        if height != width
        else channel
    )
    values = _normalise_for_fft(np.asarray(square, dtype=np.float64))
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(values))) ** 2
    yy, xx = np.indices(spectrum.shape)
    radius = np.rint(np.hypot(xx - size / 2, yy - size / 2)).astype(np.int32)
    max_radius = size // 2
    power = np.array(
        [spectrum[radius == radius_value].mean() for radius_value in range(1, max_radius + 1)],
        dtype=np.float64,
    )
    start, stop = (1, max_radius) if full else (10, min(max_radius, 256))
    if stop < start or np.any(power[start - 1 : stop] <= 0):
        raise ImageFluencyError("Image does not contain enough valid spatial frequencies")
    frequencies = np.arange(start, stop + 1, dtype=np.float64)
    slope = float(np.polyfit(np.log(frequencies), np.log(power[start - 1 : stop]), 1)[0])
    return float(-abs(slope + 2.0))


def _mirror_similarity(channel: np.ndarray, axis: str, shift_range: float) -> float:
    """Return maximum absolute half-image correlation around shifted mirror axes."""
    array = channel if axis == "vertical" else channel.T
    width = array.shape[1]
    if width < 4:
        raise ImageFluencyError("Symmetry requires at least 4 pixels on both image dimensions")
    maximum = 0.0
    for shift in range(int(np.floor(width * shift_range)) + 1):
        for view in (array[:, : width - shift], array[:, shift:]):
            half = view.shape[1]
            left = view[:, : half // 2].ravel()
            right = view[:, -(half // 2) :][:, ::-1].ravel()
            if np.std(left, ddof=1) == 0 or np.std(right, ddof=1) == 0:
                raise ImageFluencyError("Symmetry cannot be computed from a constant image half")
            maximum = max(maximum, abs(float(np.corrcoef(left, right)[0, 1])))
    return maximum


def _image_fluency_metrics(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Compute fluency metrics and directional mirror symmetry."""
    image = _require_image(inputs)
    shift_range = parameters["symmetry_shift_range"]
    if (
        isinstance(shift_range, bool)
        or not isinstance(shift_range, (int, float))
        or not 0 <= shift_range <= 1
    ):
        raise ImageFluencyError("Symmetry shift range must be a number between 0 and 1")
    channels = _metric_channels(image)
    weights = (1.0,) if len(channels) == 1 else (0.2989, 0.5870, 0.1140)
    contrast = _rms_contrast(image)
    self_similarity = sum(
        weight * _self_similarity_channel(channel, parameters["self_similarity_full"])
        for weight, channel in zip(weights, channels)
    )

    if _exec_context is None or  "symmetry_vertical" in _exec_context.connected_output_ports:
        symmetry_vertical = sum(
            weight * _mirror_similarity(channel, "vertical", float(shift_range))
            for weight, channel in zip(weights, channels)
        )
    else:
        symmetry_vertical = np.nan

    symmetry_horizontal = sum(
        weight * _mirror_similarity(channel, "horizontal", float(shift_range))
        for weight, channel in zip(weights, channels)
    )
    return {
        "contrast": contrast,
        "complexity": _compression_complexity(image, parameters["complexity_rotate"]),
        "self_similarity": float(self_similarity),
        "symmetry_vertical": float(symmetry_vertical),
        "symmetry_horizontal": float(symmetry_horizontal),
    }


def _positive_integer(parameters: Mapping[str, Any], name: str) -> int:
    """Return a positive integer parameter or raise an actionable operation error."""
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImageOperationError(
            f"{name.replace('_', ' ').capitalize()} must be a positive integer"
        )
    return value


def _nonnegative_integer(parameters: Mapping[str, Any], name: str) -> int:
    """Return a non-negative integer parameter or raise an actionable operation error."""
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ImageOperationError(
            f"{name.replace('_', ' ').capitalize()} must be a non-negative integer"
        )
    return value


def _validate_source(parameters: Mapping[str, Any]) -> Path:
    """Return an existing image source path or raise an actionable load error."""
    source = Path(parameters["path"]).expanduser()
    if not source.is_file():
        raise ImageLoadError(f"Image file does not exist or is not a file: {source}")
    return source


def _validate_destination(parameters: Mapping[str, Any]) -> Path:
    """Return a writable image destination path or raise an actionable write error."""
    destination = Path(parameters["filename"]).expanduser()
    if not destination.name:
        raise ImageWriteError("Image filename must not be empty")
    if not destination.suffix:
        raise ImageWriteError(
            f"Image filename has no extension; Pillow cannot select an output format: {destination}"
        )
    if not destination.parent.is_dir():
        raise ImageWriteError(
            f"Image output directory does not exist or is not a directory: {destination.parent}"
        )
    return destination


def _read_image(
    _inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Load an image with Pillow and detach its pixel data from the source file."""
    source = _validate_source(parameters)
    try:
        with PillowImage.open(source) as image:
            result = image.copy()
    except (OSError, UnidentifiedImageError) as error:
        LOGGER.exception("Pillow failed while loading %s", source)
        raise ImageLoadError(f"Pillow could not load '{source}': {error}") from error

    LOGGER.info("Pillow loaded image %s (%s, %s)", source, result.mode, result.size)
    return {"image": result}


def _write_image(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Write a Pillow image using the format inferred from its destination extension."""
    destination = _validate_destination(parameters)
    image = inputs["image"]
    if not isinstance(image, Image):
        raise ImageWriteError("Image input must be a PIL.Image.Image instance")

    try:
        image.save(destination)
    except (OSError, ValueError) as error:
        LOGGER.exception("Pillow failed while writing %s", destination)
        raise ImageWriteError(f"Pillow could not write '{destination}': {error}") from error

    LOGGER.info("Pillow wrote image to %s", destination.resolve())
    return {}


def _resize_image(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Resize an image to a requested width and height using Lanczos resampling."""
    image = _require_image(inputs)
    width = _positive_integer(parameters, "width")
    height = _positive_integer(parameters, "height")
    result = image.resize((width, height), PillowImage.Resampling.LANCZOS)
    LOGGER.info("Resized Pillow image from %s to %s", image.size, result.size)
    return {"image": result}


def _crop_image(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Crop an image to an in-bounds box described by left, top, right, and bottom."""
    image = _require_image(inputs)
    left = _nonnegative_integer(parameters, "left")
    top = _nonnegative_integer(parameters, "top")
    right = _positive_integer(parameters, "right")
    bottom = _positive_integer(parameters, "bottom")
    width, height = image.size
    if left >= right or top >= bottom:
        raise ImageOperationError(
            "Crop right and bottom coordinates must exceed left and top coordinates"
        )
    if right > width or bottom > height:
        raise ImageOperationError(
            f"Crop box ({left}, {top}, {right}, {bottom}) exceeds image bounds {image.size}"
        )
    result = image.crop((left, top, right, bottom))
    LOGGER.info(
        "Cropped Pillow image %s to box (%s, %s, %s, %s)", image.size, left, top, right, bottom
    )
    return {"image": result}


def _rotate_image(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Rotate an image counter-clockwise by the requested number of degrees."""
    image = _require_image(inputs)
    angle = parameters["angle"]
    if isinstance(angle, bool) or not isinstance(angle, (int, float)):
        raise ImageOperationError("Angle must be a number of degrees")
    expand = parameters["expand"]
    if not isinstance(expand, bool):
        raise ImageOperationError("Expand output must be a Boolean value")
    result = image.rotate(angle, resample=PillowImage.Resampling.BICUBIC, expand=expand)
    LOGGER.info("Rotated Pillow image %s by %s degrees (expand=%s)", image.size, angle, expand)
    return {"image": result}


def _convert_image_mode(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Convert an image to one of the supported common Pillow color modes."""
    image = _require_image(inputs)
    mode = parameters["mode"]
    if mode not in _COLOR_MODE_OPTIONS:
        raise ImageOperationError(f"Unsupported target color mode: {mode!r}")
    result = image.convert(mode)
    LOGGER.info("Converted Pillow image from %s to %s", image.mode, result.mode)
    return {"image": result}


def _node_colors(image: Image) -> np.ndarray:
    """Return image colors in the node order used by Muscat's rectilinear mesh.

    The output has one row per image pixel and one to four columns according to
    the L, LA, RGB, or RGBA channel convention.
    """
    normalized = image if image.mode in {"L", "LA", "RGB", "RGBA"} else image.convert("RGBA")
    pixels = np.asarray(normalized)
    if pixels.ndim == 2:
        pixels = pixels[..., np.newaxis]

    return np.ascontiguousarray(pixels.transpose(1, 0, 2).reshape(-1, pixels.shape[-1]))


def _image_to_mesh(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Convert a Pillow image into a structured Muscat mesh with a ``Colors`` field."""
    image = inputs["image"]
    if not isinstance(image, Image):
        raise ImageMeshError("Image input must be a PIL.Image.Image instance")

    width, height = image.size
    if width < 1 or height < 1:
        raise ImageMeshError("Image dimensions must both be at least one pixel")

    storeOnNodeFields = parameters.get("storeOnNodeFields", True)
    if not storeOnNodeFields:
        width += 1
        height += 1

    mesh = CreateConstantRectilinearMesh(
        dimensions=[width, height], origin=[0.0, 0.0], spacing=[1.0, 1.0]
    )
    colors = _node_colors(image)

    if parameters.get("storeOnNodeFields", True):
        mesh.nodeFields["Colors"] = colors
    else:
        mesh.elemFields["Colors"] = colors

    LOGGER.info(
        "Converted Pillow image (%s, %s) to a mesh with Colors on %s fields",
        image.mode,
        image.size,
        "node" if parameters.get("storeOnNodeFields", True) else "element",
    )
    return {"mesh": MeshDocument(mesh=mesh)}


_COLOR_MODE_OPTIONS = {
    "1": "1-bit pixels",
    "L": "Grayscale",
    "LA": "Grayscale with alpha",
    "RGB": "Red, green, blue",
    "RGBA": "Red, green, blue, alpha",
    "CMYK": "Cyan, magenta, yellow, black",
    "HSV": "Hue, saturation, value",
}


READ_IMAGE = NodeDefinition(
    id="read-image",
    icon="mdi-image-arrow-down-outline",
    label="Read Image (Pillow)",
    description="Loads an image file into a Pillow image.",
    ports=(PortDefinition("image", PortDirection.OUTPUT, IMAGE, "Image"),),
    executor=_read_image,
    parameters=(
        ParameterDefinition(
            "path",
            ParameterKind.FILE,
            "File path",
            "",
            "/path/to/image",
            file_patterns=("*.bmp", "*.gif", "*.jpeg", "*.jpg", "*.png", "*.tiff", "*.webp"),
        ),
    ),
)


PILLOW_TO_IMAGEJ = NodeDefinition(
    id="pillow-to-imagej",
    icon="mdi-image-sync-outline",
    label="Pillow To ImageJ",
    description="Converts a Pillow image to a detached NumPy array for ImageJ-compatible processing.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Pillow image"),
        PortDefinition("image", PortDirection.OUTPUT, IMAGEJ, "ImageJ NumPy array"),
    ),
    executor=_pillow_to_imagej,
)


WRITE_IMAGE = NodeDefinition(
    id="write-image",
    icon="mdi-image-arrow-up-outline",
    label="Write Image (Pillow)",
    description="Writes a Pillow image using the output filename extension.",
    ports=(PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),),
    executor=_write_image,
    parameters=(
        ParameterDefinition(
            "filename",
            ParameterKind.FILE,
            "Filename",
            "",
            "/path/to/image.png",
            file_patterns=("*.bmp", "*.gif", "*.jpeg", "*.jpg", "*.png", "*.tiff", "*.webp"),
        ),
    ),
)


RESIZE_IMAGE = NodeDefinition(
    id="resize-image",
    icon="mdi-arrow-expand-all",
    label="Resize Image",
    description="Resizes a Pillow image to a target width and height.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),
        PortDefinition("image", PortDirection.OUTPUT, IMAGE, "Image"),
    ),
    executor=_resize_image,
    parameters=(
        ParameterDefinition("width", ParameterKind.INTEGER, "Width", 1),
        ParameterDefinition("height", ParameterKind.INTEGER, "Height", 1),
    ),
)


CROP_IMAGE = NodeDefinition(
    id="crop-image",
    icon="mdi-crop",
    label="Crop Image",
    description="Crops a Pillow image to an in-bounds rectangular region.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),
        PortDefinition("image", PortDirection.OUTPUT, IMAGE, "Image"),
    ),
    executor=_crop_image,
    parameters=(
        ParameterDefinition("left", ParameterKind.INTEGER, "Left", 0),
        ParameterDefinition("top", ParameterKind.INTEGER, "Top", 0),
        ParameterDefinition("right", ParameterKind.INTEGER, "Right", 1),
        ParameterDefinition("bottom", ParameterKind.INTEGER, "Bottom", 1),
    ),
)


ROTATE_IMAGE = NodeDefinition(
    id="rotate-image",
    icon="mdi-rotate-right",
    label="Rotate Image",
    description="Rotates a Pillow image counter-clockwise by an angle in degrees.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),
        PortDefinition("image", PortDirection.OUTPUT, IMAGE, "Image"),
    ),
    executor=_rotate_image,
    parameters=(
        ParameterDefinition("angle", ParameterKind.FLOAT, "Angle (degrees)", 0.0),
        ParameterDefinition("expand", ParameterKind.BOOLEAN, "Expand output", True, port=False),
    ),
)


CONVERT_IMAGE_MODE = NodeDefinition(
    id="convert-image-mode",
    icon="mdi-palette-outline",
    label="Convert Image Mode",
    description="Converts a Pillow image to a selected color mode.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),
        PortDefinition("image", PortDirection.OUTPUT, IMAGE, "Image"),
    ),
    executor=_convert_image_mode,
    parameters=(
        ParameterDefinition(
            "mode",
            ParameterKind.STR_SELECT,
            "Color mode",
            "RGB",
            options=tuple(
                ParameterOption(value, label) for value, label in _COLOR_MODE_OPTIONS.items()
            ),
            port=False,
        ),
    ),
)


IMAGE_TO_MESH = NodeDefinition(
    id="image-to-mesh",
    icon="mdi-image-filter-center-focus-weak",
    label="Image To Mesh",
    description="Converts a Pillow image to a structured mesh with a Colors field.",
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Image"),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
    ),
    executor=_image_to_mesh,
    parameters=(
        ParameterDefinition(
            "storeOnNodeFields",
            ParameterKind.BOOLEAN,
            "Store colors on node fields",
            True,
            port=False,
        ),
    ),
)


IMAGE_FLUENCY_METRICS = NodeDefinition(
    id="image-fluency-metrics",
    icon="mdi-image-filter-vintage",
    label="Image Fluency Metrics",
    description=(
        "Computes imagefluency-style contrast, compression complexity, self-similarity, "
        "and vertical/horizontal mirror symmetry from a Pillow image."
    ),
    ports=(
        PortDefinition("image", PortDirection.INPUT, IMAGE, "Pillow image"),
        PortDefinition("contrast", PortDirection.OUTPUT, FLOAT, "Contrast"),
        PortDefinition("complexity", PortDirection.OUTPUT, FLOAT, "Complexity"),
        PortDefinition("self_similarity", PortDirection.OUTPUT, FLOAT, "Self-similarity"),
        PortDefinition("symmetry_vertical", PortDirection.OUTPUT, FLOAT, "Vertical symmetry"),
        PortDefinition("symmetry_horizontal", PortDirection.OUTPUT, FLOAT, "Horizontal symmetry"),
    ),
    executor=_image_fluency_metrics,
    parameters=(
        ParameterDefinition(
            "complexity_rotate",
            ParameterKind.BOOLEAN,
            "Test rotated image for complexity",
            False,
            port=False,
        ),
        ParameterDefinition(
            "self_similarity_full",
            ParameterKind.BOOLEAN,
            "Use full self-similarity frequency range",
            False,
            port=False,
        ),
        ParameterDefinition(
            "symmetry_shift_range",
            ParameterKind.FLOAT,
            "Symmetry axis shift range",
            0.05,
            "0.0 to 1.0",
            port=False,
        ),
    ),
)


AVAILABLE_NODES = (
    READ_IMAGE,
    PILLOW_TO_IMAGEJ,
    WRITE_IMAGE,
    RESIZE_IMAGE,
    CROP_IMAGE,
    ROTATE_IMAGE,
    CONVERT_IMAGE_MODE,
    IMAGE_TO_MESH,
    IMAGE_FLUENCY_METRICS,
)
