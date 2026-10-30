"""Frozen pre-optimization fluency kernels for numerical regression tests."""

import numpy as np
from PIL import Image as PillowImage

from flowgraph.adapters.image_tools import ImageFluencyError, _normalise_for_fft


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
