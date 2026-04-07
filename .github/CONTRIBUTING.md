# Contributing

Thank you for your interest in PBIX Documenter. Contributions are welcome.

## Getting started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Install [Ollama](https://ollama.com) and pull the default model if you want to test LLM explanations:
   ```bash
   ollama pull gemma3:1b
   ```
4. Run the app:
   ```bash
   streamlit run src/app.py
   ```

## Workflow

- Open an issue before starting significant work so we can discuss the approach.
- Create a branch from `main` with a descriptive name: `feature/snowflake-yaml-export`, `fix/pdf-table-overflow`.
- Keep pull requests focused on a single concern.
- Update docstrings and the relevant ADR if your change affects an architectural decision.

## Code style

- Python 3.12+, type annotations on all public functions.
- Follow the existing pattern: callbacks for UI feedback, Markdown as the generation output format.
- No new dependencies without a clear justification.

## What to work on

See the open issues for current priorities. The roadmap in `README.md` describes planned features including Snowflake Semantic View / Cortex Analyst YAML export.
