# Repository Guidelines

## Project Structure & Module Organization
All automation lives in `script/`. `city_analysis.py` ingests the latest `city_*.json` from `~/Documents/FOE/CityAnalysis/input`, prints the map/troop breakdown, and drops `output/city_summary_<YYYY-MM-DD_HH-MM-SS>.txt`. `kit_producer_report.py` scans `CityEntities` for kit-producing buildings, emitting two ranked text reports plus `output/kit_buildings_<ERA>.xlsx`. Clipboard helpers (`save_city_json.sh`, `display_top_attribute.sh`) sit alongside the age lookup in `script/script_config`. Only commit sanitized fixtures in `input/`; generated outputs stay ignored, so stash any samples under a dedicated branch if they must be shared.

## Build, Test, and Development Commands
- `bash script/save_city_json.sh` — dump the FOE clipboard export into `~/Documents/FOE/CityAnalysis/input/city_<date>.json` and prettify via `jq`.
- `python3 script/city_analysis.py` — produce the daily city summary; redirect stdout if you need a diffable artifact.
- `python3 script/kit_producer_report.py --era VirtualFuture` — rebuild `one_up_kit_buildings_<ERA>.txt`, `renovation_kit_buildings_<ERA>.txt`, and the Excel workbook in `output/`.
- `bash script/display_top_attribute.sh | less` — survey the JSON topography before touching new keys.

## Coding Style & Naming Conventions
Python uses 4-space indent, explicit type hints, and module-level constants (`UPPER_SNAKE_CASE`). Favor small, pure helpers over inlined logic so they can be reused across analyzers (e.g., `format_probability`, `extract_size`). Bash scripts must start with `#!/usr/bin/env bash`, use `set -euo pipefail`, quote paths, and stick to `snake_case`. Filenames, branches, and exported assets should carry ISO timestamps for traceability.

## Testing Guidelines
No automated suite exists. When altering parsers, run `python3 script/city_analysis.py` plus `python3 script/kit_producer_report.py --era <TargetEra>` against at least two archived inputs. Compare the resulting `output/` artifacts (text + Excel) with prior runs and call out intentional diffs in the PR. Add a new JSON fixture any time you rely on previously unseen keys or eras and note which scripts were exercised.

## Commit & Pull Request Guidelines
Use Conventional Commit prefixes (`feat`, `fix`, `docs`, `chore`) and keep commits focused (config changes separate from data updates). PRs must include: summary, linked ticket or FOE patch note, exact commands executed, and snippets or attachments from updated outputs (including the Excel diff when relevant). If a workflow change impacts other agents (e.g., new input paths), highlight it in the PR body and ping reviewers.

## Data & Configuration Notes
Never push raw exports from `~/Documents/FOE/city`. Continue to store sanitized snapshots under `CityAnalysis/input/` but keep them out of Git unless required for reproducibility. Extend `script/script_config` whenever Inno adds an era, and update helper constants (e.g., `TARGET_KIT_SUBTYPES`) in tandem. Developers with different directory layouts should override the path constants locally rather than editing them in commits.
