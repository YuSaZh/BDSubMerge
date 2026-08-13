# Repository Instructions

- Use `py -3.12` for every local Python command. Never use the default Python 3.14 runtime.
- Local Python dependency installation, tests, linters, type checks, builds, and packaging are allowed with Python 3.12.
- Missing Python packages may be installed locally. When validation requires a new non-Python environment or dependency, perform that validation with GitHub Actions instead of provisioning it locally.
- Commit and push final changes with the machine's existing SSH or `gh` credentials. Never use browser-based GitHub login.
- After every push, audit GitHub Actions for the exact pushed commit SHA and resolve any failures before considering the work complete.
- Target Python 3.12. Core business logic must not depend on Qt or Windows-only APIs.
- Use integer 90 kHz media ticks for all core timeline calculations. Do not use floating-point seconds.
- Treat BDMV inputs as read-only. Never write into source media structures except through an explicitly resolved subtitle output target.
- Preserve the layered architecture in `docs/architecture.md` and keep CLI and GUI on the same application services.
