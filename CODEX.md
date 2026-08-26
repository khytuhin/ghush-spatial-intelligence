# Project maintenance guide

The user's request controls scope. This file documents maintenance conventions, not authorization to access sources.

- Extend the existing vanilla JavaScript/MapLibre and Python pipeline; do not add a frontend framework or change hosting without a specific request.
- Sources belong in `pipeline/sources/`; return the canonical report table. Never bypass authentication, anti-bot controls, rate limits, robots policies, or a denied API by using a backing service or DOM.
- Ghush is not a verified live connector. Prefer an owner-approved, allowed complete JSON/CSV export. The scraper remains disabled.
- `geography.py` assigns ADM3 parents by validated overlap and ADM2 parents through the pinned National Portal crosswalk. Do not infer parents from report text or silently accept a new boundary vintage.
- Default map is ADM2 district. Division comparisons are national; ADM3 detail is lazy-loaded.
- Public schema **3** is the complete six-file bundle defined in `products.NAMES`. Keep every feature's `slices["PERIOD|DEPARTMENT"]` matrix and shared content ID. The legacy pair helpers are internal compatibility tests, not the deployed dashboard contract.
- Every new breakdown must refine or respect the shared privacy partition. Do not compute a chart directly from hidden raw rows.
- Privacy is mandatory: whole-upazila suppression across department × week × rolling-window atoms, monetary/outcome withholding, and complete amount-band-table withholding.
- Higher geographic totals and medians use eligible lower-level records. Never average medians or sum rates. Population rates/ratios require compatible cited denominators; do not invent them.
- Never serialize report IDs, narratives, coordinates, individual amounts, arbitrary departments or raw QA examples. Only administrative polygon coordinates are public.
- Exact QA counters are private; public Actions logs redact hidden/fetched/matched totals.
- CSV is the one approved public CSV, generated from validated completed-week district/department cells. No raw CSVs, formula-like labels or timestamp-only archive copies.
- `publish_bundle` stages and validates all artifacts, rolls back ordinary failures, and preserves no-op bytes/timestamps. Update validators, commit allowlist, tests and docs whenever adding a file.
- Deploy only `site/`, never the repository root. Keep the operational heartbeat ignored.
- Preserve default-branch serialization, least-privilege jobs, SHA-pinned actions and same-run Pages deployment. No force-push or dependence on bot commits retriggering workflows.
- Keep the 12-hour schedule. Do not imply that GitHub's scheduler is a guaranteed SLA or that source access is already approved.
- UI: system Helvetica Neue/Helvetica/Arial, editorial grid, tabular numerals, small radii, restrained colors. Reuse geometry and fetch ADM3 only on demand.
- All filters, legends, rankings and details must agree. Weekly and rolling contexts must be explicit. Unavailable is not zero.
- Validate with `python -m pytest -q`, `python -m compileall -q pipeline`, `python -m pipeline.contracts site/data`, `node --check site/app.js`, `node --check site/core.js`, `node --check site/analytics.js`, and `node --test tests/frontend.test.js`. Lint workflows with Actionlint.
- Test 390×844, 768×1024, 1440×900 and 1920×1080, repository subpaths, corrupt releases, missing WebGL, keyboard controls and no horizontal page overflow.
- Suppression is not differential privacy. Live republication needs owner permission and a release-history privacy review.
