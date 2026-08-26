# Ghush Spatial Intelligence

A static, privacy-preserving GIS dashboard for **unverified public-service payment reports in Bangladesh**. This extends the audited MapLibre/vanilla JavaScript and Python/GeoPandas/PySAL project; it does not replace it with a framework.

**The included release is a synthetic public demo, not a live Ghush feed.** It uses real administrative boundaries and illustrative reports. Ghush's discovered API routes remain unapproved and blocked by its robots policy; no restricted API was called.

Read [AUDIT.md](AUDIT.md), [DEPLOYMENT.md](DEPLOYMENT.md), [CODEX.md](CODEX.md), and [source discovery](docs/SOURCE_DISCOVERY.md).

## What the dashboard includes

- District/Zila map by default: 64 districts; drill into publishable upazila/urban-unit detail.
- Six KPIs: published reports, reported amount, pooled median, refusal, represented districts, verified refresh status.
- Eight modes: report activity, money concentration, median amount, refusal, reports per 100k, reporting concentration, Gi* hotspot, weekly trend.
- Eight-division comparison, department bars, Department × Division matrix, refusal by division/department/amount band.
- Reporting-share/population-share comparison and representation ratio; unavailable without compatible population data.
- Weekly national/division/department pulse, district playback, and an automatically generated weekly CSV.
- System Helvetica Neue/Helvetica/Arial typography, restrained editorial styling, accessible tables, responsive layouts and a usable fallback without WebGL.

The synthetic release has 40,547 input reports, 2 suppressed reports, and 40,545 published reports. These are demonstration counts, not observations about Bangladesh.

## Preview and test

From the project root, with Python 3.12 and Node 22 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q pipeline
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pipeline.contracts site/data
node --check site/app.js
node --check site/core.js
node --check site/analytics.js
node --test tests/frontend.test.js
py -m http.server 8080 --directory site
```

Open [localhost:8080](http://localhost:8080), not a file URL. No npm installation/build step is required. MapLibre JS/CSS is vendored; CARTO raster tiles require network access. When tiles or WebGL fail, the data remains available through search, tables and charts.

Runtime dependencies are pinned in `requirements.lock.txt`; no dependency changes were needed for this extension.

## Modular architecture

| Module | Responsibility |
|---|---|
| `pipeline/sources/` | Approved JSON, hosted CSV, private snapshot, disabled scraper extension point |
| `pipeline/geography.py` | Validated administrative hierarchy and parent overlap checks |
| `pipeline/analyze.py` | Normalization, matching, shared privacy partition, PySAL |
| `pipeline/products.py` | District/division/weekly products, exact pooled metrics, CSV |
| `pipeline/contracts.py`, `bundle_contracts.py` | Strict schema, geometry, privacy, rollup and CSV validation |
| `pipeline/publication.py` | Content hash, staging, no-op detection and rollback |
| `pipeline/run.py` | Fetch → validate → publish → operational heartbeat |
| `site/core.js`, `app.js`, `analytics.js` | Pure helpers, MapLibre interaction, analytical views |
| `.github/workflows/` | Tests, 12-hour refresh and Pages deployment |

## Public schema 3

The entire release is one six-file bundle:

| File | Content |
|---|---|
| `site/data/district_metrics.geojson` | Default ADM2 geometry, period/department metrics, trends |
| `site/data/adm3_metrics.geojson` | ADM3 geometry, parent links and metrics; fetched only on drill-down |
| `site/data/summary.json` | National metrics, metadata, denominator provenance, amount bands, spatial statistics |
| `site/data/division_summary.json` | All eight divisions, department matrices, trends and amount bands |
| `site/data/weekly_summary.json` | District, division and national weekly aggregates |
| `site/data/weekly_summary.csv` | Safe completed-week district × department export |

JSON products share one SHA-256 `data_id`. The hash includes the exact CSV content and excludes only publication IDs and generated timestamp. A no-op preserves bytes and timestamps. The optional ignored `refresh.json` reports a successful source check without a timestamp-only commit.

Feature slices retain `properties.slices["PERIOD|DEPARTMENT"]`. Weekly series use `"YYYY-MM-DD|DEPARTMENT"`. Null means unavailable/withheld; zero means zero published reports. District and division totals include only publishable lower-level records. Medians use the pooled eligible records, not medians of medians.

CSV columns:

```text
week_start,division,district,department,published_reports,reported_amount,median_amount,refusal_rate
```

The stored CSV has one stable path; the browser downloads it as `ghush_spatial_weekly_YYYY-MM-DD.csv`, dated with the latest completed week. It contains up to 52 weeks, completed Monday–Sunday UTC weeks only, no duplicate ALL rows, no low-count cells and no individual amounts/IDs/coordinates/descriptions. A blank monetary/rate field remains unavailable. No historical copies are generated just to change filenames.

## Ingestion and matching

All adapters return this normalized table:

```text
report_id,reported_at,department,service,location,upazila,district,division,amount,outcome
```

Stable IDs and an upazila/location are required. Source text never determines geographic parent membership. Unique exact place matching is preferred; district names disambiguate duplicate upazila names. Fuzzy matching is off by default. Reviewed overrides can target a stable shapeID. District-only reports are not assigned to guessed upazilas.

Empty exports, future timestamps, conflicting IDs, incomplete pagination and match rates below 80% fail without publication. Unknown dates enter all-time totals only. Amount parsing accepts Bengali digits, currency prefixes/suffixes and conventional international/South Asian grouping; malformed separators, ranges and ambiguous units are not guessed. Departments and outcomes use canonical allowlists.

For a private local research snapshot:

```powershell
.\.venv\Scripts\python.exe -m pipeline.run --source snapshot --input data/raw/ghush_snapshot.csv
```

Keep raw snapshots and logs out of Git and `site/`. Scheduled jobs accept only approved hosted API/CSV modes; there are no recurring manual uploads. Configure the adapter and owner-approved URL as described in [DEPLOYMENT.md](DEPLOYMENT.md).

API mapping supports a documented complete JSON response or stable offset pagination with unique IDs, declared total, page cap and delay. Cursor APIs require a new tested adapter. Source changes require no frontend changes.

## Privacy and interpretation

Public k=5 is mandatory; k cannot be below 3.

1. A rare upazila × department × week × disjoint rolling-window atom withholds that entire upazila across every view. Unknown-date atoms are included.
2. Monetary and outcome fields have additional area-wide withholding. Any unsafe amount-band atom withholds the **entire** amount-band table across periods, departments and divisions, preventing complementary disclosure.
3. Districts, divisions, national KPIs, CSV and spatial statistics derive only from the same eligible lower-level records. Hidden-only department labels are not disclosed.
4. Exact local/private Actions counters show fetched, normalized, matched, unmatched, suppressed and published counts. Public Actions logs redact private counters because subtraction can disclose suppressed reports.
5. Suppression is not differential privacy. Comparisons across releases, homogeneous groups and external knowledge remain risks; a real sensitive launch still needs a privacy review.

Reports are allegations, not proof. Reporting concentration means share of national **published reports**, not a corruption score. Representation ratio = report share / population share: 1 is proportional, above 1 over-represented, below 1 under-represented. The attachment's contradictory inequality was corrected.

Refusal rate divides refused reports by all published reports, including unknown outcomes. Weekly direction uses the last two complete weeks, at least max(10, 2k) reports in each, and both a 20% and k-report change. Otherwise it is stable or insufficient. Trend and the pulse are explicitly independent of the rolling map window; single-week mode does not invent upazila, band, or spatial statistics.

PySAL uses public counts, Queen adjacency, seed 42, one worker and 99 permutations. Global Moran, Local Moran and Gi* are preserved at the appropriate levels. Local two-sided tests exclude islands; disconnected-component warnings are expected. No multiple-testing correction is applied.

## Boundaries and population

geoBoundaries gbOpen ADM2 has 64 districts, ID `BGD-ADM2-16705992`; ADM3 has 544 polygons, ID `BGD-ADM3-5055444`. Both represent 2020 and cite BBS/OCHA, CC BY 3.0 IGO. ADM3 includes urban units: this is **not** a claim that Bangladesh currently has 544 upazilas.

Every ADM3 parent passed ≥95% projected overlap with its ADM2 parent. The coarse 2015 ADM1 layer was unsuitable for reliable parent assignment; division membership instead uses the [National Portal district list](https://bangladesh.gov.bd/views/district-list/), pinned to the district boundary ID in `config/district_divisions.json`. Changed IDs fail for review.

Population data is optional and absent from the demo. A private/approved reference CSV must contain `shapeID,population,source,boundary_id`. IDs must be unique, values positive, source cited and boundary ID compatible. Complete coverage is required for district/division/national comparisons. Sources are carried into the public metadata. The file is ignored by default; unattended population use needs a deliberate approved reference-data deployment or separately reviewed downloader.

## Releases

The workflow runs at **00:17 and 12:17 UTC**. It tests and validates all six artifacts, commits only actual generated-data changes, then deploys `site/` in the same run. Failed fetches, validation, writes, commits or deployments preserve the last successful Pages release. Ordinary local replacement failures roll back the whole bundle; power loss across separate filesystem renames is not atomic, so hash checks detect mixed files.

GitHub scheduling is best effort and public-repository schedules can stop after inactivity. See the exact setup, source gate and limitations in [DEPLOYMENT.md](DEPLOYMENT.md).

To regenerate the synthetic release: `python -m pipeline.make_demo`. It downloads/caches public boundaries and refuses to overwrite a non-demo publication. Do not run it as a live refresh.
