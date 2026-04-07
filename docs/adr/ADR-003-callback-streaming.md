# ADR-003: Callback-Driven Progress and Streaming

## Status: Accepted

## Context

Documentation generation is a long-running operation, especially when LLM explanations are enabled. A model with 50 DAX measures may take 2-5 minutes to fully document. Without feedback, users have no way to know whether the application is working or hung.

Two sub-problems to solve:
1. Progress tracking: show how far through the model the generator has reached.
2. LLM streaming: show LLM output as it is generated, token by token, rather than waiting for the full response.

Streamlit's execution model re-runs the entire script on each interaction, which constrains how UI updates can be triggered from within a long-running function.

## Decision

The generator accepts four callback functions at construction time:

- `progress_callback(value: float)` -- called after each component is processed, with a value between 0.0 and 1.0
- `scratch_callback(text: str)` -- called with the name of the component currently being processed
- `clear_scratch_callback()` -- called to clear the current item label after processing
- `stream_callback(generator)` -- called with a token generator; the UI consumes it via `st.write_stream()`

The generator has no direct dependency on Streamlit. It calls callbacks without knowing what they do. In the UI, these callbacks are closures over Streamlit container objects. In a headless or CLI context, they can be replaced with no-ops or print functions.

Component count is computed upfront (before generation begins) so the progress denominator is known and the progress bar moves at an honest rate.

## Consequences

**Easier:**
- The generator is fully decoupled from the UI framework. It can be used in a CLI, a test, or a different frontend without modification.
- Real-time feedback makes slow operations feel responsive.
- Token streaming of LLM output gives users visibility into what the model is generating before the full response is complete.
- Progress is honest -- derived from the actual number of components, not a fake timer.

**Harder:**
- The constructor signature has four callback parameters, which is verbose. A callback config object would be cleaner but adds indirection.
- Callers must wire up callbacks explicitly. Forgetting to pass a callback results in silent no-ops, which can make debugging harder.
