# Changelog

All notable development changes are recorded here. BDSubMerge has not reached a stable 1.0
release; entries under **Unreleased** describe the current pre-alpha source tree.

## Unreleased

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

### Changed

- README status now reflects M5 feature completion in source while CI integration remains in
  progress. No stable release claim is made.

### Known Limitations

- Real-world MPLS and SUP fixture breadth still requires expansion and verification.
- Writing to a live UNC/SMB share still requires environment-level verification.
- The Qt GUI and Windows artifact remain development builds until explicitly released.
