# Agent Logic and Learning Guide

This guide describes the implemented workflow. Start with `backend/agent/state.py`,
then read `backend/agent/graph.py`, and finally inspect the API and React client.

## State: what persists and what resets

`messages` uses LangGraph's `add_messages` reducer. New messages are merged by ID;
`RemoveMessage` removes older messages only after successful summarization.
`conversation_summary` and the document ID persist in SQLite for each thread.

`begin` resets evidence, drafts, review feedback, revision count and final result
for every new turn. Old references must never become evidence for a new answer.
The request's question also remains separate from its resolved follow-up question.
Pydantic validates model outputs; TypedDict documents graph state but does not
perform runtime validation.

## Routing

1. `begin`: restore checkpointed conversation and reset turn-local values.
2. If conversation character count reaches the configured threshold and enough
   complete recent turns can be retained, run `summarize_memory`.
3. `planner`: choose `qa`, `document_summary`, or `clarify`. Resolve pronouns from
   conversation context without treating previous answers as verified facts.
4. Clarifications go directly to `finalize`. Other requests go to `collect`.
5. QA retrieves text blocks by English terms and Chinese bigram overlap, including
   neighboring blocks when the budget permits. Short documents use all blocks.
6. Document summary uses all blocks, maps bounded batches to partial summaries,
   then combines them. The application refuses documents exceeding the configured
   full-summary character limit instead of silently summarizing a subset.
7. `review`: validate citation IDs and primary citation, then ask a reviewer model
   whether the answer's factual claims, conditions and amounts match cited text.
8. A failed answer gets one `revise` attempt and a second review. A second failure
   returns an unverified response with no source highlights.
9. `finalize`: assemble source coordinates and add the final AI message to memory.

The workflow diagram is in the README. `docs/workflow.mmd` is generated from the
compiled graph, so it can be compared with the actual node topology.

## Two different summarizers

**Document Summary Agent** is user-facing. It processes the selected PDF and
returns key points with original block IDs. Batched summaries remain intermediate
material; the final reviewer checks the original cited blocks.

**Conversation Summarizer** reduces older chat history. It preserves user statements,
open questions, uncertainties and source references. Recent turns stay intact.
If summarization fails, the original messages remain. Its summary is context for
interpreting questions, never a substitute for PDF evidence.

The trigger uses a conservative character budget, not an exact tokenizer. Adjust
it alongside document and response budgets for the model you use.

## Evidence and highlighting

The SHA-256 of the uploaded PDF is its document ID. Two files with the same name
and different contents therefore have different caches and conversation scopes.
Text block IDs are deterministic within an extraction, for example `p2-b3`.
Each block contains its page, original text and normalized rectangle.

The model selects IDs. The server supplies original text and coordinates. React
renders rectangles over the PDF and scrolls to the primary citation. Clicking a
source button selects another citation. This marks whole source blocks rather
than promising exact sentence-level highlighting.

PDF layout extraction can still merge table cells or read columns imperfectly.
Coordinate highlighting fixes text-match ambiguity; it does not correct extraction.

## Memory lifecycle

The backend opens one async SQLite checkpointer during FastAPI lifespan and uses
it when compiling the graph. API requests include a UUID `thread_id` and a
`document_id`. The browser keeps the thread ID in localStorage per document and
restores recent messages after reload. Creating a new chat creates a new UUID.

The backend rejects document changes within a populated thread and overlapping
requests to that thread in the same process. Run one Uvicorn worker for this local
prototype. Before multi-user deployment, add authentication, ownership checks,
a shared concurrency mechanism and a production database.

Memory is persistent conversation memory, not cross-chat user-profile memory.
Older checkpoints remain in SQLite even after messages are removed from the latest
state; summarization is not data erasure. File retention and deletion controls are
future work.

## Progress events

Nodes send curated `status` events through `get_stream_writer()`. The API forwards
only custom status events and the verified final result over SSE. It does not expose
raw graph state, intermediate drafts, provider errors or private model reasoning.

The frontend uses POST + fetch streaming, parses fragmented UTF-8/SSE frames and
shows progress during processing. Completed answers retain an expandable execution
record during the current browser session. Reload restores conversation text, the
latest citations and summary presence; old progress records are not persisted.

`/api/chat` executes the same graph without streaming for scripts and tests.

## How to extend this yourself

- Add a node: define its state inputs, its partial update and its outgoing route.
- Add a model result: create a Pydantic schema, then call `llm.structured`.
- Improve retrieval: replace `retrieve` while preserving EvidenceBlock IDs and geometry.
- Add long-term preferences: use a separate user-scoped store after adding authentication.
- Add a tool: keep its results as untrusted evidence; validate before final delivery.

## Verification

Run backend tests from `backend`:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Run frontend checks from `frontend`:

```bash
npm run lint
npm run build
npm test
```

Tests use a deterministic fake model and real PDF extraction, LangGraph and SQLite.
They do not measure Gemini/Gemma factual accuracy. For a live acceptance check,
upload a text PDF, ask a question, follow up with a pronoun, request a summary,
click sources, reload, restart the backend, and then start a new chat.

## External references

- [LangGraph memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
