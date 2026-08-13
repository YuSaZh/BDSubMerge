# Changelog

All notable changes to BDSubMerge are recorded here.

## Unreleased

## 1.0.2-beta.2 - 2026-08-14

### Added

- Added a parallel Linux x86_64 onedir package with native X11 GUI smoke tests, packaged screenshots,
  SHA-256 verification, and publication beside the Windows archive.

### Fixed

- Sized compact mapping columns only wide enough for their complete headings and values, including
  the new `No.` heading, chapter IDs, target interval, offset, confidence, and status.
- Kept complete subtitle filenames and output target paths visible through full-width columns and
  horizontal scrolling instead of ellipsis.
- Reworded zero-time event diagnostics in Simplified Chinese to explain that a source event shifted
  entirely before the final timeline is omitted from the generated subtitle.

## 1.0.2-beta.1 - 2026-08-14

### Fixed

- Kept the subtitle filename column expanded when sufficient width is available while preserving
  manual resizing and full-path tooltips.
- Widened the chapter boundary option list independently from its compact chapter-only cell value.
- Prevented timeline labels from stretching horizontally during mouse-wheel zoom.
- Added Simplified Chinese fallback for merge, output, and report diagnostics, including a clearer
  explanation when an event is dropped after its time offset places it at or before zero.
- Grouped repeated diagnostics in the GUI without changing the underlying warning and report counts.
- Prevented near-exact duration matches from being downgraded solely because another local candidate
  is close; materially inaccurate ambiguous matches remain low confidence.

## 1.0.1 - 2026-08-13

### Added

- Mouse-wheel timeline zoom from 100% to approximately 890%, anchored at the pointer and shown
  beside the time display selector.
- Simplified Chinese descriptions for GUI errors and warnings while retaining stable codes and
  original technical details.

### Changed

- Replaced the fixed workspace stack with a persistent vertical splitter. The episode subtitle
  table now starts about twice as tall, supports manually resized columns, and exposes full source
  paths in tooltips.
- Hid the duplicate Qt row-number header while retaining the explicit sequence column.
- Collapsed merge-report settings when report output is disabled.
- Boundary cells now show chapter IDs only; opening a boundary list still shows chapter IDs with
  formatted times.
- Windows release archives now include only BDSubMerge's `LICENSE`; dependency and reference
  attribution is listed in both READMEs and retained in the source repository.
- GitHub Release creation now uses versioned, content-rich release notes instead of relying on an
  automatically generated changelog link.

## 1.0.0 - 2026-08-13

### Added

- BDMV layout discovery, MPLS parsing adapters, integer 90 kHz timeline models, playlist
  equivalence, and explainable playlist ranking.
- ASS/SSA/SRT and Blu-ray PGS SUP loading and merge cores, including deterministic ASS style
  conflict handling, extension preservation, text precision rules, and PGS timestamp shifting.
- Deterministic episode boundary generation and mapping with confidence, locked mappings,
  user boundaries, and manual offsets.
- JRiver, playlist, disc-name, template, and full-path output strategies with transactional
  preflight, rollback, backup, and collision policies.
- Versioned `.bdsm.json` project persistence, source fingerprints, path relocation, migration,
  application-state conversion, and atomic project saves.
- Shared application services, CLI commands, Qt GUI shell, translations, GitHub CI, Windows
  onedir packaging, and automated acceptance coverage.
- Atomic project restore with per-source relocation, changed-input confirmation, complete
  playlist identity checks, and deterministic mapping/output policy replay.
- Runtime logs, optional text/JSON merge reports, cooperative cancellation, and bilingual
  packaged-UI evidence.

### Changed

- Windows release archives include the version in the filename and must pass exact version,
  SHA-256, license, no-Python startup, and packaged-UI screenshot gates.
- CLI and GUI warning confirmation now share the same application-service severity gate.

### Known Limitations

- Real-world MPLS and SUP fixture breadth is limited to licensed, anonymous, or synthetic data
  and should continue to expand.
- User-provided UNC/SMB shares remain subject to their own permissions and availability even
  though CI verifies scanning, preflight, and atomic writes on a real temporary Windows share.
