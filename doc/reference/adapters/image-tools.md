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
outputs; connect only the values needed downstream. **Pillow To ImageJ** has no
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