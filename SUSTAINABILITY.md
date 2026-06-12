# SUSTAINABILITY.md

## Commitment

- Keep the site small, static, and easy to maintain.
- Favor generated data and plain HTML over heavier client-side logic.
- Treat performance, accessibility, and sustainability as shared constraints.
- Make trade-offs explicit when a change increases weight or complexity.

## Current profile

- The site is deployed as static files through GitHub Pages.
- External runtime dependencies are limited to the map page's Leaflet and Papa Parse.
- Event and venue data is generated from repository files and scripts.

## Guardrails

- Prefer the smallest practical dependency set.
- Avoid adding new third-party requests unless they are essential.
- Reuse existing templates, CSS, and generated data pipelines.
- Remove dead code, unused assets, and redundant duplication.
- Prefer deterministic scripts over ad hoc manual steps.

## CI and review

- Track page weight and request count for the main pages.
- Re-check the homepage, calendar, and map after significant template or data changes.
- Pair sustainability review with accessibility review before merge.

## AI policy

- Prefer deterministic tools first.
- Keep prompts scoped to the specific task.
- Avoid repeated or broad AI calls when a local edit or script will do.
- Record significant AI-assisted changes in commit or PR notes when applicable.

## Ownership and cadence

- Owners: current maintainers.
- Review cadence: at least monthly, and before releases.
- Exceptions: document the reason and an expiry date.

## Definition of Done

- The change does not create avoidable page bloat or extra network cost.
- The site still builds from local source data without manual cleanup.
- Any increase in footprint is justified and tracked.