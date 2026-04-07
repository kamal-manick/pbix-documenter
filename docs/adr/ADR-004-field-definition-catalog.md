# ADR-004: External Field Definition Catalog for Schema Enrichment

## Status: Accepted

## Context

The schema extraction from a PBIX file yields column names and data types, but no business-friendly descriptions. In an enterprise context, these descriptions exist in data dictionaries and catalog tools, but are not embedded in the Power BI model itself.

Without enrichment, the Fields table in the documentation has a blank Definition column, which reduces its usefulness for business stakeholders. The goal is to inject definitions from an authoritative external source.

Options considered:
1. Require users to manually add descriptions inside Power BI Desktop (using column/measure descriptions)
2. Embed definitions as a static lookup table inside the application code
3. Load definitions from an external catalog file at generation time

## Decision

Load field definitions from an external catalog file (CSV or Excel) at generation time. The catalog is matched to model fields by column name, with a configurable primary key column and fallback key column (to handle cases where the field name in the model differs from the source system name).

The lookup function is memoized with `functools.lru_cache` to avoid redundant lookups for fields that appear in multiple tables. The entire catalog is loaded once per generation run.

The catalog integration is entirely optional. If no catalog file is present, or if a field has no matching entry, the documentation generates cleanly with an empty Definition column.

See `sample_catalog.csv` for the expected schema.

## Consequences

**Easier:**
- Business definitions can be maintained in a spreadsheet by data stewards, independently of the application.
- The same catalog can be used across multiple PBIX files.
- Memoization makes repeated lookups for the same field name effectively free.
- Graceful degradation means the tool works without a catalog configured.

**Harder:**
- The catalog file must be kept in sync with the evolving data model. Stale definitions are not flagged automatically.
- Column name matching is case-insensitive string equality. Fuzzy matching or synonym mapping is not implemented.
- The catalog path is currently a fixed convention. A future improvement would expose it as a configurable parameter in the UI.
