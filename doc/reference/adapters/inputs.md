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
| **Integer Input** (`set-int`) | `value: Integer` | `value`: `0` |
| **Float Input** (`set-float`) | `value: Float` | `value`: `0.0` |
| **3D Vector Input** (`set-vec3d`) | `value: 3D Vector` | `x`, `y`, `z`: `0.0` |
| **String List Input** (`set-list[str]`) | `value: List Text` | `value`: `[]` |
| **Integer List Input** (`set-list[int]`) | `value: List Ints` | `value`: `[]` |
| **Float List Input** (`set-list[float]`) | `value: List Floats` | `value`: `[]` |

Numeric values reject booleans; floats and vector/list components must be finite.
List values may be entered as Python-literal lists and are type-checked. See the
[File Nodes](file.md) reference for file selection, URL downloads, and directory
listing.