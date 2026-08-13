# BDSubMerge

[简体中文](README.zh-CN.md)

BDSubMerge is a Windows-first tool for rebuilding ordered episode subtitles on a Blu-ray
MPLS timeline. It reads BDMV metadata without modifying the disc, maps ASS/SSA/SRT or
Blu-ray PGS SUP sources to playlist intervals, and writes external subtitles through
preflighted, transactional output targets.

> Status: `v1.0.2-beta.1` is available for testing; `v1.0.1` remains the stable release. The beta's
> exact commit passes CI, Windows packaging, checksum, no-Python startup, and packaged-UI gates.

## What It Does

- Discovers BDMV layouts from a disc root, `BDMV`, `index.bdmv`, `PLAYLIST`, or MPLS path.
- Parses and ranks every MPLS with an explainable score; it never silently selects one.
- Uses integer 90 kHz ticks for playlist, mapping, text subtitle, and PGS timing.
- Preserves ASS/SSA styles, override style references, comments, extensions, and attachments.
- Maps ordered episode subtitles automatically and accepts locked mappings, manual offsets,
  and user boundaries.
- Preflights every output before writing and commits multi-target output transactionally.
- Saves reproducible, versioned `.bdsm.json` projects with source fingerprints.
- Provides shared application services for the CLI and Qt GUI.

## Quick Start

Download `BDSubMerge-1.0.2-beta.1-windows-x64.zip` and its SHA-256 file from the
[`v1.0.2-beta.1` prerelease](https://github.com/YuSaZh/BDSubMerge/releases/tag/v1.0.2-beta.1)
to test the latest fixes. For the stable build, use the
[`v1.0.1` release](https://github.com/YuSaZh/BDSubMerge/releases/tag/v1.0.1). Verify the checksum,
extract the archive completely, and start `BDSubMerge.exe`. Keep the `_internal` directory beside
the executable.

The CLI is available in an installed environment:

```powershell
bdsubmerge scan "D:\Anime\Title\BDMV" --json
bdsubmerge inspect "D:\Anime\Title\BDMV\PLAYLIST\00001.mpls" --json --verbose
bdsubmerge plan "D:\Projects\Title.bdsm.json" --json
bdsubmerge validate "D:\Projects\Title.bdsm.json" --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --dry-run --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --json
```

See the [user guide](docs/user-guide.md) for input rules, playlist recommendations,
mapping, output modes, project relocation, CLI JSON and exit codes, and safety behavior.
See the [Chinese README](README.zh-CN.md) and
[Chinese user guide](docs/user-guide.zh-CN.md) for Chinese documentation.

## Safety

- BDMV sources are read-only; the application never writes into `PLAYLIST`, `CLIPINF`, or
  `STREAM`.
- Existing output files use `abort` by default. All targets pass preflight before any write.
- Core timeline math does not use floating-point seconds.
- Project and subtitle writes use same-directory temporary files and atomic replacement.
- No telemetry, source upload, online subtitle search, or automatic update is implemented.

## Current Limits

- Real-world MPLS and SUP fixture coverage remains intentionally limited to licensed,
  anonymous, or synthetic data and should continue to expand.
- GitHub Actions validates scanning, preflight, and atomic writes on a temporary real Windows
  SMB/UNC share; behavior still depends on the permissions and availability of each user's
  own share.
- A project whose files moved must be relocated and fingerprinted again before merge.

## Development

The target is Python 3.12. Use `py -3.12` for local Python commands; local Python dependency
installation, tests, Ruff, Mypy, builds, and packaging are supported. Validation that requires a
new non-Python environment runs in GitHub Actions. Every pushed candidate is audited against its
exact commit SHA. See [architecture](docs/architecture.md),
[timebase ADR](docs/adr/0001-media-timebase.md), and [changelog](CHANGELOG.md).

## License

BDSubMerge is licensed under the [MIT License](LICENSE). The release archive includes only
this project's `LICENSE`; the repository retains detailed dependency notices for source audits.

BDSubMerge uses or references these open-source projects:

- [Shinya](https://github.com/shimamura-hougetsu/shinya) for MPLS parsing.
- [pysubs2](https://github.com/tkarabela/pysubs2) as the declared text-subtitle dependency.
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) for the desktop interface.
- [lxml](https://lxml.de/) through Shinya, and
  [PyInstaller](https://pyinstaller.org/) for the Windows build.
- [BluraySubtitle](https://github.com/Haruite/BluraySubtitle) as a functional reference only;
  no source code was copied.

Exact versions and extended notices are recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
