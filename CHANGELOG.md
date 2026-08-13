# Changelog

All notable changes to BDSubMerge are recorded here.

## Unreleased

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
