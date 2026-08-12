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

The directory structure and acceptance criteria are defined by the repository development
specification. New third-party behavior must first be captured by a contract test.
