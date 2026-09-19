# dollar_watch V3.4.2 — PDF parser runtime hardening

- Suppresses recoverable `pypdf._reader` warning chatter such as `Ignoring wrong pointing object ...` while parsing official NY Fed FX-quarterly PDFs.
- Uses `PdfReader(..., strict=False)` explicitly so malformed/stale cross-reference pointers are repaired when possible.
- Validates the `%PDF-` file signature before invoking pypdf, preventing HTTP-200 HTML/CDN error pages from being misparsed as PDFs.
- Treats a PDF that produces no extractable text as a real extraction failure and sends it through the existing validated-cache/Data Health fallback path.
- Restores the prior pypdf logger level immediately after each extraction; suppression is local, not global.
- App version becomes 3.4.2. Data/schema version remains 3.4.1 because no persisted payload shape or scoring taxonomy changed.
