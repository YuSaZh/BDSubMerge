# Repository Instructions

- Never run builds, tests, linters, type checks, dependency installation, or packaging locally.
- Validate code exclusively with GitHub Actions by committing and pushing to the remote repository.
- Local commands are limited to source inspection, static text searches, Git operations, and non-executing file checks such as `git diff --check`.
- Target Python 3.12. Core business logic must not depend on Qt or Windows-only APIs.
- Use integer 90 kHz media ticks for all core timeline calculations. Do not use floating-point seconds.
- Treat BDMV inputs as read-only. Never write into source media structures except through an explicitly resolved subtitle output target.
- Preserve the layered architecture in `docs/architecture.md` and keep CLI and GUI on the same application services.
