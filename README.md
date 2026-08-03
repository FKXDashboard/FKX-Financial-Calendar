# FKX Financial Calendar Repair v2.0

## Chosen design
A GitHub-hosted weekly mirror is the transport authority. Fair Economy / Forex Factory remains the content source.

Flow:
1. GitHub Action runs twice every Sunday.
2. It tries JSON, CSV, XML and ICS routes.
3. It normalizes successful data to `calendar/current_week.json`.
4. It archives the successful weekly artifact.
5. Google Apps Script reads the GitHub raw mirror instead of fetching Fair Economy directly.
6. The live sheet reports CURRENT, PARTIAL or STALE using the governed Sunday–Saturday week.

## Deployment
1. Create a private or public GitHub repository.
2. Copy this package into the repository root.
3. Commit and enable GitHub Actions.
4. Run the workflow manually once.
5. In Apps Script, replace the existing calendar code with `FKX_Financial_Calendar_v2_0.gs`.
6. Set `MIRROR_URL` in the Apps Script configuration to the raw GitHub URL for `calendar/current_week.json`.
7. Run `FKX_FINANCIAL_CALENDAR_REFRESH_V2_0`.
8. Keep the existing Sunday trigger pointed at the V2.0 entrypoint.

## Required raw URL form
https://raw.githubusercontent.com/<OWNER>/<REPO>/<BRANCH>/calendar/current_week.json

## Operational rules
- The expected week is always Sunday through Saturday in America/New_York.
- A successful mirror artifact for the expected week is GREEN.
- A current-week retained artifact with source warnings is YELLOW.
- A prior-week artifact is RED / STALE.
- Prior data are never cleared unless a valid current-week artifact is accepted.
