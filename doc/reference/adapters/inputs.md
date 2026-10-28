---
id: reference.adapters.inputs
title: Input Nodes
section: Reference
order: 12
description: Nodes that produce configured values and selected file paths.
---

# Input nodes

These nodes produce values without reading mesh data. Parameter ports are
optional; an unconnected port uses the configured default.

| Node (ID) | Output | Parameters and defaults |
| --- | --- | --- |
| **String Input** (`set-string`) | `value: Text` | `value`: `""` |
| **Boolean Input** (`set-boolean`) | `value: Boolean` | `value`: `false` |
| **Integer Input** (`set-int`) | `value: Integer` | `value`: `0` |
| **Float Input** (`set-float`) | `value: Float` | `value`: `0.0` |
| **Float Slider** (`float-slider`) | `value: Float` | `min`: `0.0`, `max`: `1.0`, `value`: `0.5` |
| **Integer Slider** (`int-slider`) | `value: Integer` | `min`: `0`, `max`: `100`, `value`: `50` |
| **2D Vector Input** (`set-vec2d`) | `value: 2D Vector` | `x`, `y`: `0.0` |
| **2D Integer Vector Input** (`set-vec2di`) | `value: 2D Integer Vector` | `x`, `y`: `0` |
| **3D Vector Input** (`set-vec3d`) | `value: 3D Vector` | `x`, `y`, `z`: `0.0` |
| **String List Input** (`set-list[str]`) | `value: List Text` | `value`: `[]` |
| **Integer List Input** (`set-list[int]`) | `value: List Ints` | `value`: `[]` |
| **1D Array Input** (`set-array-1d`) | `value: 1D Array` | `value`: `[]` |

Sliders appear under **Inputs → Scalars**. Their `min`, `max`, and `value`
parameters are optional input ports; connections override local settings.
They require `min < max` and `min <= value <= max`.

Numeric values reject booleans; floats and vector/list components must be finite.
1D Array Input uses a list-based parameter editor and outputs a read-only NumPy
float array. Its optional `value` input is a list parameter; array connections
are converted to Python float lists before updating that parameter.
List values may be entered as Python-literal lists and are type-checked. See the
[File Nodes](file.md) reference for file selection, URL downloads, and directory
listing.