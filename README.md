# BDSubMerge

BDSubMerge is a Windows-first desktop tool for rebuilding episode subtitles on a Blu-ray
MPLS playback timeline. It reads BDMV metadata without modifying the disc, maps ordered
ASS/SSA/SRT/PGS subtitles to playlist intervals, and writes external subtitles through
explicit, preflighted output targets such as JRiver's `BDMV/index.ass` convention.

> Status: pre-alpha. The repository is being implemented milestone by milestone from the
> [development specification](./BDSubMerge%EF%BC%9ABDMV%20%E5%8E%9F%E7%9B%98%E5%AD%97%E5%B9%95%E5%90%88%E5%B9%B6%E5%B7%A5%E5%85%B7%E5%AE%9E%E7%8E%B0%E4%BB%BB%E5%8A%A1%E4%B9%A6%EF%BC%88Codex%20%E5%BC%80%E5%8F%91%E7%89%88%EF%BC%89.md).

## Design constraints

- The BDMV source is always read-only.
- Core time is represented by integer 90 kHz ticks.
- Qt, Shinya, and pysubs2 are isolated behind adapters.
- CLI and GUI use the same application services.
- Output paths are resolved separately from merge computation.
- Existing files are never overwritten by default.

## Development

This project targets Python 3.12. Validation and packaging run only in GitHub Actions;
the repository intentionally does not require or permit local builds in its current
development workflow. See [architecture](docs/architecture.md), [timebase ADR](docs/adr/0001-media-timebase.md),
and the [Chinese README](README.zh-CN.md).

## License

BDSubMerge is licensed under the MIT License. Third-party attribution is documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
