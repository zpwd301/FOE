# Repository Guidelines

## Project Structure & Module Organization
City-facing utilities live in `script/`. `script/city_analysis.py` loads the newest `city_*.json` from `~/Documents/FOE/CityAnalysis/input`, classifies every entity, and prints troop summaries. `script/save_city_json.sh` captures clipboard dumps, while `script/display_top_attribute.sh` scans the JSON surface area. Checkpoint source inputs under `input/` and commit analyzer output in `output/` using `city_summary_YYYY-MM-DD_HH-MM-SS.txt`. The era lookup table in `script/script_config` is the single place to extend age metadata.

## Build, Test, and Development Commands
- `bash script/save_city_json.sh` — snapshot the FOE clipboard export into `~/Documents/FOE/CityAnalysis/input/city_<date>.json`, validating the JSON with `jq`.
- `python3 script/city_analysis.py` — run the analyzer; it writes `output/city_summary_<YYYY-MM-DD_HH-MM-SS>.txt` and still streams the summary to stdout if you want to tee or filter it.
- `bash script/display_top_attribute.sh | less` — list the top three levels of keys to locate new attributes before coding against them.

## Coding Style & Naming Conventions
Python modules use 4-space indentation, type hints, and constants in `UPPER_SNAKE_CASE`. Keep helpers tight and explicit—favor functions like `is_time_limited` over inlined conditionals, and avoid broad `try/except`. Shell scripts stay POSIX-friendly Bash with `set -euo pipefail`, `snake_case` variable names, and fully quoted paths. Inputs, outputs, and git branches should include ISO dates so reports line up with in-game events.

## Testing Guidelines
There is no automated harness, so rely on deterministic sample cities. Before changing parsing logic, run `python3 script/city_analysis.py` against at least two files from `input/` and diff the resulting summaries with `output/`. Commit a fresh sample JSON whenever you touch new keys, and capture the expected analyzer text as proof in `output/` or the PR body.

## Commit & Pull Request Guidelines
Commits follow Conventional Commit prefixes (`feat`, `fix`, `chore`) plus a concise description, e.g., `feat: add city analysis script for FOE JSON data`. Keep each commit scoped to one behavior change and describe user-visible effects in the body when the summary format shifts. Pull requests should include the motivation, commands executed (`python3 script/city_analysis.py`, `bash script/save_city_json.sh`, etc.), updated artifacts or snippets, and links to any FOE patch notes or tracker issues.

## Data & Configuration Notes
City exports often include personal identifiers; never push raw `~/Documents/FOE/CityAnalysis/input/*.json`. Reference sanitized inputs under `input/` instead, and expand `script/script_config` whenever an age is added to the game. If your filesystem layout differs, override the directory constants locally rather than modifying them in commits.
