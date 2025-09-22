# Repository Guidelines

## Project Structure & Module Organization
- Core daemon logic lives in `rofication-daemon.py`; supporting clients (GUI, Waybar, i3blocks) are neighbouring scripts.
- Shared message types are in `msg.py`; cached notification data persists under `~/.cache/rofication/not.json`.
- User configuration is read from `~/.config/rofication/config.json`; keep examples or templates alongside documentation.
- Static assets (e.g., screenshots) reside in `Picture/`; CLI utilities occupy the project root.

## Build, Test, and Development Commands
- `python -m compileall rofication-daemon.py` — quick syntax validation for the daemon without running it.
- `./rofication-daemon.py` — launch the DBus notification daemon (ensure executable bit and DBus session).
- `./rofication-gui.py` — open the Rofi-based client against the running daemon.
- `PYTHONPATH=. python -m pdb rofication-daemon.py` — optional interactive debugging entry point.

## Coding Style & Naming Conventions
- Follow PEP 8: 4-space indentation, snake_case for variables/functions, CapWords for classes.
- Prefer descriptive logging over verbose inline comments; add comments only for non-obvious logic.
- Keep configuration keys lowercase with underscores (`ntfy_mirror`, `single_notification_app`).
- Use f-strings for formatting and guard optional imports (e.g., `requests`) with fallbacks.

## Testing Guidelines
- No automated test suite ships today; run `python -m compileall` on edited modules and exercise key flows manually.
- When adding tests, place them in a top-level `tests/` package and name files `test_<feature>.py` using `pytest` conventions.
- Capture edge cases (e.g., invalid regexes, missing config) with targeted unit tests when feasible.

## Commit & Pull Request Guidelines
- Write commit subjects in the imperative mood (“Add ntfy mirroring”) with <= 50 characters when possible.
- Include concise bodies explaining the rationale, configuration changes, and testing performed.
- PRs should describe user-visible effects, reference related issues, and include screenshots or logs for UI or daemon output changes.
- Highlight any new configuration keys or migration steps so downstream users can update their setups safely.

## Security & Configuration Tips
- Never commit personal ntfy tokens; load secrets via `config.json` and document required fields.
- Validate and log regex compilation failures to prevent silent misconfiguration.
- Ensure the daemon runs with standard user permissions; avoid storing sensitive data outside `$HOME`.
