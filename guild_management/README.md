# GoE Guild Portal

This project provides `generate_treasury_report.py`, which creates:
- A guild-member PDF report (polished, visual, 2 pages)
- A technical Markdown report (detailed metrics and tables)

It also includes the no-runtime static GoE Guild Portal in `dashboard/`,
ready for Cloudflare Pages. The portal provides a home page, a treasury module,
an individual goods-contribution module, and a resource library. The first library
entry is the Official GoE Guild Expedition Lottery Rules. Treasury tools include
7/30/90-day period controls, age drill-downs, and a short goods watch list.
Contribution tools rank members using up to 30 days of positive goods records, including
building production and direct treasury contributions, and provide public
member-level aggregates. The most recent 500 contribution records per member and
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

### Forge Hammer treasury and contribution export (recommended)

`export_forge_hammer_treasury.py` reuses Forge Hammer's real Chrome storage and
CSV exporters. It never constructs a game request or chooses a request ID. The
command starts Chrome once with `Profile 3` and the installed companion
extension from `chrome/forge-hammer-treasury-exporter/`.

For treasury balances, the companion dispatches the game's own **open Guild
Treasury** action exactly once. Immediately beforehand it dispatches the game's
close-all-windows action once, which clears the visible window stack and queued
popups, then waits for window disposal to settle. It correlates Forge Hammer's
outgoing request and incoming response by the game-assigned request ID, waits
for the matching hourly and daily records, and exports `input/stats-YYYY-MM-DD.csv`. Because a
new Chrome profile begins with no Forge Hammer history, the launcher merges the
download into the longest compatible prior treasury CSV before rebuilding. A
current-day snapshot can therefore extend, but never replace, saved history.
If the browser session opens a pre-game page, the companion clicks the official
**Play** action once and selects the configured world display name (`Yorkton`
for `us24`) once before continuing. Both navigation steps are guarded against
repetition and persist only across that launched tab's redirects.

For contribution logs, the launcher reads the newest record timestamp from the
latest prior `input/guild-goods-contribution/GuildTreasury-*.csv` and subtracts
one hour. The companion opens the game's Message Center once so its contribution
module is initialized, opens the official Guild Contribution window, resets
Forge Hammer's in-memory export log, and advances through 10-row pages in
order. Each page is requested once with the game client's own request ID. It
stops when the first row on the current page is at or before the overlap cutoff,
or when the server reports that no page remains, then invokes Forge Hammer's
Guild Treasury Export Log feature. The launcher validates and imports the file
as `input/guild-goods-contribution/GuildTreasury-YYYY-MM-DD.csv`.

Official Google Chrome builds ignore the `--load-extension` command-line flag.
Install the companion once by opening `chrome://extensions`, enabling Developer
mode, choosing **Load unpacked**, and selecting
`chrome/forge-hammer-treasury-exporter/`. Keep that extension and Forge Hammer
enabled in Profile 3.

Before every run, close Google Chrome completely so the correct profile can be
started. The profile must already be signed in to the configured `FOE_WORLD`.
Then run:

```bash
../CityAnalysis/.venv/bin/python -B export_forge_hammer_treasury.py
```

The command is intentionally fail-closed:

- If both of today's validated CSVs already exist, it skips Chrome and refreshes
  both dashboards from those local inputs. If only one exists, it requests only
  the missing export.
- It launches the browser once, triggers each required game action once, and
  never retries a failed login, page load, treasury refresh, contribution page,
  or export.
- It exports only after Forge Hammer observes the matching response and stores
  its resource map in both the current-hour and current-day records.
- Contribution offsets must be `0, 10, 20, ...` with exactly one matching
  response each. Paging stops only at the requested overlap or when the
  response's total count proves that the server has no next page.
- It requires the existing 110-good schema and a unique current-date row.
- It requires Forge Hammer's **Guild Treasury Export Log** setting to be enabled.
- A failed or interrupted attempt is recorded in the Git-ignored, mode-600
  `.foe-forge-hammer-state.json`; another automatic attempt that day is refused.
  A user-authorized diagnostic retry requires the explicit
  `--allow-same-day-retry` flag and retains the previous attempt in the state file.

After saving `stats-YYYY-MM-DD.csv` directly under `input/` and
`GuildTreasury-YYYY-MM-DD.csv` under `input/guild-goods-contribution/`, the
command refreshes both dashboards by default. Treasury uses the validated
current-date CSV. Contribution refresh merges every CSV in its input directory
because those exports are overlapping partial snapshots. Use `--no-refresh`
only when CSV download and validation are intentionally being separated from
dashboard generation; `--rebuild` remains as a compatibility alias.

Use `--live-debug` for an explicitly authorized diagnostic attempt. It records
the one-shot navigation, game-assigned request IDs, matching responses, Forge
Hammer storage, pagination, and export milestones to a local
`foe-export-debug-*.json` download. Chrome remains open at the final success or
error state for manual inspection; the mode does not retry any game action.

Use `--dry-run` to validate the Chrome profile, Forge Hammer installation,
existing CSVs, and calculated contribution cutoff without opening the browser
or writing state. Browser paths, the profile directory, download directory, and
timeout can be overridden with the optional settings documented in
`.env.foe.example`.

### Daily automatic refresh and deployment

`automation/run_daily_refresh.py` is the fail-closed orchestration entry point
for unattended updates. A scheduled run requires a clean `main` branch that
exactly matches `origin/main`, runs the offline test suite before touching the
game, invokes the Forge Hammer exporter exactly once, validates both generated
datasets, and permits changes only under `dashboard/` plus the two source data
payloads. When publishing is enabled, it creates a generated-data-only `FOE-30`
commit and pushes it so Cloudflare Pages can deploy the refreshed dashboard.

The runner never retries. Before an export, it gracefully closes a stale Chrome
process only when that process was launched with the configured automation data
directory and profile. It refuses to close Chrome processes that do not match
both settings. A failed login, unresolved Chrome profile conflict, export,
validation, commit, or push ends that day's scheduled run and produces a local
notification. `KeepAlive` and `RunAtLoad` are deliberately disabled in the
LaunchAgent. Before publishing, the runner also compares the rebuilt treasury
dates with the previously published payload and refuses any update that drops a
historical snapshot. Logs and the process lock are local and ignored by Git.

For reliable unattended runs, use a Chrome data directory dedicated to this
workflow. Add these local-only settings to `.env.foe`:

```dotenv
FOE_CHROME_USER_DATA_DIR=~/.foe-automation-chrome
FOE_CHROME_PROFILE_DIRECTORY=Default
FOE_WORLD_NAME=Yorkton
```

Open that profile once for setup:

```bash
open -na "Google Chrome" --args \
  --user-data-dir="$HOME/.foe-automation-chrome" \
  --profile-directory=Default
```

Install Forge Hammer and the unpacked companion extension in that profile,
sign in to the configured world, then quit that Chrome instance. A dedicated
data directory allows ordinary Chrome windows to remain open; the preflight
check blocks only another process using the automation directory. If the normal
Chrome data directory remains configured, all Chrome windows must be closed at
the scheduled time.

Validate the complete scheduled path without making a game request:

```bash
../CityAnalysis/.venv/bin/python -B automation/run_daily_refresh.py --validate-only
```

Install the daily 2:15 AM local-time job with automatic generated-data
publishing:

```bash
../CityAnalysis/.venv/bin/python -B automation/install_launch_agent.py \
  --hour 2 --minute 15
```

Installation replaces the same LaunchAgent if it already exists, but never
starts it immediately. Use `--no-publish` for local-only dashboard generation,
or `--uninstall` to unload and remove the job.

### Direct game download

`sync_foe_treasury.py` logs in to Forge of Empires, downloads the current
guild-treasury snapshot and recent overlapping treasury transactions, and then
rebuilds both dashboard datasets. The overlap is intentional: contribution
exports are merged and deduplicated by the existing generator.

The treasury output mirrors Forge Hammer's Statistics export. It takes the
authoritative goods IDs and names from `StartupService.getData.goodsList`,
stores the `ClanMain` treasury resource map as a daily snapshot, fills omitted
resource IDs with zero, and writes `stats-YYYY-MM-DD.csv` in the same
semicolon-delimited format while retaining the existing daily history.

Create the local credential file once:

```bash
cp .env.foe.example .env.foe
chmod 600 .env.foe
```

Fill in `FOE_USERNAME` and `FOE_PASSWORD` in `.env.foe`. `FOE_WORLD` defaults
to `us24`. The credential file is ignored by Git, must not be committed, and is
parsed directly rather than sourced by a shell. Login cookies stay in memory
for the duration of the command.

On every run, the sync reads the exact ForgeHX bundle referenced by the logged-in
game page and extracts its client version and request-signature secret. It does
not use cached or hard-coded fallback values. If the bundle cannot be loaded or
parsed, the command stops before sending any game API request. Optional
`FOE_CLIENT_VERSION` and `FOE_SIGNATURE_SECRET` values are safety assertions:
the command aborts if either one differs from the live bundle.

Validate authentication without writing data:

```bash
../CityAnalysis/.venv/bin/python -B sync_foe_treasury.py --login-only
```

Send exactly one startup gateway request and write a permission-restricted,
Git-ignored diagnostic record containing only redacted protocol metadata:

```bash
../CityAnalysis/.venv/bin/python -B sync_foe_treasury.py --gateway-probe
```

Download only the current treasury snapshot using the startup, clan, and
treasury gateway sequence, then exit before any contribution request:

```bash
../CityAnalysis/.venv/bin/python -B sync_foe_treasury.py --treasury-only
```

Download both CSVs and rebuild the portal:

```bash
../CityAnalysis/.venv/bin/python -B sync_foe_treasury.py
```

Use `--download-only` to stop after writing the input CSVs. The treasury file
keeps the accumulated daily history and replaces today's row when rerun. The
contribution file contains a configurable overlap with existing history so a
rerun remains deterministic. Optional settings are documented in
`.env.foe.example`.

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
The Member Contributions page embeds its 30-day overview in the HTML and loads
a compact pre-aggregated summary for range changes and search. Detailed transaction
history is capped to the most recent 500 contributions in each fingerprinted
per-member JSON file and is fetched only after that member's passcode is
accepted, keeping raw history off the initial page-loading path.
The script supports both the older comma-delimited exports and the current
semicolon-delimited FoE export format. The contribution dashboard offers 3-,
7-, and 30-day windows, using the available history when it contains fewer than
30 days.

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
and returning the portal HTML with an incorrect MIME type. HTML responses use
`Cache-Control: no-transform` so Cloudflare does not inject an analytics beacon
that conflicts with the portal's strict Content Security Policy. Run the local
build and commit its generated dashboard files before deploying because
Cloudflare does not run a build command in this configuration.

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
