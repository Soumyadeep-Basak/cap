# Root causes

- Structured SQL rows were deliberately serialized as pretty-printed JSON in `rag_workflow.py`; the UI displays the API's `answer` string directly, so it showed that JSON verbatim.
- The classifier relied on a model response for every question. This left obvious numbered-invoice summaries vulnerable to inconsistent routing even though the intended behavior is SQL.
- The RAG generation prompt did not instruct the model to translate internal field paths or present source metadata as readable citations.
- `rag_workflow.py` defined `finalize_unstructured_node` twice. The later definition overwrote the earlier RAG Triad acceptance check, allowing any non-empty answer to be marked completed regardless of its score.

The fixes keep both execution branches and the Agent API contract intact. SQL facts are rendered as readable Markdown while retaining returned keys, values, nested collections, and explicit nulls. Numbered-invoice audit questions route to SQL unless they request document reasoning. RAG answer instructions now preserve facts while clarifying paths and citations, and the generation cache version changes so old answers do not bypass the updated prompt. The evaluation-aware finalizer is restored as the function used by the graph.

# Modified files

## `agent/src/invoice_auditor/workflows/rag_workflow.py`

- **Purpose:** Classifies queries and runs either the SQL path or the retrieval, generation, and evaluation path.
- **Changes made:** Added deterministic routing for numbered-invoice audit questions; replaced JSON serialization with recursive Markdown formatting for SQL rows; removed the later duplicate finalizer that overrode the evaluation-aware implementation.
- **Reason:** Addresses inconsistent routing, unreadable SQL output, and the RAG acceptance check bypass.
- **Impact:** Invoice audit queries use SQL; structured answers retain their data in readable form; RAG answers are completed only when evaluation passes.
- **Verification:** Python compilation and focused checks for nested formatting, nulls, routing, and acceptance behavior passed. Full API/database/Bedrock/Qdrant integration was not run.

## `agent/src/invoice_auditor/agents/rag_agents/generation_agent.py`

- **Purpose:** Generates grounded answers and caches them by question and context.
- **Changes made:** Bumped the generation cache-key version.
- **Reason:** Prevents cached pre-prompt-change answers from bypassing the updated readability and citation instructions.
- **Impact:** Only RAG cache identity changes; retrieval, generation sequence, and evaluation are unchanged.
- **Verification:** Python compilation passed. Live cache/model behavior was not exercised.

## `config/rag_prompts.yaml`

- **Purpose:** Stores query classification, SQL, RAG generation, and reflection prompt instructions.
- **Changes made:** Expanded RAG generation instructions for human-readable technical field paths, preservation of relevant facts, and readable citations retaining source type and invoice ID.
- **Reason:** Existing instructions did not address technical paths or raw source-marker syntax.
- **Impact:** Improves RAG answer readability while retaining evidence traceability and grounding requirements.
- **Verification:** Prompt text checks passed. YAML parsing could not be run because PyYAML is not installed in the local Python environment; model output was not exercised.

## `list.md`

- **Purpose:** Documents the root causes, changes, impact, and verification for this task.
- **Changes made:** Added this change and verification record.
- **Reason:** Required deliverable.
- **Impact:** Documentation only.
- **Verification:** Reviewed against the final modified-file list and checks performed.

# Verification summary

- `python -m compileall -q agent/src/invoice_auditor` — passed.
- Focused source-level checks — passed for nested SQL formatting, null retention, invoice query routing, RAG evidence routing, and evaluation-aware finalization.
- `git diff --check` — passed; Git emitted only line-ending normalization notices.
- YAML parsing and full service integration — not run; PyYAML and running database/model/vector-store services were unavailable/not exercised.
