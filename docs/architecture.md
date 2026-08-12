# Architecture

BDSubMerge uses a layered package with immutable or controlled domain models at its center.

```text
UI / CLI
   |
application services
   |
domain, mapping, merge, output, project
   |
Shinya / pysubs2 / filesystem adapters
```

## Dependency rules

1. `domain` imports only the Python standard library.
2. `bdmv` converts third-party parser objects into project-owned domain models.
3. `subtitles` converts text and PGS files into project-owned representations.
4. `mapping` is deterministic and has no filesystem or UI dependency.
5. `merge` computes output data but never chooses a destination path.
6. `output` resolves and validates destinations, then performs atomic writes.
7. `project` persists versioned plans and migrates older schemas.
8. `ui` and `cli` call the same application services and never consume raw adapter objects.

## Application and persistence boundaries

CLI and GUI construct the same typed application requests. Application services coordinate
BDMV adapters, subtitle loading, mapping, merge computation, output preflight, and transactional
writing; surfaces must not duplicate those rules.

The `project` layer owns a versioned immutable snapshot and neutral state DTOs. It does not
import UI or concrete output targets. A snapshot stores cheap source metadata fingerprints,
integer mapping times, output/conflict policies, and relative paths with absolute recovery hints.
Loading reports changed or missing sources before an application request can execute. Project
JSON is committed by a same-directory atomic writer.

The `output` layer resolves all targets before writing. Multi-target writes stage and validate
every payload before commit, and roll back the set on failure. Merge engines return data only;
they never choose a destination or write a file.

The directory structure and acceptance criteria are defined by the repository development
specification. New third-party behavior must first be captured by a contract test.
