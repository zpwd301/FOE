# GoE Guild Portal

This project provides `generate_treasury_report.py`, which creates:
- A guild-member PDF report (polished, visual, 2 pages)
- A technical Markdown report (detailed metrics and tables)

It also includes the no-runtime static GoE Guild Portal in `dashboard/`,
ready for Cloudflare Pages. The portal provides a home page, a treasury module,
an individual goods-contribution module, and a resource library. The first library
entry is the Official GoE Guild Expedition Lottery Rules. Treasury tools include
7/30/90-day period controls, age drill-downs, and a short goods watch list.
Contribution tools rank members using all positive goods records, including
building production and direct treasury contributions, and provide public
member-level aggregates. Complete contribution records and
aggregated guild-goods usage by purpose, good, and era are hidden behind a
client-side assigned-passcode prompt; this is a convenience gate, not secure
authentication, because the static data is delivered to the browser. Keep
Cloudflare Access enabled for real access control. Successful member validation
is remembered in session storage for the current browser tab, including across
period changes and same-tab navigation.
Bronze Age goods are excluded from the treasury balance using the same rule as
the PDF report.

## Prerequisites

- The shared `../CityAnalysis/.venv` environment with the project dependencies installed

## How To Run

From this folder:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_report.py
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
../CityAnalysis/.venv/bin/python build_dashboard.py
```

Refresh the dashboard after adding a treasury export to `input/`:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_dashboard.py
```

Refresh contribution records after adding a `GuildTreasury-*.csv` export to
`input/guild-goods-contribution/`:

```bash
../CityAnalysis/.venv/bin/python generate_contribution_dashboard.py
```

Contribution exports are non-cumulative snapshots and may overlap. The refresh
script merges every CSV in that directory, removes duplicate transactions both
within and across files, and lets the newest overlapping copy supply the current
player display name. Do not remove older exports or select only the newest file
for a normal refresh.

The refresh script selects the newest CSV by modified time, writes
`site/data/treasury-data.js`, and rebuilds every portal page. Source assets stay
under `site/`; the deployable `dashboard/` directory contains only
content-fingerprinted CSS, JavaScript, data, icons, and responsive banner files.
This lets browsers cache assets efficiently without showing an older dashboard
after a deployment.
The script supports both the older comma-delimited exports and the current
semicolon-delimited FoE export format. The current site uses all available
data up to 90 days; when fewer than three months are present it says so in the
overview.

Treasury data is operational guild information. Protect the deployed dashboard
with a Cloudflare Access policy before adding a public custom domain. Static
headers prevent indexing, but they do not authenticate visitors.

### Cloudflare Pages deployment

The production portal is served from the root of `https://goe.z301.uk/`. Use
these Cloudflare Pages build settings:

```text
Build command: [leave empty]
Build output directory: dashboard
Root directory: guild_management
```

The committed `dashboard/` directory is the complete, deploy-ready site. Portal
links and fingerprinted assets are intentionally rooted at `/`. The included
`dashboard/_redirects` file permanently redirects old `/guild-management/...`
bookmarks to their corresponding root URLs, while `dashboard/_headers` defines
the production security and caching policy. The generated top-level `404.html`
also prevents Cloudflare Pages from treating missing asset paths as SPA routes
and returning the portal HTML with an incorrect MIME type. Run the local build
and commit its generated dashboard files before deploying because Cloudflare
does not run a build command in this configuration.

In the Cloudflare dashboard, add `goe.z301.uk` under the Pages project's
**Custom domains** settings. If the `z301.uk` zone is managed by the same
Cloudflare account, Cloudflare creates the required DNS record during setup.

For a local preview:

```bash
../CityAnalysis/.venv/bin/python -m http.server 8001 --directory dashboard
```

Portal routes:

- `/` — Guild Portal home
- `/treasury/` — live treasury dashboard
- `/treasury/contributions/` — individual guild goods contribution rankings and member drill-downs
- `/contributions/` — compatibility redirect to the Treasury contribution section
- `/resources/` — guild resource library
- `/resources/guild-expedition-lottery-rules/` — lottery rules

Resource metadata lives in `site/resources.json`; policy text lives in
`site/content/`. Add a resource entry and an HTML content fragment to extend
the library without changing the shared navigation or page layout.

## Common Examples

Run with a custom guild name:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_report.py --guild-name "GoE"
```

Run a different window:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_report.py --guild-name "GoE" --days 30
```

Run against a specific CSV:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_report.py --csv "input/guild-treasury-daily (6).csv"
```

Use a custom dip threshold:

```bash
../CityAnalysis/.venv/bin/python generate_treasury_report.py --dip-threshold 125000
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
