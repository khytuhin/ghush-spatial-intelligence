# Production audit — district and weekly extension

Audit completed locally on 2026-08-26. This extends the previously audited application; the source adapters, privacy guarantees, deterministic PySAL path and GitHub Pages architecture were retained.

## FEATURES IMPLEMENTED

- District/Zila default map using 64 real administrative polygons, with lazy ADM3 detail and all eight named division comparisons.
- Six KPIs with explicit synthetic/unverified refresh status.
- Eight consistent map modes, including money concentration, reporting share and conservative weekly direction.
- Department bars and Department × Division matrix with count, sum, pooled median and refusal selectors.
- Refusal comparisons by division, department and privacy-safe amount band.
- Population-share/representation-ratio panel and labeled division scatter when compatible denominators exist. Missing population remains unavailable.
- National/division/department weekly pulse, district playback, and automatically generated completed-week CSV.
- Schema-3 six-file publication bundle, shared hash, full validation, rollback and no-op preservation.
- Editorial responsive UI with system fonts, accessible controls/tables, restrained geometry and no new frontend framework.

The representation-ratio inequality typo in the attachment was corrected: 1 proportional, >1 over-represented, <1 under-represented.

### Issues found and fixed in this extension

| Finding | Fix |
|---|---|
| Default map only showed ADM3 and lacked trusted parent links | Added real ADM2 geometry and verified hierarchy |
| Coarse ADM1 boundaries had incompatible vintage/coverage | Used pinned district membership from the National Portal; did not weaken overlap checks |
| New weekly views could expose small temporal complements | Refined shared privacy atoms by week and rolling-window intersection |
| Amount-band subtraction could expose a rare subgroup | Withhold the entire band table whenever any underlying atom is unsafe |
| Higher-level medians risked a median-of-medians error | Compute pooled metrics from eligible lower-level records |
| Hidden-only department names could reveal source categories | Publish department options only from eligible records |
| Missing population could invite fabricated rates/ratios | Require complete cited compatible denominators; preserve nulls |
| Initial load would unnecessarily fetch all ADM3 geometry | Load upazila data only on drill-down |
| New artifacts were outside the old pair-only transaction | Stage/hash/validate/roll back all six files together |
| Failed release could leave chart controls usable | Gate chart controls on successful bundle validation |
| Drill-down could complete after the user changed geography | Discard stale pending drill selection |
| Trend fill was categorical but its legend numeric | Added matching categorical legend and explicit sparse-data state |
| Zero-report map values could display as unavailable | Preserve true zeros and valid coldspot statistics; constant-zero scales use a light fill |
| Malformed comma amounts such as 1,2 could become 12 | Validate conventional international/South Asian grouping |
| Polygon type alone did not guarantee valid rings | Validate actual polygon geometry as well as coordinate bounds |
| Windows line-ending conversion could alter CSV hashes | Added explicit LF policy in .gitattributes |
| Public CSV could carry spreadsheet-like labels | Reject formula-like administrative/department labels |

Previous audit fixes remain: stable IDs/deduplication, conservative matching, safe amount/outcome handling, no private coordinates, robots-aware bounded transport, complete pagination, disabled unverified scraper, deterministic public-only spatial statistics, null-safe filters, vendored MapLibre, strict public contracts, failure-safe deployment and least-privilege SHA-pinned Actions.

## FILES CHANGED

- Frontend: `site/index.html`, `app.js`, `core.js`, `styles.css`; new `analytics.js`.
- Pipeline: `analyze.py`, `run.py`, `publication.py`, `contracts.py`, `make_demo.py`; new `products.py`, `geography.py`, `bundle_contracts.py`.
- Geography: new `config/district_divisions.json`.
- Publication: all six files under `site/data`; existing ADM3/summary upgraded and district/division/weekly JSON/CSV added.
- Automation/tooling: both GitHub workflows, `package.json`, `.gitignore`, new `.gitattributes` and `pytest.ini`.
- Regression coverage: pipeline/workflow/frontend tests plus new `tests/test_products.py`.
- Documentation: README, CODEX, DEPLOYMENT and this AUDIT. Source investigation remains applicable and unchanged.

No new runtime dependency, frontend framework, proprietary font, hosting service or raw-report artifact was introduced.

## TEST RESULTS

- **74 Python tests passed**, including all original regression tests.
- **13 Node tests passed** for helpers, all modes, nulls, schema versions, complete filter matrices, ratios, CSV naming and escaping.
- Python compilation and JavaScript syntax checks passed.
- Strict six-file JSON/GeoJSON/CSV contract and content-hash validation passed.
- Actionlint 1.7.12 accepted both workflows; schedule, same-run deploy and conditional commit logic retained.
- `pip check` reported no broken requirements.
- OSV returned no known advisories for 31 pinned runtime Python packages, vendored MapLibre GL JS 4.7.1, pytest 9.1.1 and PyYAML 6.0.3 on the audit date. This is a point-in-time advisory check, not a security guarantee.
- Actual CLI snapshot run on 425 synthetic reports and full real geometry succeeded, publishing all six artifacts and a matching heartbeat.
- Full demo regeneration on 40,547 synthetic records preserved every artifact byte on unchanged input.
- Browser exercised all eight modes, department/period/division filters, district search, lazy upazila drill-down, chart selectors, playback, methodology dialog and dated CSV link.
- Browser tested at **390×844, 768×1024, 1440×900, 1920×1080**. No horizontal page overflow; mobile map begins within the first screen. Wide tables scroll inside their own containers.
- Normal root and GitHub Pages-style repository-subpath views had no browser console errors.
- Deliberate mixed release: retry message, blank KPIs and all data/chart controls disabled.
- Deliberately absent MapLibre runtime: clear fallback message; search, KPIs and analytics remained usable.

The browser checks ran in the available Chromium-based in-app browser, not a full Safari/Firefox/device matrix. Remote GitHub execution and production network performance have not been observed.

## PRIVACY TEST RESULTS

**PASS for the implemented suppression contract.**

Tests reject low weekly counts, rare time complements, unsafe band cells, extra private fields, points, invalid polygons, inconsistent parent/child totals, mixed release IDs, altered CSV and invented sparse trends. They verify hidden-only departments are absent, unknown dates are all-time only, missing/incomplete population is not invented, and valid denominator provenance/rates are correct.

The demo has **40,547 fetched/matched synthetic reports; 2 suppressed; 40,545 published**. Real private QA counters are redacted in public Actions logs.

A simulated failure on the final CSV replacement restored the complete previous bundle. Invalid publication attempts left existing files unchanged. Suppression protects the current release under this policy; it is **not differential privacy** and does not eliminate release-history or background-knowledge risks.

## PERFORMANCE RESULTS

| Local observation | Result |
|---|---|
| Full 40,547-report demo rebuild, real hierarchy and PySAL | 52.56 seconds on this host |
| Administrative coverage | 64 districts / 544 lower-level polygons |
| Initial overview JSON | 3,019,489 bytes raw; about 571,865 bytes gzip |
| Lazy ADM3 JSON | 5,695,354 bytes raw; about 1,306,190 bytes gzip |
| Weekly CSV | 153,634 bytes raw |
| Unchanged full rebuild | All six artifact hashes/bytes preserved |

Compression sizes are local gzip estimates, **not measured GitHub Pages transfer timings**. Vendor JS, CSS and basemap tiles are additional. No formal Lighthouse, load-test, mobile-network or hosted Core Web Vitals claim is made.

Geometry is reused between filter changes; the browser does no spatial joins/statistical fitting. Weekly/department/geographic aggregates are precomputed. The full-size dataset and interactive controls rendered successfully at all requested viewports.

PySAL emitted expected disconnected-component warnings for the real geography. Isolated areas are not assigned local labels.

## REMAINING LIMITATIONS

1. No owner-approved Ghush export or verified live response schema/coverage. The candidate API remains disallowed by robots. Cursor pagination would require another tested adapter.
2. No GitHub repository/remote/account authorization was supplied; hosted Actions and Pages remain unverified.
3. No population dataset was supplied. Rates, population shares, ratios and the corresponding scatter are intentionally unavailable in the included demo.
4. Suppression is conservative and may withhold many real records or all amount-band comparisons. Never relax it merely to populate a chart.
5. Sensitive live releases need an owner/privacy review, including differencing across releases and Git history.
6. Boundaries represent 2020; the pinned crosswalk intentionally stops on an incompatible district release. ADM3 includes urban units, not only current upazilas.
7. GitHub scheduling is best effort and can be disabled after public-repository inactivity; strict unattended SLAs need a separate authorized monitor. CARTO is an external tile dependency.
8. Individual local file renames are not power-loss atomic; hashes detect mixed bundles and Pages deploys one complete artifact.
9. An accidental nested backup remains in the original Downloads project's ignored `work/` folder because recursive removal was blocked by the environment. It is excluded from pytest, Git and the delivered clean ZIP. It can be removed through Explorer.

## LIVE-SOURCE STATUS

**BLOCKED pending an approved, robots-allowed export and schema/geography verification.**

The public frontend's JSON routes were discovered without calling them. No authentication, anti-bot control, robots restriction or backend access boundary was bypassed. Use an owner-provided allowed JSON/full CSV feed. See [SOURCE_DISCOVERY.md](docs/SOURCE_DISCOVERY.md).

## DEPLOYMENT STATUS

**Local code and synthetic artifact ready; not remotely deployed.**

The 12-hour workflow validates and commits only actual changes, generates CSV automatically and deploys in the same run. A failed refresh does not replace the current Pages deployment. Source configuration and GitHub repository settings are still required for live unattended operation.

## EXACT NEXT STEP

Extract the clean release ZIP, create/push the GitHub repository once, choose **Settings → Pages → GitHub Actions**, permit the approved workflow's generated-data commits, and run **Deploy and refresh GIS**. This launches the labeled demo.

Follow [DEPLOYMENT.md](DEPLOYMENT.md) for exact commands, repository/environment permissions and API/CSV variables/secrets. Enable live source variables only after the owner supplies an allowed approved feed and its first validated refresh succeeds.

## PASS/FAIL FOR PUBLIC DEMO DEPLOYMENT

**PASS — the labeled synthetic public demo is ready for the first GitHub deployment.**

**Live unattended Ghush updates: NOT YET.** The code supports 00:17/12:17 UTC URL ingestion with no recurring uploads after setup, but the approved live source and initial GitHub deployment remain outstanding.

## Evidence

[geoBoundaries ADM2 metadata](https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM2/), [ADM3 metadata](https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM3/), [National Portal district membership](https://bangladesh.gov.bd/views/district-list/), [Ghush source investigation](docs/SOURCE_DISCOVERY.md), [GitHub Pages workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [GitHub schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
