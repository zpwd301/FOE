# GoE Guild Portal

This project provides `generate_treasury_report.py`, which creates:
- A guild-member PDF report (polished, visual, 2 pages)
- A technical Markdown report (detailed metrics and tables)

It also includes the no-runtime static GoE Guild Portal in `dashboard/`,
ready for Cloudflare Pages. The portal provides a home page, a treasury module,
and a resource library. The first library entry is the Official GoE Guild
Expedition Lottery Rules. Treasury tools include 7/30/90-day period controls,
age drill-downs, and a short goods watch list. Bronze Age goods are excluded
using the same rule as the PDF report.

## Prerequisites

- Python 3 with `matplotlib` installed

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

Build the portal from the templates and content in `site/` without changing
treasury data:

```bash
python3 build_dashboard.py
```

Refresh the dashboard after adding a treasury export to `input/`:

```bash
python3 generate_treasury_dashboard.py
```

The refresh script selects the newest CSV by modified time, writes
`dashboard/data.js`, and rebuilds every portal page. The build publishes
content-fingerprinted copies of the dashboard CSS, JavaScript, and data and
removes obsolete fingerprinted copies. This lets browsers cache assets
efficiently without showing an older dashboard after a deployment.
The script supports both the older comma-delimited exports and the current
semicolon-delimited FoE export format. The current site uses all available
data up to 90 days; when fewer than three months are present it says so in the
overview.

Treasury data is operational guild information. Protect the deployed dashboard
with a Cloudflare Access policy before adding a public custom domain. Static
headers prevent indexing, but they do not authenticate visitors.

For a local preview:

```bash
python3 -m http.server 8001 --directory dashboard
```

Portal routes:

- `/` — Guild Portal home
- `/treasury/` — live treasury dashboard
- `/resources/` — guild resource library
- `/resources/guild-expedition-lottery-rules/` — lottery rules

Resource metadata lives in `site/resources.json`; policy text lives in
`site/content/`. Add a resource entry and an HTML content fragment to extend
the library without changing the shared navigation or page layout.

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
