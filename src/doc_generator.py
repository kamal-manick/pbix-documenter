"""
doc_generator.py -- Core documentation generation engine.

Responsibilities:
  - Parse a .pbix file using pbixray to extract all semantic model components.
  - Optionally enrich schema fields with business definitions from an
    external catalog file (see FieldDefinitionCatalog).
  - Optionally generate plain-English explanations for DAX and M code
    using a locally hosted LLM via Ollama.
  - Produce a single canonical Markdown string representing the full model.

Design notes:
  - All UI feedback (progress, streaming, labels) is handled via callbacks
    injected at construction time. The generator has no direct dependency
    on Streamlit and can be used headlessly by passing no-op callbacks.
  - The total number of components (DAX columns + DAX measures + M queries)
    is counted before generation begins, providing an honest progress denominator.
  - The LLM runs at temperature=0 for deterministic, reproducible output.
  - Smart quotes introduced by the LLM are normalised to ASCII equivalents
    before being written into the Markdown document.
"""

import os
import re
from functools import lru_cache
from typing import Callable, Generator

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pbixray import PBIXRay


# ---------------------------------------------------------------------------
# Field definition catalog
# ---------------------------------------------------------------------------

class FieldDefinitionCatalog:
    """
    Loads business field definitions from an external catalog file and
    exposes a cached lookup function keyed on field name.

    The catalog is expected to be a CSV or Excel file with at least:
      - A primary key column matching Power BI column names in the model.
      - One or more definition columns containing human-readable descriptions.

    An optional fallback key column handles cases where the field name in
    the model differs from the name used in the source system.

    Example catalog schema (see sample_catalog.csv):
      pbi_column_name, source_column_name, business_definition,
      technical_definition, tooltip_definition

    Usage:
        catalog = FieldDefinitionCatalog(
            catalog_path="sample_catalog.csv",
            primary_key_column="pbi_column_name",
            fallback_key_column="source_column_name",
            definition_columns=["business_definition", "technical_definition"],
        )
        lookup = catalog.load()
        definition = lookup("Revenue")
    """

    def __init__(
        self,
        catalog_path: str,
        primary_key_column: str,
        fallback_key_column: str,
        definition_columns: list[str],
    ) -> None:
        self.catalog_path = catalog_path
        self.primary_key_column = primary_key_column
        self.fallback_key_column = fallback_key_column
        self.definition_columns = definition_columns

    def load(self) -> Callable[[str], str]:
        """
        Read the catalog file and return a memoized lookup function.

        Returns a function: lookup(field_name: str) -> str
          - Searches the primary key column first, then the fallback column.
          - Returns the first non-empty, non-'not applicable' value from the
            definition columns, or an empty string if no match is found.
        """
        if self.catalog_path.endswith(".xlsx") or self.catalog_path.endswith(".xls"):
            catalog = pd.read_excel(self.catalog_path)
        else:
            catalog = pd.read_csv(self.catalog_path)

        def _normalize_whitespace(text: str) -> str:
            return re.sub(r"\s+", " ", str(text)).strip()

        @lru_cache(maxsize=None)
        def lookup(field_name: str) -> str:
            row = catalog[
                catalog[self.primary_key_column].str.lower() == field_name.lower()
            ]
            if row.empty and self.fallback_key_column:
                row = catalog[
                    catalog[self.fallback_key_column].str.lower() == field_name.lower()
                ]
            if row.empty:
                return ""
            for col in self.definition_columns:
                val = row.iloc[0][col]
                if pd.notna(val) and str(val).strip().lower() not in ("not applicable", ""):
                    return _normalize_whitespace(val)
            return ""

        return lookup


# ---------------------------------------------------------------------------
# Document generator
# ---------------------------------------------------------------------------

class PBIDocumentGenerator:
    """
    Generates a canonical Markdown document from a Power BI .pbix file.

    Extracts all semantic model components via pbixray:
      - M Parameters
      - For each table: M Query, Relationships, Schema fields,
        Calculated Columns, DAX Measures

    Optionally enriches the output with:
      - Field definitions from a FieldDefinitionCatalog
      - Plain-English LLM explanations for each DAX/M expression (via Ollama)

    All UI feedback is handled through callbacks to keep the generator
    decoupled from the Streamlit framework.
    """

    #: Name of the local Ollama model used for code explanations.
    #: Any model available in your Ollama installation can be substituted here.
    LLM_MODEL = "gemma3:1b"

    def __init__(
        self,
        pbix_path: str,
        enable_explanation: bool = True,
        catalog_path: str | None = "sample_catalog.csv",
        catalog_primary_key: str = "pbi_column_name",
        catalog_fallback_key: str = "source_column_name",
        catalog_definition_columns: list[str] | None = None,
        scratch_callback: Callable[[str], None] | None = None,
        clear_scratch_callback: Callable[[], None] | None = None,
        progress_callback: Callable[[float], None] | None = None,
        stream_callback: Callable[[Generator], None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        pbix_path:
            Absolute path to the .pbix file on disk.
        enable_explanation:
            When True, calls Ollama to generate plain-English explanations
            for each DAX expression and Power Query (M) script.
        catalog_path:
            Path to the field definition catalog file (CSV or Excel).
            Set to None to skip catalog enrichment entirely.
        catalog_primary_key:
            Column in the catalog to match against Power BI column names.
        catalog_fallback_key:
            Secondary column to try if the primary key yields no match
            (e.g. the source system column name).
        catalog_definition_columns:
            Ordered list of catalog columns to search for a definition.
            The first non-empty value found is used.
        scratch_callback:
            Called with a label string as each component begins processing.
            Useful for showing the current item in the UI.
        clear_scratch_callback:
            Called after each component is processed to clear the label.
        progress_callback:
            Called with a float in [0.0, 1.0] after each component is processed.
        stream_callback:
            Called with a token generator for LLM output. Should consume the
            generator and display tokens in real time (e.g. st.write_stream).
        """
        self.pbix_path = pbix_path
        self.model_name = os.path.splitext(os.path.basename(pbix_path))[0]
        self.enable_explanation = enable_explanation
        self.catalog_path = catalog_path
        self.catalog_primary_key = catalog_primary_key
        self.catalog_fallback_key = catalog_fallback_key
        self.catalog_definition_columns = catalog_definition_columns or [
            "business_definition", "technical_definition", "tooltip_definition"
        ]

        # Default callbacks are no-ops so the generator works headlessly
        self.scratch = scratch_callback or (lambda x: None)
        self.clear_scratch = clear_scratch_callback or (lambda: None)
        self.update_progress = progress_callback or (lambda x: None)
        self.write_stream = stream_callback or (lambda gen: list(gen))

        self.llm = ChatOllama(model=self.LLM_MODEL, temperature=0)
        self.model = PBIXRay(pbix_path)

        self.total_items: int = 1
        self.current_count: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_components(self) -> None:
        """
        Count total DAX columns + DAX measures + Power Query steps upfront.
        This gives an accurate denominator for progress reporting.
        """
        dax_columns = len(self.model.dax_columns) if not self.model.dax_columns.empty else 0
        dax_measures = len(self.model.dax_measures) if not self.model.dax_measures.empty else 0
        power_query = len(self.model.power_query) if not self.model.power_query.empty else 0
        self.total_items = max(dax_columns + dax_measures + power_query, 1)
        self.current_count = 0

    @staticmethod
    def _normalize_quotes(text: str) -> str:
        """
        Replace Unicode smart quotes with their ASCII equivalents.

        LLMs commonly produce typographic quotes in their output. Leaving
        these in the Markdown document can break code block rendering and
        cause encoding issues in downstream format conversions.
        """
        replacements = {
            "\u2018": "'", "\u2019": "'",   # left/right single quotation marks
            "\u201C": '"', "\u201D": '"',   # left/right double quotation marks
            "\u2032": "'", "\u2033": '"',   # prime / double prime
        }
        for fancy, plain in replacements.items():
            text = text.replace(fancy, plain)
        return text

    def _explain(self, code: str, label: str) -> str:
        """
        Generate a plain-English explanation for a DAX or M expression.

        Streams LLM output token-by-token via stream_callback, allowing
        the UI to display partial results in real time. Returns the full
        explanation string with smart quotes normalised.

        Returns an empty string if code is blank or explanations are disabled.
        """
        if not code or not str(code).strip():
            self.current_count += 1
            self.update_progress(self.current_count / self.total_items)
            return ""

        if not self.enable_explanation:
            self.clear_scratch()
            self.current_count += 1
            return ""

        self.scratch(f"Adding explanation for {label}")

        messages = [
            SystemMessage(
                content=(
                    "You are a data analytics assistant. Your task is to explain DAX or M code "
                    "in plain English, summarising its purpose clearly and concisely. "
                    "Avoid any introductions or conclusions -- your response should be ready to "
                    "paste into product documentation. "
                    "Do not expand abbreviations or include any formatting. "
                    "Do not repeat the DAX or respond in multiple lines. "
                    "Avoid line breaks in your reply."
                )
            ),
            HumanMessage(content=f"Explain this DAX or M code:\n\n{code}"),
        ]

        full_response: list[str] = []

        def stream_gen() -> Generator:
            for chunk in self.llm.stream(messages):
                text = chunk.content
                full_response.append(self._normalize_quotes(text))
                yield text

        self.write_stream(stream_gen())
        self.clear_scratch()
        self.current_count += 1
        self.update_progress(self.current_count / self.total_items)
        return "".join(full_response).strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """
        Extract the full semantic model from the PBIX file and produce
        a canonical Markdown document.

        Returns the complete Markdown string. This string is the single
        source of truth used by MarkdownExporter for all format conversions.
        """
        self._count_components()

        # Load field definitions -- skip enrichment if no catalog file exists
        get_definition: Callable[[str], str]
        if self.catalog_path and os.path.exists(self.catalog_path):
            catalog = FieldDefinitionCatalog(
                catalog_path=self.catalog_path,
                primary_key_column=self.catalog_primary_key,
                fallback_key_column=self.catalog_fallback_key,
                definition_columns=self.catalog_definition_columns,
            )
            get_definition = catalog.load()
        else:
            get_definition = lambda field_name: ""  # noqa: E731

        # Precompute definitions for all schema rows upfront to avoid
        # repeated catalog lookups during the table iteration loop
        full_schema = self.model.schema.copy()
        full_schema["Definition"] = full_schema["ColumnName"].apply(get_definition)
        full_schema.fillna("", inplace=True)

        lines: list[str] = [
            f"# {self.model_name} - Model Documentation",
            f"**File**: `{os.path.basename(self.pbix_path)}`",
            f"**Size**: `{self.model.size / (1024 * 1024):.2f} MB`",
            "",
        ]

        # M Parameters (query parameters defined at model level)
        if not self.model.m_parameters.empty:
            lines.append("## M Parameters")
            for _, r in self.model.m_parameters.iterrows():
                lines.append(f"**{r['ParameterName']}**")
                lines.append(f"`{r['Expression']}`")
                lines.append("")

        if self.enable_explanation:
            self.update_progress(self.current_count / self.total_items)

        # Iterate over each table in the model
        for table in self.model.tables:
            lines.append(f"## Table: {table}")

            # M Query (Power Query transformation for this table)
            if not self.model.power_query.empty:
                pq = self.model.power_query[self.model.power_query["TableName"] == table]
                for _, r in pq.iterrows():
                    expr = str(r.get("Expression", "")).strip()
                    if expr:
                        lines.append("#### M Query")
                        lines.append("```m")
                        lines.append(expr)
                        lines.append("```")
                        lines.append(self._explain(expr, f"M Query for {table}"))

            # Relationships involving this table
            if not self.model.relationships.empty:
                rels = self.model.relationships
                table_rels = rels[
                    (rels["FromTableName"] == table) | (rels["ToTableName"] == table)
                ]
                if not table_rels.empty:
                    lines += [
                        "",
                        "#### Relationships",
                        "",
                        "| Relationship | Cardinality | Cross Filter Direction | Is Active | Referential Integrity |",
                        "|---|---|---|---|---|",
                    ]
                    for _, r in table_rels.iterrows():
                        rel = (
                            f"`{r['FromTableName']}.[{r['FromColumnName']}]"
                            f" -> {r['ToTableName']}.[{r['ToColumnName']}]`"
                        )
                        lines.append(
                            f"| {rel} | {r['Cardinality']} | {r['CrossFilteringBehavior']} "
                            f"| {'Yes' if r['IsActive'] else 'No'} "
                            f"| {'Yes' if r['RelyOnReferentialIntegrity'] else 'No'} |"
                        )
                    lines.append("")

            # Schema fields (with enriched definitions)
            schema = full_schema[full_schema["TableName"] == table]
            if not schema.empty:
                lines += [
                    "",
                    "#### Fields",
                    "",
                    "| Name | Type | Definition |",
                    "|---|---|---|",
                ]
                for _, r in schema.iterrows():
                    lines.append(f"| {r['ColumnName']} | {r['PandasDataType']} | {r['Definition']} |")

            # Calculated columns (DAX expressions stored in the model)
            if not self.model.dax_columns.empty:
                dax_cols = self.model.dax_columns[self.model.dax_columns["TableName"] == table]
                if not dax_cols.empty:
                    lines.append("#### Calculated Columns")
                for _, r in dax_cols.iterrows():
                    expr = str(r.get("Expression", "")).strip()
                    if expr:
                        lines.append(f"**{r['ColumnName']}**")
                        lines.append("```dax")
                        lines.append(expr)
                        lines.append("```")
                        lines.append(self._explain(expr, f"column {r['ColumnName']}"))
                        lines.append("")

            # DAX Measures
            if not self.model.dax_measures.empty:
                measures = self.model.dax_measures[self.model.dax_measures["TableName"] == table]
                if not measures.empty:
                    lines.append("#### DAX Measures")
                for _, r in measures.iterrows():
                    expr = str(r.get("Expression", "")).strip()
                    if expr:
                        lines.append(f"**{r['Name']}**")
                        lines.append("```dax")
                        lines.append(expr)
                        lines.append("```")
                        if r.get("Description"):
                            lines.append(f"Description: {r['Description']}")
                        lines.append(self._explain(expr, f"measure {r['Name']}"))
                        lines.append("")

            lines.append("")

        if self.enable_explanation:
            self.update_progress(1.0)

        return "\n".join(lines)
