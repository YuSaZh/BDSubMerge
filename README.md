# BDSubMerge

BDSubMerge is a Windows-first tool for rebuilding ordered episode subtitles on a Blu-ray
MPLS timeline. It reads BDMV metadata without modifying the disc, maps ASS/SSA/SRT or
Blu-ray PGS SUP sources to playlist intervals, and writes external subtitles through
preflighted, transactional output targets.

> Status: pre-alpha. Milestones M0-M5 are feature-complete in source, and the current
> integration is being verified by GitHub Actions. This is not a 1.0 release.

## What It Does

- Discovers BDMV layouts from a disc root, `BDMV`, `index.bdmv`, `PLAYLIST`, or MPLS path.
- Parses and ranks every MPLS with an explainable score; it never silently selects one.
- Uses integer 90 kHz ticks for playlist, mapping, text subtitle, and PGS timing.
- Preserves ASS/SSA styles, override style references, comments, extensions, and attachments.
- Maps ordered episode subtitles automatically and accepts locked mappings, manual offsets,
  and user boundaries.
- Preflights every output before writing and commits multi-target output transactionally.
- Saves reproducible, versioned `.bdsm.json` projects with source fingerprints.
- Provides shared application services for the CLI and developing Qt GUI.

## Quick Start

Use the downloadable Windows artifact for normal evaluation. From the repository's
**Actions** page, open a successful **Package Windows** run, download
`BDSubMerge-windows-x64`, extract the complete directory, and start `BDSubMerge.exe`.
Keep the `_internal` directory beside the executable.

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

- Real-world MPLS and SUP fixture coverage still needs expansion and validation.
- Actual writes to a live UNC/SMB share still require environment-level verification;
  Windows path resolution and preflight are covered without contacting a share.
- The Qt GUI is under integration and does not yet represent a declared stable 1.0 workflow.
- A project whose files moved must be relocated and fingerprinted again before merge.

## Development

The target is Python 3.12. Repository policy forbids local builds, tests, linters, type
checks, dependency installation, and packaging. CI, tests, and Windows packaging run only in
GitHub Actions. See [architecture](docs/architecture.md),
[timebase ADR](docs/adr/0001-media-timebase.md), and [changelog](CHANGELOG.md).

## License

BDSubMerge is licensed under the MIT License. Third-party attribution is in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
