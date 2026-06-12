# ACCESSIBILITY.md

## Conformance

- Target: WCAG 2.2 AA.
- Applies to the static pages, the venue map, generated calendar views, and content contributed through issue templates.

## Current guardrails

- `npx playwright test` runs axe-core checks in CI through the GitHub Pages workflow.
- The homepage test suite checks for no WCAG 2.2 AA violations, a skip navigation link, heading hierarchy, image alt text, keyboard focusability, and a valid `lang` attribute.
- Visible focus, semantic HTML, and descriptive links are part of the site styling and should remain so.

## Required practices

- Use semantic HTML before ARIA.
- Keep every interactive element keyboard accessible.
- Maintain visible focus indicators.
- Never rely on color alone to convey meaning.
- Provide text alternatives for images, icons, and maps.
- Keep link text specific enough to make sense out of context.
- Preserve accessible names, roles, and states when scripting UI.

## Testing

- Run `npm run test:a11y` on any HTML, CSS, or JavaScript change.
- Do a keyboard-only pass on `public/index.html` and `public/places-map.html`.
- Check zoom, contrast, and focus behavior on mobile widths.
- Re-run tests after changing templates, data that affects rendering, or navigation.

## Definition of Done

- No Critical or Serious accessibility issues are introduced.
- Any Moderate issue is documented and explicitly approved.
- The page still reads sensibly with CSS off and with a screen reader.

## Open items

- Review future map or calendar changes for text alternatives and fallback content.
- Keep GitHub issue templates aligned with the same accessibility expectations.