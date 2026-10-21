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

# Additional changes in this follow-up

## `agent/src/invoice_auditor/workflows/input_guardrail.py`

- **Purpose:** Checks each incoming question before it reaches the SQL or RAG workflow.
- **Changes made:** Added a dedicated LangGraph input check using `ChatBedrockConverse`; it returns a safety decision from a constrained JSON prompt and fails closed if the check errors or returns invalid data.
- **Reason:** Adds the requested harmful-request and safeguard-bypass check as a separate workflow module.
- **Impact:** Unsafe or uncheckable requests stop before classification, retrieval, or SQL execution; safe requests continue through the existing graph.
- **Verification:** Syntax compilation and mocked safe/unsafe/error parsing checks passed. No live Bedrock call was made.

## `agent/src/invoice_auditor/workflows/rag_workflow.py`

- **Additional changes made:** Calls the guardrail before classification and adds a blocked response path. Replaced the direct boto3 Converse client with `ChatBedrockConverse`.
- **Impact:** Guardrail metadata is returned through the existing API fields; SQL/RAG routing only runs after the guardrail accepts the prompt.
- **Verification:** Syntax compilation passed; mocked guardrail behavior and graph wiring checks passed. Live database/model integration was not run.

## `agent/src/invoice_auditor/workflows/state.py`

- **Purpose:** Defines shared state fields for LangGraph workflows.
- **Changes made:** Added input guardrail state and the `blocked`/`guardrail` metadata values.
- **Reason:** Keeps the workflow state contract typed for the new response path.
- **Impact:** Adds metadata values for blocked inputs; existing SQL/RAG values remain supported.
- **Verification:** Syntax compilation passed.

## `agent/src/invoice_auditor/agents/translation_agent.py`

- **Purpose:** Detects invoice language and translates extracted invoice text.
- **Changes made:** Replaced its direct boto3 Converse call with `ChatBedrockConverse` while retaining the model IDs, region, temperature, token limit, JSON parsing, and translation flow.
- **Reason:** Removes direct boto usage as requested.
- **Impact:** Translation uses the LangChain AWS integration with the same model configuration and output parsing.
- **Verification:** Syntax compilation passed; no live Bedrock call was made.

## `agent/src/invoice_auditor/agents/rag_agents/reflection_agent.py`

- **Purpose:** Evaluates generated RAG answers with the RAG Triad.
- **Changes made:** Replaced its direct boto3 Converse call with `ChatBedrockConverse`, retaining the score parsing and configured threshold.
- **Reason:** Removes direct boto usage without changing the evaluation logic.
- **Impact:** RAG evaluation remains on the existing path and keeps its scoring contract.
- **Verification:** Syntax compilation passed; no live Bedrock call was made.

## `agent/src/invoice_auditor/tools/rag_tools/vector_store.py`

- **Purpose:** Creates embeddings and stores/retrieves invoice chunks in Qdrant.
- **Changes made:** Replaced direct boto3 model invocation and response parsing with `BedrockEmbeddings.embed_query`.
- **Reason:** Removes the remaining direct boto embedding call.
- **Impact:** The Qdrant interface and configured embedding model remain unchanged.
- **Verification:** Syntax compilation passed; live embedding/Qdrant calls were not made.

## `agent/requirements.txt`

- **Purpose:** Declares the agent service's Python dependencies.
- **Changes made:** Added `langchain-aws` and removed the direct `boto3` dependency.
- **Reason:** Declares the integration package used by the migrated call sites; its AWS SDK dependency is transitive.
- **Impact:** Agent installs now include LangChain AWS integrations.
- **Verification:** Dependency installation/resolution was not run in this environment.

## `streamlit-ui/src/invoice_auditor_ui/app.py`

- **Purpose:** Renders the Streamlit auditor dashboard.
- **Changes made:** Added idle and hover background/text colors for the sidebar refresh button.
- **Reason:** Fixes the low-contrast button state reported before interaction.
- **Impact:** Visual-only sidebar styling.
- **Verification:** CSS was reviewed; no live browser visual check was run.

## Result limit guidance (not changed)

- The generated SQL `LIMIT` behavior is instructed in `config/rag_prompts.yaml` under `text_to_sql` (including the example query near the end of that section).
- `agent/src/invoice_auditor/tools/sql_tools.py` defines `MAX_ROW_LIMIT` as a safety fallback only when generated SQL has no `LIMIT`.
- For a meaningful top result/top N, the SQL needs an explicit ordering and `LIMIT N`; changing `MAX_ROW_LIMIT` alone does not sort or limit a query that already has a smaller generated `LIMIT`.

- Follow-up verification: `python -m compileall -q agent/src/invoice_auditor streamlit-ui/src/invoice_auditor_ui` passed; mocked safe/unsafe/invalid guardrail responses passed; source-level graph checks verified the guardrail is first and has accepted/blocked branches; `rg` found no direct boto3 imports or calls in agent Python files; `git diff --check` passed.
- Runtime limitation: dependency installation and real AWS/DB/Qdrant integration were not run, so LangChain AWS model and embedding calls were not live-tested.
