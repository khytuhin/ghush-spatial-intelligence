# Ghush source investigation

Inspected on 2026-08-26 UTC (2026-08-25 America/Chicago). This records observations, not permission to reuse data.

## Evidence

An ordinary unauthenticated HTTPS GET of [the public homepage](https://www.ghush.site/) returned HTTP 200. Its referenced, publicly served JavaScript was inspected. The client contains:

- a GET request to `/api/reports` with `offset`, `limit`, `sort` and optional filters;
- response checks for a `reports` array and integer `total`;
- a GET request to `/api/reports/summary`;
- separate report-submission and confirmation operations, which are outside this project's scope.

The [robots policy](https://www.ghush.site/robots.txt) returned HTTP 200 and:

```text
User-Agent: *
Allow: /
Disallow: /api/
```

**No requests were made to the discovered API routes.** Their live response schemas, pagination stability, data completeness and authorization requirements were not verified.

The client also references a backing service for a narrowly scoped public feature. Its client configuration was not used to query the backing service. Accessing that service to work around the API restriction is not an acceptable ingestion route.

## Recommended route

Request an owner-provided, read-only JSON endpoint or complete CSV export, explicit permission for scheduled access and aggregate republication, and an allowed robots policy for the export route. Prefer a versioned full snapshot, or stable pagination with IDs and totals, over DOM scraping.

The project can then use `load_api` or `load_csv_feed` without changing the map. API mode requires an adapted, verified mapping. An HTML scraper remains disabled because selectors, completeness and access permission are not verified; it is not a fallback for a denied route.

The automation approval variable is an operator attestation, not a bypass switch. It does not override robots restrictions, authentication failures or rate limits.

## Discovery-helper corrections

The original helper started a browser and saved complete JSON response bodies. That risked persisting descriptions, coordinates or unrelated payloads, and could automatically call denied API routes as the page loaded. It also truncated serialized JSON by characters, potentially creating invalid output.

The replacement reads only allowed HTML and same-origin JavaScript, extracts endpoint paths, and stores a small valid metadata document under ignored `data/debug/`. It never executes the site, calls candidate APIs, records response bodies or captures tokens/query strings.

Robots parsing uses Protego for specific-path precedence. A regression test covers Ghush's `Allow: /` followed by `Disallow: /api/`; a first-match parser would incorrectly permit that API.

## Remaining source questions

1. Will the owner approve access/reuse and supply an allowed, reliable endpoint?
2. Do published reports contain sufficiently precise, standardized upazila/district fields? District-only reports cannot safely be assigned to an upazila.
3. What are the exact JSON keys, timestamps, outcome values and amount units?
4. Are pagination ordering and totals stable while new reports or moderation changes occur?
5. What attribution, retention, removal and request-rate rules apply?

Until these are answered and a real first refresh passes, the site remains a synthetic preview rather than a live Ghush GIS.
