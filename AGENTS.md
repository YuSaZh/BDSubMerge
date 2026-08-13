# Repository Instructions

- Use `py -3.12` for every local Python command in this repository.
- Local Python package installation, tests, Ruff, Mypy, builds, and packaging are allowed.
- Validation that requires adding a non-Python environment must run in GitHub Actions after committing and pushing. Audit the final pushed commit by its exact SHA in GitHub Actions.
- Target Python 3.12. Core business logic must not depend on Qt or Windows-only APIs.
- Use integer 90 kHz media ticks for all core timeline calculations. Do not use floating-point seconds.
- Treat BDMV inputs as read-only. Never write into source media structures except through an explicitly resolved subtitle output target.
- Preserve the layered architecture in `docs/architecture.md` and keep CLI and GUI on the same application services.
