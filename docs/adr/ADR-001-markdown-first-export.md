# ADR-001: Markdown as Universal Intermediate Format

## Status: Accepted

## Context

The tool needed to produce documentation in multiple output formats: Word and PDF were hard requirements from stakeholders who distribute reports via email and SharePoint. HTML was a natural addition for web rendering. Markdown was needed for version control and diff workflows.

The naive approach is to build a dedicated generation path per format -- write directly to `.docx`, render directly to HTML, etc. This means any change to the content structure (adding a section, changing a table layout) must be replicated across all format writers.

## Decision

Generate one canonical Markdown string as the single source of truth. All export formats are derived from this string by pure transformation functions in `MarkdownExporter`. The generator has no awareness of the final output format.

## Consequences

**Easier:**
- Adding a new export format requires writing one converter, with no changes to the generation pipeline.
- Content changes (new sections, restructured output) are made in one place.
- The Markdown output is useful on its own -- renderable in GitHub, VS Code, and documentation platforms.
- Unit testing the generator output is straightforward: assert against a Markdown string.

**Harder:**
- Format-specific layout control is limited. Rich Word formatting (styles, headers, footers, tracked changes) is not achievable through HTML-MIME conversion.
- PDF output relies on browser print, which means layout depends on the user's browser and print settings.
- Tables with very long content can overflow in some renderers -- CSS workarounds are needed.
