# ADR-005: Client-Side File Download via Browser JavaScript

## Status: Accepted

## Context

After documentation is generated, users need to download it in their chosen format. Streamlit provides `st.download_button()` as a native download mechanism, but it requires the file content to be pre-computed and held in memory before the button is rendered -- which conflicts with the on-demand generation flow where the format is chosen after generation completes.

An alternative is to write the exported file to the server filesystem and serve it via a URL. This introduces file lifecycle management: cleanup on session end, collision avoidance between concurrent users, and permission management.

## Decision

Implement export as a client-side operation: encode the document content as Base64, inject a JavaScript snippet via `st.components.v1.html()`, and trigger a programmatic anchor click to initiate the browser download. No file is written to the server.

For PDF, a print window is opened via JavaScript with the rendered HTML content, and `window.print()` is called programmatically. The user's browser handles the print-to-PDF conversion.

## Consequences

**Easier:**
- No server-side file management -- no cleanup, no collision risk, no permission issues.
- Export is instantaneous from the user's perspective (no server round-trip for the download).
- Works correctly in single-user Streamlit deployments without a persistent filesystem.

**Harder:**
- Large documents encoded as Base64 in an inline script tag can hit browser memory limits. For typical PBIX documentation this is not a concern, but very large files could fail silently.
- PDF output quality and layout depend on the user's browser and print driver. There is no server-side control over pagination, margins, or font rendering.
- The JavaScript injection approach is less idiomatic than `st.download_button()` and may be affected by future Streamlit security policy changes around inline scripts.
