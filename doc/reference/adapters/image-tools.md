---
id: reference.adapters.image-tools
title: Image Tool Nodes
section: Reference
order: 22
description: Nodes that load, transform, save, and convert Pillow images.
---

# Image tool nodes

The **Image Tools** top-level group uses Pillow `Image` values. The reader returns
a detached image copy, so downstream nodes can use it after the input file closes.

| Node (ID) | Inputs and outputs | Behavior |
| --- | --- | --- |
| **Read Image (Pillow)** (`read-image`) | Parameter/input `path: Path`; output `image: Image` | Loads a Pillow image from an existing file. |
| **Pillow To ImageJ** (`pillow-to-imagej`) | Input `image: Image`; output `image: ImageJ` | Copies the Pillow image into a detached NumPy array for ImageJ-compatible processing. |
| **Write Image (Pillow)** (`write-image`) | Parameter/input `filename: Path`, input `image: Image`; no outputs | Saves the image using the output filename extension to select the format. |
| **Resize Image** (`resize-image`) | Input `image: Image`; parameter/input `width: Integer`, `height: Integer`; output `image: Image` | Resizes to a positive target size with Pillow's Lanczos resampling. |
| **Crop Image** (`crop-image`) | Input `image: Image`; parameter/input `left: Integer`, `top: Integer`, `right: Integer`, `bottom: Integer`; output `image: Image` | Crops to an in-bounds rectangle. Coordinates use Pillow's exclusive right and bottom edges. |
| **Rotate Image** (`rotate-image`) | Input `image: Image`; parameter/input `angle: Float`, `expand: Boolean`; output `image: Image` | Rotates counter-clockwise in degrees with bicubic resampling. `expand` defaults to enabled so the complete rotated image fits. |
| **Convert Image Mode** (`convert-image-mode`) | Input `image: Image`; output `image: Image`; local `mode` | Converts to `1`, `L`, `LA`, `RGB`, `RGBA`, `CMYK`, or `HSV`. |
| **Image To Mesh** (`image-to-mesh`) | Input `image: Image`; output `mesh: Mesh document` | Creates a Muscat constant rectilinear mesh with a `Colors` field. |
| **Image Fluency Metrics** (`image-fluency-metrics`) | Input `image: Image`; outputs `contrast`, `complexity`, `self_similarity`, `symmetry_vertical`, `symmetry_horizontal: Float` | Calculates contrast, compression complexity, self-similarity, and vertical/horizontal symmetry. |

The reader rejects missing or non-file paths. The writer requires a filename
extension and an existing output directory. Pillow load and write failures are
reported as actionable `ImageLoadError` and `ImageWriteError` messages.

File parameters and the Resize, Crop, and Rotate operation parameters are
exported as optional workflow input ports. A connection overrides the configured
parameter value for that execution.

Image transformation nodes always return a new Pillow image and do not mutate the
input value. Color-mode settings remain local node configuration. Invalid
dimensions, crop regions, color modes, and image inputs are reported as actionable
`ImageOperationError` messages.

**Image Fluency Metrics** has local (non-port) parameters
`complexity_rotate=False`, `self_similarity_full=False`, and
`symmetry_shift_range=0.05` (from 0 to 1). The metrics are separate float
outputs; only connected outputs (including exported workflow outputs) are computed
during workflow execution. For example, connecting only `contrast` skips FFT-based
self-similarity, symmetry searches, and gzip compression. Unconsumed outputs retain
their declared keys with `NaN` placeholders (`null` in JSON responses). Direct
executor calls without an execution context compute all metrics. Channels are
converted once and shared by the requested channel-based metrics.

The metrics retain the original full-resolution definitions: self-similarity
keeps its historical square/BOX preprocessing and radial log-log regression;
symmetry searches every configured shifted axis using absolute Pearson
correlation. Radial powers are accumulated by ring in one pass, with geometry
shared across RGB channels. Symmetry uses prefix statistics and chunked,
zero-padded FFT self-convolution to evaluate the same pixel pairings without
repeatedly copying image halves. Ill-conditioned candidates use the original
direct correlation calculation. Inputs are not modified or downsampled for
speed. Floating-point reduction order can change the last few decimal places.
Geometry is execution-local; FFT scratch uses at most 32 image rows per chunk.

The reproducible full-resolution browser benchmark is
`tests/benchmark_fluency_wasm.cjs`. With the production editor served on port
8082, run it using Node and an existing Playwright installation (set
`PLAYWRIGHT_MODULE` to its module path if it is not locally resolvable).
`FLOWGRAPH_URL` selects another editor URL and `FLUENCY_REPORT` sets the report
filename. It measures three runs per metric group in the actual WASM worker,
excludes warmup, checks 2850 × 2484 dimensions, and asserts reference outputs
within `5e-12`. Browser benchmark tooling is not a runtime dependency.

On October 30, 2026, the rebuilt production serial runtime measured the following
three-run averages on the original 2850 × 2484 RGB `ColorCardboard.jpg`, in
Chromium 156.0.8078.4. Runtime warmup is excluded. Metric times include all RGB
channels; shared conversion/geometry and workflow overhead are included only in
the complete workflow time.

| Calculation | Original | Optimized | Speedup |
| --- | ---: | ---: | ---: |
| Self-similarity | 25.55 s | 0.979 s | 26.1× |
| Horizontal symmetry | 61.68 s | 0.546 s | 112.9× |
| Vertical symmetry (separate workflow) | 59.28 s | 0.362 s | 163.7× |
| Contrast + complexity + self-similarity + horizontal symmetry workflow | 88.09 s | 2.433 s | 36.2× |

The optimized four-metric workflow ranged from 2.233–2.778 s. Contrast,
complexity, and self-similarity matched the browser reference exactly; maximum
absolute symmetry differences were `1.25e-13` horizontally and `1.08e-12`
vertically. These timings are environment-specific, not performance guarantees.
Memory use was not measured; only temporary array sizes are bounded by design.

**Pillow To ImageJ** has no
parameters and produces an independent NumPy array rather than modifying the
source Pillow image.

## Image to mesh colors

**Image To Mesh** uses Muscat's `CreateConstantRectilinearMesh` with unit spacing
and a zero origin. The resulting mesh uses structured quadrangle elements. In
node-field mode it has dimensions `[image.width, image.height]` and one node per
input pixel.

The local **Store colors on node fields** checkbox defaults to enabled. When
enabled, `Colors` is stored in `mesh.nodeFields` with one row per image pixel. When
disabled, the mesh has one additional node in each direction so it has one
quadrangle per image pixel, and `Colors` is stored directly in `mesh.elemFields`.

`Colors` always has one row per selected mesh entity and uses these component
conventions:

| Image mode | Components per `Colors` row | Channels |
| --- | --- | --- |
| `L` | 1 | Grayscale / luminance |
| `LA` | 2 | Grayscale / luminance, alpha |
| `RGB` | 3 | Red, green, blue |
| `RGBA` | 4 | Red, green, blue, alpha |

Other Pillow modes are converted to `RGBA` before creating `Colors`.