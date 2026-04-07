# ADR-002: Local LLM Inference via Ollama

## Status: Accepted

## Context

DAX and Power Query (M) expressions are technical code that most stakeholders cannot read. Generating plain-English explanations of these expressions would significantly improve the usefulness of the documentation for business audiences.

Options considered:
1. Cloud LLM API (OpenAI, Anthropic, Azure OpenAI)
2. Local inference via Ollama
3. No LLM -- static documentation only

The tool is an internal self-serve application. Report files may contain sensitive business logic. Users expect the tool to work without external dependencies.

## Decision

Use Ollama with a lightweight local model (gemma3:1b) for all LLM inference. LLM explanations are an opt-in feature toggled by a checkbox in the UI. The system degrades gracefully to static documentation when the option is disabled or Ollama is unavailable.

Temperature is set to 0 for deterministic, reproducible output. The system prompt instructs the model to produce single-line, documentation-ready prose with no formatting or preamble.

## Consequences

**Easier:**
- No API keys, no cloud costs, no rate limits.
- Report data never leaves the local machine -- no data governance concerns.
- Works fully offline.
- Reproducible output (temperature=0) means re-running documentation on the same file produces the same explanations.

**Harder:**
- Ollama must be installed and running on the host machine. This is a setup dependency that cloud APIs do not require.
- Inference speed is limited by local hardware. On CPU-only machines, generating explanations for a large model can be slow.
- Model quality is lower than frontier cloud models. Complex DAX patterns may produce vague or incomplete explanations.
- The model name (gemma3:1b) is currently hardcoded. Swapping to a different local model requires a code change.
