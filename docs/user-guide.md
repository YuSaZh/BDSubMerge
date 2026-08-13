# BDSubMerge User Guide

This guide describes the BDSubMerge 1.0 workflow. The GUI and CLI use the same application
services; CLI examples remain suitable for repeatable and automated checks.

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

An error blocks all output. A warning remains visible in validation and dry-run results, but a
real write requires explicit confirmation in the GUI or `--accept-warnings` in the CLI.
Information does not require confirmation. Multi-target preflight completes before staging any
file. Output then stages all targets, validates them, and commits or rolls back the transaction.

```powershell
bdsubmerge validate "D:\Projects\Title.bdsm.json" --json --verbose
bdsubmerge merge "D:\Projects\Title.bdsm.json" --dry-run --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --accept-warnings --json
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
refresh its fingerprint only after confirming it is the intended file. In the GUI, opening a
project with unresolved inputs shows every source before any BDMV scan or subtitle load. Locate
each BDMV directory or source file; exact fingerprint matches are accepted directly, while a
changed file requires an explicit confirmation whose safe default is No. The project JSON is
updated atomically only after all sources, the saved MPLS timeline, and subtitle loading succeed.
Cancel or any failure leaves the current workspace and the original project file unchanged.

The CLI remains non-interactive: `validate` and `merge` report changed or missing sources and
stop. Complete relocation in the GUI, then rerun the CLI command. The anonymous
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
bdsubmerge merge <project.bdsm.json> [--dry-run] [--accept-warnings]
  [--report <path>] [--report-format json|text]
  [--report-collision abort|overwrite|backup|auto_rename]
```

`plan` displays the stored project without executing it. `validate` reloads all inputs,
reproduces locked mapping, and runs output preflight. `merge` performs transactional output.
When `--report` is supplied, the UTF-8 JSON or text report is preflighted and committed in the
same atomic transaction as the subtitle outputs. A report cannot target the BDMV tree, an input,
an output, or the project file itself.

Runtime logs are bounded JSON Lines files in the platform user-data log directory (for example,
`%LOCALAPPDATA%\BDSubMerge\logs` on Windows). They contain versions, paths, mapping/output
diagnostics, and exception stack frames, but never subtitle body text or exception messages.

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

## 9. Desktop Artifacts

The **Package Desktop** GitHub workflow builds Windows and Linux in parallel. It produces
`BDSubMerge-<version>-windows-x64.zip` and `BDSubMerge-<version>-linux-x86_64.tar.gz`, each with a
matching SHA-256 file. Verify the checksum, extract the complete onedir package, and keep
`_internal` and this project's `LICENSE` beside the executable. Dependency references remain
documented in the repository README and are not duplicated into the release archives.
The workflow smoke-tests both final archives with Python environment variables removed. It also
verifies the embedded version and captures distinct Chinese/light and English/dark screenshots
from each packaged executable. Linux GUI checks run through the native `xcb` plugin under Xvfb.

An Actions artifact is a release candidate until the corresponding GitHub Release is published.
Windows CI creates an isolated temporary SMB share and verifies real UNC scan, preflight, and
atomic output there; commercial-disc fixture breadth and end-user Windows configurations remain
separate validation concerns.

## 10. Safety and Development Policy

- Never modify BDMV source structures.
- Never silently overwrite output; display and preflight the full destination.
- Do not log subtitle body text unless explicit debugging is added by the user.
- No telemetry, network upload, online subtitle download, or automatic update is present.
- Use `py -3.12` for local Python commands. Local Python dependency installation, tests, Ruff,
  Mypy, builds, and packaging are allowed. Run validation that requires adding a non-Python
  environment in GitHub Actions. Audit each pushed candidate by exact commit SHA.

Known validation gaps are real-world MPLS/SUP fixture breadth and a clean Windows 10/11 desktop.
