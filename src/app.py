"""
app.py -- Streamlit entry point for PBIX Documenter.

Implements a three-step sidebar workflow:
  1. Upload  -- accept a .pbix file
  2. Generate -- run PBIDocumentGenerator with optional LLM explanations
  3. Export  -- download the documentation in the chosen format

Session state is used to persist the generated document and exporter
across Streamlit reruns. State is reset automatically when the uploaded
file changes, ensuring stale documentation is never shown.
"""

import os
import shutil
import streamlit as st
from doc_generator import PBIDocumentGenerator
from doc_exporter import MarkdownExporter

st.set_page_config(
    page_title="PBIX Documenter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide sidebar border and allow code blocks to wrap
st.markdown(
    """
    <style>
        .st-emotion-cache-1h9usn1 { margin-left:-15px !important; border-style: none !important; }
        code { text-wrap-mode: wrap !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Suppress sidebar in print/PDF output
st.html("<style>@media print { section.stSidebar { display: none !important; } }</style>")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
_DEFAULTS: dict = {
    "uploaded_file": None,
    "mdata": None,
    "exporter": None,
    "is_generating": False,
    "generation_complete": False,
    "prev_uploaded_name": None,
}
for key, value in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def _start_generation() -> None:
    st.session_state.is_generating = True


def _reset_generation() -> None:
    st.session_state.is_generating = False


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def main() -> None:
    # UI placeholder containers -- defined at top level so callbacks can
    # reference them via closure.
    status_container = st.empty()
    progress_container = st.empty()
    llm_node_container = st.empty()
    scratch_container = st.empty()
    documentation_container = st.empty()

    # ------------------------------------------------------------------
    # Callback definitions
    # ------------------------------------------------------------------

    def update_progress_bar(value: float) -> None:
        """Update the progress bar and status label (0.0 to 1.0)."""
        clamped = min(value, 1.0)
        progress_bar.progress(clamped)
        status_spinner.update(label=f"Generating document... {int(clamped * 100)}% completed.")

    def update_scratch(text: str) -> None:
        """Display the name of the component currently being processed."""
        llm_node_container.text(text)

    def clear_scratch() -> None:
        """Clear the current component label after processing."""
        scratch_container.empty()
        llm_node_container.empty()

    stream_writer = scratch_container.write_stream

    # ------------------------------------------------------------------
    # Sidebar: Step 1 -- Upload
    # ------------------------------------------------------------------
    with st.sidebar:
        st.title("📊 PBIX Documenter")
        st.caption(
            "Generate documentation for Power BI semantic models. "
            "See the [GitHub repository](https://github.com/kamal-manick/pbix-documenter) for setup instructions."
        )

        st.subheader("1 Upload", divider=True)
        uploaded_file = st.file_uploader("Select your PBIX file", type=["pbix"])

        st.session_state.uploaded_file = uploaded_file if uploaded_file else None

        # Reset all state when the file changes or is removed
        current_filename = uploaded_file.name if uploaded_file else None
        if current_filename != st.session_state.prev_uploaded_name:
            st.session_state.mdata = None
            st.session_state.exporter = None
            st.session_state.generation_complete = False
            st.session_state.is_generating = False
            st.session_state.prev_uploaded_name = current_filename

            # Clear the temp directory to avoid stale PBIX files on disk
            if os.path.exists("temp"):
                shutil.rmtree("temp")

        # ------------------------------------------------------------------
        # Sidebar: Step 2 -- Generate
        # ------------------------------------------------------------------
        if st.session_state.uploaded_file:
            st.subheader("2 Generate", divider=True)
            explain = st.checkbox("Include DAX/M Explanation", value=True)
            st.button("Generate", on_click=_start_generation)

            if st.session_state.is_generating:
                os.makedirs("temp", exist_ok=True)
                documentation_container.empty()

                pbix_path = os.path.join("temp", uploaded_file.name)
                with open(pbix_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Initialise the generator -- raises KeyError if the PBIX
                # has no embedded data model.
                try:
                    docgen = PBIDocumentGenerator(
                        pbix_path=pbix_path,
                        enable_explanation=explain,
                        scratch_callback=update_scratch,
                        clear_scratch_callback=clear_scratch,
                        progress_callback=update_progress_bar,
                        stream_callback=stream_writer,
                    )
                except KeyError as e:
                    if "DataModel" in str(e):
                        st.error(
                            "The uploaded PBIX file does not contain a data model. "
                            "Please upload a file with a valid data model."
                        )
                    else:
                        st.error(f"An unexpected error occurred: {e}")
                    st.stop()
                except Exception as e:
                    st.error(f"Failed to initialise documentation generator: {e}")
                    st.stop()

                with status_container:
                    status_spinner = st.status("Initialising...")
                with progress_container:
                    progress_bar = st.progress(0.0)

                mdata = docgen.generate()
                st.session_state.mdata = mdata
                st.session_state.exporter = MarkdownExporter(
                    mdata, "temp", docgen.model_name
                )

                # Remove the PBIX from disk -- it is no longer needed
                if os.path.exists(pbix_path):
                    os.remove(pbix_path)

                status_container.empty()
                progress_container.empty()
                _reset_generation()
                st.session_state.generation_complete = True

        # ------------------------------------------------------------------
        # Sidebar: Step 3 -- Export
        # ------------------------------------------------------------------
        if st.session_state.generation_complete:
            st.subheader("3 Export", divider=True)
            export_format = st.radio("Output Format:", ["Markdown", "HTML", "Word", "PDF"])
            if st.button("Export") and st.session_state.exporter:
                st.session_state.exporter.export(export_format)

    # ------------------------------------------------------------------
    # Main area: render the generated documentation
    # ------------------------------------------------------------------
    if st.session_state.mdata:
        with documentation_container:
            st.markdown(st.session_state.mdata)


if __name__ == "__main__":
    main()
