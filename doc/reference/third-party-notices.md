---
id: reference.third-party-notices
title: Third-Party Notices
section: Reference
order: 50
description: License and attribution notices for FlowGraph dependencies.
---

# Third-Party Notices

FlowGraph is proprietary software. This page records the third-party software
included with or used by the FlowGraph application and explains the notices and
license conditions that apply when the application is redistributed.

The third-party components remain governed by their own licenses. Their
licenses do not change the proprietary status of FlowGraph itself.

## Runtime dependencies

| Component | Locked version | License / status | Attribution and redistribution note |
| --- | ---: | --- | --- |
| trame | 3.13.2 | Apache-2.0 | Preserve copyright, license, and applicable `NOTICE` information. |
| trame-vtk | 2.11.15 | BSD | Preserve copyright, license, and disclaimer; do not imply endorsement. |
| trame-vuetify | 3.2.5 | MIT | Preserve the copyright and license notice. |
| trame-flow | 2.2.2 | MIT | Preserve the copyright and license notice. |
| trame-dockview | 1.4.0 | MIT | Preserve the copyright and license notice. |
| markdown-it-py | 4.2.0 | MIT | Preserve the copyright and license notice. |
| VTK | 9.6.2 | BSD | Preserve the BSD notice and disclaimer; do not use contributor names for endorsement. |
| Muscat | 2.5.2 | BSD-3-Clause | Upstream repository identifies BSD-3-Clause; verify the exact distributed files. |
| meshio | 5.3.5 | MIT | Preserve the copyright and license notice. |
| Meshlane | 5.5.0 | MIT | Preserve the copyright and license notice. |
| pyplaid | 1.0.0 | BSD-3-Clause | Preserve the BSD notice and disclaimer; verify the exact package artifact. |
| SciPy | 1.17.1 | BSD-3-Clause plus bundled components | Preserve SciPy notices and review bundled native-library licenses. |
| pandas | 3.0.5 | BSD-3-Clause | Preserve the copyright, license, and disclaimer. |
| h5py | 3.16.0 | BSD-3-Clause plus HDF5 | Preserve h5py/HDF5 notices and review the bundled HDF5 library. |

## Optional desktop dependencies

| Component | Locked version | License / status | Redistribution note |
| --- | ---: | --- | --- |
| PyWebView | 6.2.1 | BSD | Preserve the BSD notice and disclaimer. Platform WebView runtimes may have separate terms. |
| PyGObject | 3.50.2 | LGPL-2.1-or-later | Include the LGPL notice and preserve the applicable user-replacement/source obligations. GTK, Cairo, and GObject-Introspection libraries must be reviewed separately. |

PyGObject is selected only on Linux by the project dependency declaration.
The operating system's GTK and related libraries may be supplied by the
platform rather than by FlowGraph, but their licenses still apply to any
libraries included in a FlowGraph release.

## License conditions

The licenses above generally permit use of these components in a proprietary
application. When receiving or redistributing FlowGraph, the following
conditions remain applicable:

- Preserve the relevant copyright, attribution, license, warranty disclaimer,
  and Apache `NOTICE` text.
- Do not use contributor or project names to imply endorsement.
- For LGPL components such as PyGObject, do not prevent replacement of the
  LGPL library and satisfy the applicable source and modification requirements.
- Platform components such as GTK, Cairo, WebView runtimes, and native libraries
  may have additional notices and conditions.

The complete license texts and notices for the components included in a
particular FlowGraph release should be supplied with that release.

## Project links

- [FlowGraph project metadata](https://github.com/FBW-Engineering-Solutions/FlowGraph)
- [Trame](https://kitware.github.io/trame/)
- [VTK licensing](https://vtk.org/licensing/)
- [Muscat source and license](https://gitlab.com/drti/muscat)
- [PyInstaller license](https://pyinstaller.org/en/stable/license.html)
- [SciPy license](https://github.com/scipy/scipy/blob/main/LICENSE.txt)
- [PyGObject project](https://pygobject.gnome.org/)
- [meshio](https://github.com/nschloe/meshio)
- [Meshlane](https://github.com/simvia-tech/meshlane)
- [pyplaid](https://plaid-lib.github.io/)
