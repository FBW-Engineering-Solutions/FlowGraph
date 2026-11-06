---
id: reference.third-party-notices
title: Third-Party Notices
section: Reference
order: 50
description: License and attribution notices for FlowGraph dependencies.
---

# Third-Party Notices

FlowGraph Core is licensed under **BSD-3-Clause**. The project's
[LICENSE](https://github.com/FBW-Engineering-Solutions/FlowGraph/blob/master/LICENSE)
contains its copyright notice, conditions, and disclaimer. Third-party software
retains its own licenses; FlowGraph's license does not replace those terms.

This page covers the direct dependencies declared by the Core project, not the
separate desktop application or browser editor. The Core wheel and source
distribution contain FlowGraph code, packaged resources, and the project license;
dependency declarations cause other distributions to be installed separately.
Installing a dependency is not the same as bundling its files into the Core wheel.
An application or environment that redistributes those files needs its own review.

## Inventory scope and evidence

**Review date: November 5, 2026.** Versions below are a snapshot of `uv.lock`, not
installation requirements or a promise that every user receives those versions.
The version constraints and extras in
[pyproject.toml](https://github.com/FBW-Engineering-Solutions/FlowGraph/blob/master/pyproject.toml)
determine which direct dependencies are requested; resolution also depends on the
platform and installer inputs. An optional dependency can also arrive transitively.

License descriptions were checked against the installed distributions' metadata
and license files for the listed versions. For scyjava, pyplaid, and PyCGNS, source
archives were also checked against the SHA-256 hashes in `uv.lock`. Linked upstream
projects provide context; the actual files in the selected distribution remain
the evidence to use for redistribution, not a moving upstream branch or a metadata
label alone. The descriptions identify the main project license, not every bundled
component's terms.

## Required runtime dependencies

`required` means a direct dependency of the base Core installation.

| Distribution | Group | Locked version | Main project license | Role and evidence |
| --- | --- | --- | --- | --- |
| `vtk` | `required` | `9.6.2` | BSD-3-Clause | VTK data representations and algorithms. Installed `LICENSE` contains the three-clause BSD terms; see [VTK copyright](https://github.com/Kitware/VTK/blob/master/Copyright.txt). Native and third-party components require separate review. |
| `muscat` | `required` | `2.5.2` | BSD-3-Clause | Mesh data structures and processing. Installed `LICENSE` identifies Muscat Packages and BSD-3-Clause; see [Muscat source](https://gitlab.com/drti/muscat). |

## Optional runtime dependencies

The group column names the extra, for example `flowgraph[io]`. It does not imply
that the integration or its external tools are supported on every platform.

| Distribution | Group | Locked version | Main project license | Role and evidence |
| --- | --- | --- | --- | --- |
| `meshio` | `io` | `5.3.5` | MIT | Mesh format I/O. Installed `LICENSE.txt` credits Nico Schlömer and contributors; see [meshio source](https://github.com/nschloe/meshio). |
| `meshlane` | `io` | `5.5.0` | MIT | Mesh format I/O. Installed `LICENSE.txt` credits Nico Schlömer, Simvia, and Meshlane contributors; see [Meshlane source](https://github.com/simvia-tech/meshlane). |
| `pandas` | `io` | `3.0.5` | BSD-3-Clause | Tabular data operations and I/O. Installed `LICENSE` includes project and additional notices; see [pandas source](https://github.com/pandas-dev/pandas). |
| `h5py` | `io` | `3.16.0` | BSD-3-Clause | HDF5 I/O. Installed metadata and `LICENSE` identify the project license; the distribution also carries HDF5, LZF, and other notices. See [h5py source](https://github.com/h5py/h5py). |
| `pillow` | `io` | `13.0.0` | MIT-CMU (metadata identifier) | Image I/O and processing. Installed `LICENSE` includes PIL/Pillow terms and additional component notices; do not substitute a generic MIT license. See [Pillow source](https://github.com/python-pillow/Pillow). |
| `openpyxl` | `io` | `3.1.5` | MIT | Excel workbook I/O. Installed `LICENCE.rst` identifies the MIT terms; see [openpyxl source](https://foss.heptapod.net/openpyxl/openpyxl). |
| `pyimagej` | `imagej` | `1.8.0` | Apache-2.0 | ImageJ integration. Installed `LICENSE.txt` credits the University of Wisconsin-Madison; see [PyImageJ source](https://github.com/imagej/pyimagej). Java/ImageJ artifacts are not covered by this license label. |
| `scyjava` | `imagej` | `1.12.5` | Unlicense | Python/Java interoperability. Source `UNLICENSE` agrees with the metadata identifier; see [scyjava source](https://github.com/scijava/scyjava). JVM and downloaded Java artifacts have their own terms. |
| `pyplaid` | `ml` | `1.0.0` | BSD-3-Clause | PLAID dataset integration. Source `LICENSE.txt` credits Safran; see [PLAID source](https://github.com/PLAID-lib/plaid). |
| `cosapp` | `cosapp` | `1.6.1` | Apache-2.0 | CoSApp model integration. Installed `LICENSE.rst` credits Safran; see [CoSApp source](https://gitlab.com/cosapp/cosapp). |

## Development and CI dependencies

These extras support development and testing; they are not required by the base
Core installation. Build tooling is declared separately under `build-system` in
`pyproject.toml`. The documentation toolchain also has its own configuration.

| Distribution | Group | Locked version | Role |
| --- | --- | --- | --- |
| `pytest` | `dev` | `9.1.1` | Test runner. |
| `pytest-cov` | `dev` | `7.1.0` | Coverage reporting. |
| `ruff` | `dev` | `0.16.1` | Formatting and linting. |
| `build` | `dev` | `1.6.1` | Distribution build tooling. |
| `cosapp` | `ci` | `1.6.1` | CoSApp integration test dependency; license evidence is listed above. |
| `pycgns` | `ci` | `6.3.5` | CGNS integration test dependency. Metadata says "LGPL 2", but the source `LICENSE` contains LGPL 2.1 text. See [PyCGNS source](https://github.com/pyCGNS/pyCGNS). Exact version/"or later" applicability remains unresolved; do not infer a precise SPDX expression from the metadata. |

## Attribution and redistribution boundaries

When redistributing a component, consult its actual license and accompanying
notices. Preserve applicable copyright, permission, license, disclaimer, and
`NOTICE` material; do not imply upstream endorsement. Additional source,
modification, or library-replacement requirements may apply to particular
components and delivery modes. This overview is not a substitute for those terms
or for legal advice about a specific distribution.

This page is **not an exhaustive SBOM, a complete license bundle, or an
artifact-specific compliance certification**. In particular:

- Transitive packages such as NumPy, SciPy, and matplotlib are not enumerated
  here. Their absence from the direct-dependency tables does not waive their terms.
- VTK, HDF5, image codecs, scientific libraries, and other native components can
  have additional notices that vary by wheel, platform, and build configuration.
- ImageJ/Fiji, Java runtimes, downloaded plugins/JARs, and external executables
  require review independently of the Python adapter's license.
- Separately distributed clients, documentation assets, and any future bundled
  application need a review of the files actually shipped.

The full transitive/native inventory, preserved license texts, and the PyCGNS
license-version discrepancy remain part of the separate artifact-specific review.
No generated SBOM, native audit, or complete preserved-license bundle is claimed
by this page. Recheck the selected artifacts and dependency versions before
redistribution; the remaining review is not closed merely by updating this overview.
