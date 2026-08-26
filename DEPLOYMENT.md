# Exact GitHub Pages deployment instructions

## Status

**Public synthetic demo: ready for deployment. Live Ghush integration: not approved or enabled.**

No GitHub repository/remote or account authorization was supplied. Nothing has been pushed or deployed remotely. Local verification is documented in [AUDIT.md](AUDIT.md).

The current Ghush frontend references JSON API routes, but its readable robots policy disallows `/api/`. Those routes were not called. An approval variable does not override that restriction.

## 1. Initial repository setup

Use the supplied clean release ZIP, or the modified project folder. The ZIP includes hidden `.github`, `.gitattributes` and `.gitignore` files; preserve them. It excludes caches, raw reports, heartbeat, virtual environments and scratch backups.

Create an empty repository named `ghush-spatial-intelligence` on GitHub, without an initial README/license/gitignore. Public repositories support Pages on GitHub Free; private-repository Pages availability depends on your plan. Prefer private source history/QA logs when handling a sensitive real source.

In PowerShell, **from the extracted project root**:

```powershell
git init
git branch -M main
git add .
git status --short
```

Review the staged list: no credentials, raw snapshots, `data/debug`, `data/boundaries`, `work/`, private denominators or virtual environment. Only the six schema-3 files under `site/data` are committed public data.

Replace `YOUR_USERNAME`:

```powershell
git commit -m "Deploy district GIS dashboard"
git remote add origin https://github.com/YOUR_USERNAME/ghush-spatial-intelligence.git
git push -u origin main
```

If using an existing Git repository, do not reinitialize it or add a duplicate remote; commit and push the changes on its approved default branch. Authenticate through your normal GitHub login/credential manager. Never put a token in a remote URL or committed file.

## 2. Enable Pages and Actions

1. **Settings → Pages → Build and deployment → Source → GitHub Actions**.
2. **Settings → Actions → General**: allow the official GitHub actions used here. Permit **Read and write permissions** for the generated-data commit. Organization policy may override this.
3. Check branch rules. The repository's Actions token must be allowed to commit generated data on the default branch under an owner-approved policy. Do not bypass rules or force-push. A blocked push stops deployment.
4. **Settings → Environments → github-pages**: allow the default branch. Unattended deployment requires no mandatory reviewer/manual wait gate; follow your organization's policy if it requires approval.
5. **Actions → Deploy and refresh GIS → Run workflow → main**.

With no source configured, a push/manual run deploys the clearly labeled demo. Scheduled runs skip refresh/deployment until a source is configured. If the first push ran before Pages settings were ready, rerun now.

The workflow installs pinned Python dependencies, runs Python/Node tests, validates all six public artifacts, and deploys **only `site/`**. Expected URL:

```text
https://YOUR_USERNAME.github.io/ghush-spatial-intelligence/
```

The deployment job shows the exact URL. Repository-subpath assets, data, lazy ADM3 loading and CSV URLs are relative.

## 3. Obtain an allowed source

Ask the Ghush owner for a stable read-only complete JSON/CSV export, explicit permission for 12-hour automated access and public aggregate reuse, and a route permitted by a readable robots policy.

Verify stable IDs, date/time-zone semantics, normalized department/outcome values, amount units, upazila/district coverage, full-export or pagination completeness, removals/moderation, request limits and attribution terms. Prefer a versioned complete JSON snapshot.

Do not use a backing database, alternate hostname, browser identity spoofing, CAPTCHA solver or HTML scraper to evade a denied route. The scraper remains disabled.

### JSON/API mode

Copy `config/api_mapping.example.json` to `config/api_mapping.json`, adapt every mapped field to the authorized response, test locally, then commit the reviewed mapping.

The example is **not** a verified Ghush endpoint contract. Supported modes are stable offset/limit pagination with an integer total, or explicitly declared complete single-response JSON. Cursor/page-number APIs need a tested adapter before enabling them.

Under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value |
|---|---|
| `GHUSH_SOURCE` | `api` |
| `GHUSH_AUTOMATION_APPROVED` | `true`, only after approval |

Under **Secrets**:

| Secret | Value |
|---|---|
| `GHUSH_API_URL` | Owner-approved, robots-allowed HTTPS endpoint |
| `GHUSH_API_TOKEN` | Authorized bearer token, only if required |

### Hosted CSV mode

Set variables `GHUSH_SOURCE=csv` and `GHUSH_AUTOMATION_APPROVED=true`. Set secret `GHUSH_CSV_URL` to the approved complete export URL, plus `GHUSH_API_TOKEN` if needed. Column names must follow README's normalized schema.

This is automatic URL ingestion; **no periodic upload is required**. Private local snapshots are for research/QA, not the scheduled source.

### Optional population data

The demo intentionally has no population denominators. To enable rates/representation, supply a cited complete ADM3 reference table with compatible boundary IDs. The default reference file is ignored. For unattended use, deliberately deploy an approved non-sensitive reference dataset or add a separately reviewed downloader. Never populate missing values with guesses.

## 4. Verify the first real refresh

Manually run **Deploy and refresh GIS** once after source configuration. Confirm:

- Fetch, matching, tests, complete bundle validation, conditional commit and deployment all succeed.
- The site stops showing the synthetic label and shows a current verified source-check time.
- Reviewed place matches are correct and all expected source pages were fetched.
- Districts, division totals, weekly CSV and filter values reconcile.
- Published files contain no report points, IDs, narratives, individual amounts or raw snapshots.

The minimum match rate is 80%. Do not reduce it to make an unverified feed pass. District-only rows cannot be placed into guessed upazilas.

## 5. Unattended operation

The configured schedule is **00:17 and 12:17 UTC**. After the approved source and GitHub settings are in place, fetching, processing, weekly CSV generation and deployment require no manual uploads.

Only these changed generated files may be committed:

```text
site/data/adm3_metrics.geojson
site/data/district_metrics.geojson
site/data/summary.json
site/data/division_summary.json
site/data/weekly_summary.json
site/data/weekly_summary.csv
```

Identical content creates no commit/push. A new completed week or a changed rolling window is a real data change. The source-check heartbeat is deployed but ignored by Git. Bot commits do not need to trigger another workflow: deployment happens in the same run.

A failed source, test, validation, write or commit uploads no new Pages artifact. Failed deployment leaves the previous successful Pages deployment available. Enable GitHub failure notifications; the UI warns when a recent successful source check is not verified or is more than 36 hours old.

GitHub schedules are best effort: runs can be delayed/dropped and public-repository schedules may be disabled after 60 days without activity. A strict indefinite SLA needs an external authorized monitor/dispatcher, which is not configured here. No fake commits are made to keep a schedule alive.

## Operational safeguards and remaining reviews

- Public Actions logs redact fetched/matched/suppressed private totals; published counts remain visible. Local/private Actions runs provide exact QA counters.
- K-suppression is not differential privacy. Obtain a release-history privacy review before sensitive live publication.
- Validate the 2020 administrative vintage and CC BY 3.0 IGO attribution. The pinned district crosswalk must be reviewed if the boundary ID changes.
- The Actions boundary cache is `bgd-hierarchy-v3-...`. Remove it through Actions → Caches only when deliberately reviewing a refreshed boundary vintage. `--force-boundaries` also forces refresh locally; incompatible IDs fail closed.
- Review CARTO usage terms/capacity for expected traffic. Missing tiles do not remove the administrative data.
- Local multi-file replacement cannot be power-loss atomic. Staging/rollback handles ordinary failures and shared hashes detect mixed files; Pages receives one complete artifact.
- In the original Downloads folder, an accidentally nested backup remains under ignored `work/` because the environment blocked its recursive removal. It is not built, tested, committed or included in the clean ZIP. You may remove that scratch folder in Explorer; do not remove the source folders.

## References

[GitHub custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [scheduled workflow limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), and [Ghush robots policy](https://www.ghush.site/robots.txt).
