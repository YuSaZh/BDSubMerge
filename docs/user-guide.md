# BDSubMerge User Guide

This guide describes the implemented pre-alpha workflow. The GUI is still under integration;
the CLI examples expose the same application services and are suitable for repeatable checks.

## 1. Inputs and Scanning

BDSubMerge accepts a disc container, `BDMV` directory, `index.bdmv`, `PLAYLIST` directory,
or an individual `.mpls` file. A scan locates the actual `index.bdmv`, `PLAYLIST`, `CLIPINF`,
and `STREAM` directories. BDMV data is always treated as read-only.

```powershell
bdsubmerge scan "D:\Anime\Title\BDMV" --json
```

Use `--max-depth N` when scanning above the disc directory. Optional
`--subtitle-duration-90k` and `--subtitle-count` values improve recommendations. Durations are
integer 90 kHz ticks; one second is 90,000 ticks.

The scanner continues when one MPLS fails. That playlist is reported unavailable with an
issue instead of aborting the whole disc scan.

## 2. Playlist Recommendations

Every available MPLS receives a deterministic score, confidence, and reasons. Factors include
duration, PlayItem and chapter counts, unique versus repeated clips, very short segments,
missing M2TS/CLPI references, multi-angle content, cumulative subtitle duration, and expected
episode count. The longest MPLS is not automatically assumed to be correct.

```powershell
bdsubmerge inspect "D:\Anime\Title\BDMV\PLAYLIST\00001.mpls" --json --verbose
```

`--verbose` includes PlayItems, marks, warnings, errors, and the timeline fingerprint. Two MPLS
files are timeline-equivalent only when their complete sequence of clip ID, IN/OUT times, and
selected angle matches.

For AC-10, multiple non-equivalent playlists cannot share one JRiver `index.ass` timeline.
Choose exactly one main JRiver timeline and use playlist-named or custom outputs for others.

## 3. Subtitle Sources

One merge task accepts one subtitle family:

- ASS or SSA text subtitles;
- SRT text subtitles;
- Blu-ray PGS SUP subtitles.

Do not mix ASS with SRT or text with SUP in one merge. Text decoding supports UTF-8, UTF-8
BOM, UTF-16 LE/BE, GB18030, and Shift-JIS. Ambiguous legacy encoding requires an explicit
choice. Default SRT output uses UTF-8 BOM.

ASS/SSA processing keeps Dialogue and Comment events, declared `Format` field order, styles,
parsed `\rStyle` references, Script Info diagnostics, Aegisub Extradata, fonts, graphics, and
unknown sections. Unknown or conflicting data is reported rather than silently discarded.

## 4. Mapping and Boundaries

Candidate boundaries come from playlist start/end, PlayItem edges, and chapter marks. The
integer optimizer maps ordered subtitles to monotonically increasing intervals and reports a
confidence with reasons. A subtitle ending before the interval is normal; substantial overrun
costs more than an early final line.

Review low-confidence results. A saved mapping contains:

- subtitle ID and order;
- start and end boundary IDs and exact 90 kHz times;
- manual offset in 90 kHz ticks;
- lock state, confidence, and warnings.

User-created boundaries and exact saved mapping times are restored on project load. Locked
mappings reproduce the saved interval and manual offset rather than allowing a silent remap.

## 5. Preflight

Before writing, BDSubMerge verifies source fingerprints, playlist timeline identity, mapping
completeness/order, output extensions, directories, collisions, duplicate targets, source/output
overlap, and JRiver naming. Results are errors, warnings, or information.

An error blocks all output. Multi-target preflight completes before staging any file. Output
then stages all targets, validates them, and commits or rolls back the transaction.

```powershell
bdsubmerge validate "D:\Projects\Title.bdsm.json" --json --verbose
bdsubmerge merge "D:\Projects\Title.bdsm.json" --dry-run --json
```

`validate` rebuilds the planned merge and output preflight. `merge --dry-run` performs the same
prepare/execute checks and reports what would be written, but writes nothing.

## 6. Output Modes

- **JRiver:** exactly `<actual BDMV>/index.ass` (or matching format extension), derived from
  the discovered `index.bdmv`. Auto-rename is forbidden and only one JRiver target is allowed.
- **Playlist:** `<BDMV>/PLAYLIST/<playlist_stem>.<ext>`, optionally with a language suffix.
- **Disc name:** `<disc-container-name>.<ext>` in its parent or a chosen directory.
- **Template:** a chosen directory with `{disc_name}`, `{playlist}`, `{playlist_stem}`,
  `{index_stem}`, `{language}`, `{format}`, and `{volume}`.
- **Full path:** an explicitly selected final path.

Collision policies are `abort`, `overwrite`, `backup`, and `auto_rename`, subject to target
restrictions. `abort` is the safe default. No source subtitle or BDMV media file may be an
output target.

## 7. Project Save, Restore, and Relocation

`.bdsm.json` schema v1 stores the BDMV/index/MPLS locators and metadata fingerprints, playlist
timeline fingerprint, ordered subtitles and encoding, boundaries, locked mappings and offsets,
output/conflict policies, and UI notes. Paths within a shared non-root tree prefer relative
form and retain an absolute recovery hint.

Project saves use a same-directory temporary file, flush and `fsync`, then atomic replacement.
On load, index/MPLS/subtitle sources are classified `unchanged`, `changed`, or `missing`; the
BDMV locator directory is checked for existence without treating a newly written `index.ass`
as source mutation.

Changed or missing input blocks CLI validation and merge. Relocate the source explicitly and
refresh its fingerprint only after confirming it is the intended file. The anonymous
[`examples/minimal.bdsm.json`](../examples/minimal.bdsm.json) demonstrates structure only; its
placeholder files must be relocated before use.

## 8. CLI Reference

Common options may be placed before or after the subcommand:

- `--json`: emit one JSON envelope;
- `--dry-run`: do not write merge output;
- `--verbose`: include detailed structures and diagnostics;
- `--version`: print the package version.

Commands:

```text
bdsubmerge scan <path> [--max-depth N] [--subtitle-duration-90k TICKS] [--subtitle-count N]
bdsubmerge inspect <mpls> [--max-depth N]
bdsubmerge plan <project.bdsm.json>
bdsubmerge validate <project.bdsm.json>
bdsubmerge merge <project.bdsm.json> [--dry-run]
```

`plan` displays the stored project without executing it. `validate` reloads all inputs,
reproduces locked mapping, and runs output preflight. `merge` performs transactional output.

JSON output has this stable top-level envelope:

```json
{
  "command": "validate",
  "data": {},
  "exit_code": 0,
  "issues": [],
  "ok": true
}
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 2 | CLI usage error |
| 3 | Invalid input or project JSON |
| 4 | Validation or preflight failed |
| 5 | Operation failed |

## 9. Windows Artifact

The **Package Windows** GitHub workflow produces the `BDSubMerge-windows-x64` artifact as a
PyInstaller onedir package. Download it from a successful Actions run, extract the entire
folder, and keep `_internal`, `LICENSE`, and `THIRD_PARTY_NOTICES.md` beside the executable.
The workflow smoke-tests the packaged GUI and verifies translation resources before upload.

The artifact is a development build until a release is explicitly published. Actual UNC/SMB
writes still need verification against a live share; current automated coverage validates
Windows UNC path resolution and preflight without contacting a server.

## 10. Safety and Development Policy

- Never modify BDMV source structures.
- Never silently overwrite output; display and preflight the full destination.
- Do not log subtitle body text unless explicit debugging is added by the user.
- No telemetry, network upload, online subtitle download, or automatic update is present.
- Repository contributors must not build, test, lint, type-check, install dependencies, or
  package locally. Push changes and use GitHub Actions for validation.

Known validation gaps are real-world MPLS/SUP fixture breadth and live UNC write behavior.
