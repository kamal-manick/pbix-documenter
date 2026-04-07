"""
doc_exporter.py -- Multi-format export for PBIX Documenter.

MarkdownExporter takes the canonical Markdown string produced by
PBIDocumentGenerator and converts it to one of four output formats:
  - Markdown (.md)   -- the canonical source, downloaded as-is
  - HTML (.html)     -- styled HTML with print-friendly CSS
  - Word (.doc)      -- HTML content served with application/msword MIME type
  - PDF              -- browser print window opened via JavaScript

All downloads are handled client-side via JavaScript injection into the
Streamlit component iframe. No files are written to the server filesystem.

Design note on Word export:
  The .doc format here is HTML with an application/msword MIME type. This
  opens correctly in Microsoft Word but does not use the native .docx format.
  For richer Word formatting, python-docx could replace this implementation
  at the cost of significant additional complexity.

Design note on PDF export:
  PDF generation relies on the browser's built-in print-to-PDF capability.
  Layout and pagination depend on the user's browser and print settings.
  This was an intentional trade-off: it avoids a heavyweight server-side PDF
  library (e.g. WeasyPrint, wkhtmltopdf) and requires zero additional dependencies.
"""

import base64
import re

import markdown2
import streamlit as st


class MarkdownExporter:
    """
    Converts a Markdown string to multiple output formats and triggers
    a browser-side download for each.

    Attributes
    ----------
    data:
        The canonical Markdown document string from PBIDocumentGenerator.
    output_path:
        Directory path for any temporary files (currently unused by the
        client-side export approach, retained for future extension).
    model_name:
        Used as the base filename for downloaded files.
    """

    _CSS = """<style>
    @media print { section.stSidebar { display: none !important; } }
    body {
        font-family: 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
        line-height: 1.6;
        margin: 2em;
        color: #333;
        background: #fff;
    }
    h1, h2, h3, h4 { margin-top: 1.5em; margin-bottom: 0.5em; font-weight: 600; }
    p { margin: 1em 0; display: flex; }
    ul, ol { margin: 1em 0 1em 2em; }
    pre, code {
        font-family: 'Courier New', Courier, monospace;
        background: #f6f8fa;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
    }
    code {
        padding: 0.2em 0.4em;
        font-size: 90%;
        display: inline-block;
        white-space: pre-wrap;
        word-break: break-word;
        margin: 0 10px;
    }
    pre { padding: 1em; overflow-x: auto; }
    table {
        max-width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
        table-layout: fixed;
    }
    th, td {
        border: 1px solid #dfe2e5;
        padding: 0.6em;
        text-align: left;
        vertical-align: top;
        word-wrap: break-word;
    }
    th { background-color: #f6f8fa; font-weight: bold; }
    blockquote {
        margin: 1em 0;
        padding: 0.5em 1em;
        color: #555;
        border-left: 5px solid #dfe2e5;
        background-color: #f9f9f9;
    }
    a { color: #0366d6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    </style>"""

    def __init__(
        self,
        data: str | None = None,
        output_path: str = "temp",
        model_name: str = "PBI Model",
    ) -> None:
        self.data = data
        self.output_path = output_path
        self.model_name = model_name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _markdown_to_html(self, mdata: str) -> str:
        """
        Convert Markdown to a complete, styled HTML document.

        Handles two edge cases:
        1. Language-tagged code fences (```dax, ```m) are stripped to plain
           fences since markdown2 does not recognise these language identifiers.
        2. Underscores in non-code segments are escaped to prevent markdown2
           from interpreting them as emphasis markers in column names and
           DAX identifiers.
        """

        def _escape_underscores(text: str) -> str:
            return text.replace("_", r"\_")

        # Normalise language-tagged fences
        mdata = mdata.replace("```dax", "```").replace("```m", "```")

        # Split on fenced code blocks, escaping underscores only outside them
        segments = re.split(r"(```.*?```)", mdata, flags=re.DOTALL)
        processed: list[str] = []
        for segment in segments:
            if segment.startswith("```"):
                processed.append(segment)
            else:
                # Further split on inline code spans
                sub_segments = re.split(r"(`.*?`)", segment, flags=re.DOTALL)
                processed.append(
                    "".join(
                        s if s.startswith("`") else _escape_underscores(s)
                        for s in sub_segments
                    )
                )

        html = f"<html>{self._CSS}<body>"
        html += markdown2.markdown("".join(processed), extras=["tables"])
        html += "</body></html>"
        # Remove newline after opening <code> tags (markdown2 artefact)
        html = re.sub(r"<code>\n", "<code>", html)
        return html

    def _browser_download(self, content: str, filename: str, mime: str) -> None:
        """
        Trigger a client-side file download via JavaScript.

        Encodes content as Base64, injects a script that creates a Blob URL,
        attaches it to a temporary anchor element, and clicks it programmatically.
        No file is written to the server.
        """
        b64 = base64.b64encode(content.encode()).decode()
        js = f"""
        <script>
        window.addEventListener("DOMContentLoaded", () => {{
            const blob = new Blob([atob("{b64}")], {{ type: "{mime}" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "{filename}";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }});
        </script>
        """
        st.components.v1.html(js, height=100)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, type: str = "Markdown") -> None:
        """
        Convert the canonical Markdown and trigger a browser download.

        Parameters
        ----------
        type:
            One of "Markdown", "HTML", "Word", "PDF".
        """
        base_name = f"{self.model_name} - Model Documentation"

        if type == "Markdown":
            self._browser_download(self.data, f"{base_name}.md", "text/markdown")

        elif type == "HTML":
            html = self._markdown_to_html(self.data)
            self._browser_download(html, f"{base_name}.html", "text/html")

        elif type == "Word":
            # HTML content served with Word MIME type -- opens in Word
            # but does not produce native .docx formatting.
            html = self._markdown_to_html(self.data)
            self._browser_download(html, f"{base_name}.doc", "application/msword")

        elif type == "PDF":
            # Open a print window containing the rendered HTML and call
            # window.print(). The browser handles pagination and PDF export.
            html_content = self._markdown_to_html(self.data)
            pdf_helper = st.empty()
            pdf_js = f"""
            <div id="printArea">{html_content}</div>
            <script>
            function printPDF() {{
                var w = window.open('', '', 'height=800,width=1000');
                w.document.write('<html><head><title>{base_name}</title></head><body>');
                w.document.write(document.getElementById('printArea').innerHTML);
                w.document.write('</body></html>');
                w.document.close();
                w.focus();
                w.print();
            }}
            window.addEventListener("DOMContentLoaded", () => {{ printPDF(); }});
            </script>
            """
            with pdf_helper:
                st.components.v1.html(pdf_js, height=0)
