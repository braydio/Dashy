# Repository Guidelines

## Project Structure & Module Organization
- `docker-compose.yml` at the repo root orchestrates the Dashy dashboard container, mounting `config.yml` and `item-icons/`.
- `config.yml` drives widget layout; update icons or logos under `item-icons/`.
- `Weatherboy/` contains the Flask-based weather microservice: `weatherboy.py` (app entry), `templates/` (Jinja2 views embedded in Dashy), `weather_data/` (cached API responses, safe to wipe), and supporting files (`requirements.txt`, `example.env`, service-specific compose file).

## Build, Test, and Development Commands
- Run the main dashboard: `docker compose up -d` (root) serves Dashy on `http://localhost:8085`.
- Rebuild Dashy after config or icon changes: `docker compose up --build`.
- Work on Weatherboy locally: `python -m venv .venv && source .venv/bin/activate`, `pip install -r Weatherboy/requirements.txt`, then `python Weatherboy/weatherboy.py` to serve on `http://localhost:5170`.
- Containerize Weatherboy: `docker compose -f Weatherboy/docker-compose.yml up --build`.

## Coding Style & Naming Conventions
- Target Python 3.12, PEP 8 formatting, and 4-space indents. Group imports stdlib/third-party/local.
- Use `snake_case` for functions and variables, `PascalCase` for classes, and kebab-case for template filenames (`main.html`, `hourly_chart.html`).
- Keep environment-specific settings in `.env`; never hard-code API keys or coordinates.

## Testing Guidelines
- No automated suite yet; smoke-test the Flask app by hitting `/` with different `tmpl` and `day` query strings and verifying `weather_data/` cache refresh.
- When adding Python tests, place them under `Weatherboy/tests/`, name files `test_*.py`, and run with `pytest`. Record manual test steps in PR descriptions until coverage is established.

## Commit & Pull Request Guidelines
- Existing history mixes plain imperative subjects (`update config`) and Conventional Commit scopes (`fix(config): ...`). Prefer the latter for clarity: `<type>(<scope>): short, active voice summary`.
- Reference related issues, note config or secret changes, and attach screenshots for UI or template updates. For Dashy layout tweaks, include before/after or describe affected sections. Clean up generated cache files before committing.

## Security & Configuration Tips
- Copy `Weatherboy/example.env` to `.env` and set `API_KEY` or the app falls back to a placeholder.
- Rotate API keys promptly if exposed, and avoid committing files under `weather_data/`.
