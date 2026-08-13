# Third-party notices

BDSubMerge depends on third-party packages distributed separately by their maintainers.
Release artifacts must include the license text required by every bundled dependency.

| Component | Purpose | License | Source |
| --- | --- | --- | --- |
| Shinya | MPLS parser adapter | MIT | https://github.com/shimamura-hougetsu/shinya |
| pysubs2 | Declared text subtitle dependency | MIT | https://github.com/tkarabela/pysubs2 |
| lxml and its bundled XML libraries | Transitive Shinya dependency included in the Windows package | BSD-3-Clause and component licenses | https://lxml.de/ |
| BluraySubtitle | Functional reference only; no copied code | MIT | https://github.com/Haruite/BluraySubtitle |
| PySide6 / Qt for Python | Desktop UI | LGPLv3/GPLv3/commercial | https://doc.qt.io/qtforpython-6/licenses.html |
| PyInstaller | Windows packaging | GPLv2 with bootloader exception | https://pyinstaller.org/ |

Shinya `0.2a1` is verified against upstream commit
`53998916df0b16a13bd39f79a87198f02fd80e3f`. No source from BluraySubtitle is copied into
this repository. Its MIT notice is retained because it is a requirements-level reference.

The Windows onedir artifact keeps Qt shared libraries separate from the executable. Its
`LICENSES` directory preserves the license-file paths extracted from the exact bundled wheels,
including lxml's notices for bundled XML libraries, plus the Python runtime license and Qt
source acquisition information for the bundled version. It also includes verbatim LGPLv3 and
GPLv3 texts from the matching PySide 6.11.1 source tag because current wheels do not expose the
LGPL text under a stable metadata filename.
