# Third-party notices

BDSubMerge depends on third-party packages distributed separately by their maintainers.
This repository keeps the detailed notices below for source audits; release archives include
only BDSubMerge's project `LICENSE` and do not copy the repository `licenses/` directory.

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

The tracked `licenses/` directory retains upstream texts and a Qt source-offer note for repository
audits. It is intentionally excluded from release archives.
