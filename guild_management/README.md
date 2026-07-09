# Guild Treasury Report Script

This project provides `generate_treasury_report.py`, which creates:
- A guild-member PDF report (polished, visual, 2 pages)
- A technical Markdown report (detailed metrics and tables)

It also includes `dashboard/`, a no-build static treasury dashboard ready for
Cloudflare Pages. It provides an overview, 7/30/90-day period controls, age
drill-downs, and a short goods watch list. Bronze Age goods are excluded using
the same rule as the PDF report.

## Prerequisites

- Python virtual environment:
  - a Python virtual environment
- `matplotlib` installed in that venv

## How To Run

From this folder:

```bash
python3 generate_treasury_report.py
```

This uses defaults:
- `--guild-name GoE`
- `--days 60`
- `--input-dir input`
- `--output-dir output`
- `--dip-threshold 110000`

## Static Dashboard

Refresh the dashboard after adding a treasury export to `input/`:

```bash
python3 generate_treasury_dashboard.py
```

The script selects the newest CSV by modified time and writes
`dashboard/data.js`. It supports both the older comma-delimited exports and
the current semicolon-delimited FoE export format. The current site uses all
available data up to 90 days; when fewer than three months are present it says
so in the overview.

To deploy, connect this repository to Cloudflare Pages and set the build output
directory to `dashboard`. No build command is required. For a local preview:

```bash
python3 -m http.server 8001 --directory dashboard
```

## Common Examples

Run with a custom guild name:

```bash
python3 generate_treasury_report.py --guild-name "GoE"
```

Run a different window:

```bash
python3 generate_treasury_report.py --guild-name "GoE" --days 30
```

Run against a specific CSV:

```bash
python3 generate_treasury_report.py --csv "input/guild-treasury-daily (6).csv"
```

Use a custom dip threshold:

```bash
python3 generate_treasury_report.py --dip-threshold 125000
```

## Input Rules

- The script reads the latest `*.csv` in `input/` by modified time unless `--csv` is provided.
- Bronze Age goods are always excluded from all calculations:
  - `Wine`, `Dye`, `Marble`, `Lumber`, `Stone`
- Goods-level CSV is recommended.
- Optional mapping file for goods-to-age:
  - `input/good-age-map.csv` with headers: `Good,Age`
  - If missing, the script attempts to infer age groups by FoE goods column order.

## Output Files

Files are written to `output/` and include guild name + analysis date range:

- PDF:
  - `<guild-slug>-guild-treasury-report-<YYYYMMDD>-to-<YYYYMMDD>-<days>d.pdf`
- Technical Markdown:
  - `<guild-slug>-guild-treasury-report-<YYYYMMDD>-to-<YYYYMMDD>-<days>d-technical.md`

Example:
- `goe-guild-treasury-report-20251218-to-20260216-60d.pdf`
- `goe-guild-treasury-report-20251218-to-20260216-60d-technical.md`

## Script Options

```text
--guild-name      Guild name shown in report title and filename
--input-dir       Folder containing treasury CSV files
--csv             Specific CSV file to analyze
--days            Analysis window in days (default: 60)
--output-dir      Folder to write reports
--good-age-map    Optional Good->Age mapping CSV
--dip-threshold   Threshold for low-stock goods list (default: 110000)
```
