"""Numerical and structural regressions against the original fluency algorithms."""

import warnings

import numpy as np
import pytest
from fluency_reference import _mirror_similarity as reference_mirror
from fluency_reference import _self_similarity_channel as reference_self_similarity
from PIL import Image

from flowgraph.adapters import image_tools
from flowgraph.adapters.image_tools import ImageFluencyError
from flowgraph.application.workflow_core import ExecContext


@pytest.mark.parametrize(
    "shape", [(22, 22), (23, 23), (31, 32), (32, 31), (64, 64), (65, 67), (257, 259)]
)
@pytest.mark.parametrize("full", [False, True])
def test_spectral_score_matches_original(shape: tuple[int, int], full: bool) -> None:
    values = np.random.default_rng(42).integers(0, 256, shape).astype(np.float64)
    assert image_tools._self_similarity_channel(values, full) == pytest.approx(
        reference_self_similarity(values, full), abs=2e-12, rel=2e-12
    )


@pytest.mark.parametrize("axis", ["vertical", "horizontal"])
@pytest.mark.parametrize("shift_range", [0.0, 0.05, 0.5, 0.95, 1.0])
@pytest.mark.parametrize("shape", [(4, 5), (7, 8), (31, 32), (32, 33), (65, 67)])
def test_symmetry_matches_original(shape: tuple[int, int], axis: str, shift_range: float) -> None:
    values = np.random.default_rng(42).integers(0, 256, shape).astype(np.float64)
    # At range=1 the original reaches empty/single-column halves and can warn;
    # its observable maximum and exceptions must remain unchanged.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        try:
            expected = reference_mirror(values, axis, shift_range)
        except (ValueError, ImageFluencyError) as error:
            with pytest.raises(type(error)):
                image_tools._mirror_similarity(values, axis, shift_range)
        else:
            assert image_tools._mirror_similarity(values, axis, shift_range) == pytest.approx(
                expected, abs=2e-12, rel=2e-12
            )


@pytest.mark.parametrize("axis", ["vertical", "horizontal"])
@pytest.mark.parametrize("kind", ["mirror", "negative", "bright", "almost_constant", "strided"])
def test_symmetry_special_images(axis: str, kind: str) -> None:
    rng = np.random.default_rng(43)
    left = rng.integers(0, 256, (37, 19)).astype(np.float64)
    if kind in {"mirror", "negative"}:
        right = left[:, ::-1] if kind == "mirror" else 255 - left[:, ::-1]
        values = np.concatenate((left, right), axis=1)
    elif kind == "bright":
        values = 1e9 + left * 1e-3
    elif kind == "almost_constant":
        values = 255.0 - rng.random((37, 38)) * 1e-9
    else:
        values = left[::-2, ::-1]
    if axis == "horizontal":
        values = values.T
    before = values.copy()
    values.flags.writeable = False
    assert image_tools._mirror_similarity(values, axis, 0.05) == pytest.approx(
        reference_mirror(values, axis, 0.05), abs=2e-10, rel=2e-10
    )
    np.testing.assert_array_equal(values, before)


@pytest.mark.parametrize("axis", ["vertical", "horizontal"])
@pytest.mark.parametrize("partial", [False, True])
def test_symmetry_preserves_constant_half_error(axis: str, partial: bool) -> None:
    values = np.full((32, 32), 17.0)
    if partial:
        values[:, 16:] = np.arange(16)
    if axis == "horizontal":
        values = values.T
    with pytest.raises(ImageFluencyError, match="constant image half"):
        image_tools._mirror_similarity(values, axis, 0.05)


@pytest.mark.parametrize("size", [21, 22, 23, 32])
def test_spectral_errors_unchanged(size: int) -> None:
    values = np.zeros((size, size))
    for kernel in (reference_self_similarity, image_tools._self_similarity_channel):
        with pytest.raises(ImageFluencyError):
            kernel(values, False)


def test_spectral_nonfinite_error() -> None:
    values = np.ones((32, 32))
    values[0, 0] = np.nan
    with pytest.raises(ImageFluencyError, match="non-finite"):
        image_tools._self_similarity_channel(values, False)


def test_rgb_geometry_is_shared_and_not_globally_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import Mock

    geometry = Mock(wraps=image_tools._radial_geometry)
    monkeypatch.setattr(image_tools, "_radial_geometry", geometry)
    image = Image.fromarray(np.random.default_rng(42).integers(0, 256, (33, 35, 3), dtype=np.uint8))
    parameters = image_tools.IMAGE_FLUENCY_METRICS.create_instance("metrics").parameters
    context = ExecContext(connected_output_ports=frozenset({"self_similarity"}))
    first = image_tools.IMAGE_FLUENCY_METRICS.executor({"image": image}, parameters, context)
    assert geometry.call_count == 1
    second = image_tools.IMAGE_FLUENCY_METRICS.executor({"image": image}, parameters, context)
    assert geometry.call_count == 2
    assert first["self_similarity"] == second["self_similarity"]


def test_symmetry_avoids_candidate_corrcoef_copies(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Well-conditioned candidates should use shared sufficient statistics")

    monkeypatch.setattr(np, "corrcoef", forbidden)
    values = np.random.default_rng(42).integers(0, 256, (130, 129)).astype(np.float64)
    assert 0 <= image_tools._mirror_similarity(values, "horizontal", 0.5) <= 1
