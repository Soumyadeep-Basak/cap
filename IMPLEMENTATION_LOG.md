git # Focused guardrails ? 2026-11-19

Scope clarified by user: prioritize RAG; keep other agents lightweight. Test
counts are not counts of guardrails. This implementation does not add full
A2A/MCP authentication, reviewer roles, a new orchestrator or a telemetry system.

Selected checks: bounded/safe query input, prompt-injection filtering, parsed
read-only SQL, scoped evidence/context and citations, strict RAG evaluation and
three-retry maximum. Outside RAG: file admission, existing invoice schema checks
and report recommendation consistency. Existing arithmetic/ERP rules remain.

RAG checks live in agents/Invoice_RAG_Agent/pipeline/guardrails. Other domain
checks live in each owning agent's guardrails package. Shared content helpers
are under security. Old SQL/input imports remain compatibility exports.

Baseline before guardrail wiring, using this copy's isolated .venv and declared
dependencies: six existing MCP regression tests passed. Tests use real localhost
MCP HTTP with controlled provider/storage boundaries. Live services are not
being tested.

## Runtime ownership

Paths are relative to agent/src/invoice_auditor.

| Selected guard | Definition | Actual execution points |
|---|---|---|
| Query safety and invoice relevance | agents/Invoice_RAG_Agent/pipeline/guardrails/input_guardrail.py and rag_security.py | Query API schema, graph entry before classification/SQL/retrieval, RAG MCP query tools |
| Untrusted content and prompt injection | security/content.py | Input classifier, extraction/OCR result and parsing, translation input/output, retrieved chunks, generation input/output; model system prompts explicitly treat evidence as data |
| Parsed read-only SQL | agents/Invoice_RAG_Agent/pipeline/guardrails/sql_security.py | Existing run_safe_select imports resolve here; single SELECT, allowed audit tables/functions, bounded LIMIT, read-only transaction, 5-second query timeout, 1-second lock timeout, pg_catalog search path |
| Evidence relevance, sufficiency and source scope | agents/Invoice_RAG_Agent/pipeline/guardrails/rag_security.py | Semantic retrieval, ranker, context assembly and client graph; removes explicitly weak/nonfinite scores, rejects foreign invoice chunks and unretrieved context sources, prevents model generation without context |
| Citations and evaluated groundedness | same rag_security.py | Evaluator tool validates cited invoice IDs against identified context; retained reflection model evaluates groundedness; final graph validates citations again before returning an accepted answer |
| Evaluation and retry bounds | same rag_security.py | Client reflection, routing and finalization recompute finite triad scores; average strictly above 0.7, up to three retries (four total attempts), controlled failure response |
| Basic file security | agents/Invoice_Extractor_Agent/guardrails/file_security.py | Watcher before checksum; extraction before parser/OCR; confined path, extension/signature, 20 MB file limit, 50 PDF pages, bounded PNG dimensions and DOCX expanded size |
| Existing Pydantic invoice schema | agents/Invoice_Validation_Agent/guardrails/data_validation.py | Existing validation graph before rules; missing optional extraction fields remain available to completeness rules |
| Evidence-consistent report recommendation | agents/Invoice_Reporting_Agent/guardrails/output_validation.py | Report construction before JSON/HTML writing; approval cannot contradict failed validation, missing fields or discrepancies; existing HTML escaping retained |

Old workflows/input_guardrail.py and tools/sql_tools.py are compatibility exports,
not duplicate implementations. Existing business arithmetic and ERP logic, API
response shape, database schema and deployment topology are retained.
SQL parsing adds sqlglot>=30.0,<31.0 to agent/requirements.txt.

## Deliberate limits

- No new authentication/authorization system, reviewer roles, universal MCP
  decorator, ADK budget system or Langfuse implementation was added in this
  focused pass. Source scoping is not caller-specific access control.
- Injection pattern detection and lexical invoice relevance are conservative
  filters, not guarantees against every adversarial or multilingual prompt.
- Source-ID validation proves provenance consistency, not semantic truth.
  Groundedness still depends on the existing evaluator and quality of evidence.
- Tests exercise actual MCP HTTP and LangGraph with controlled model/database
  boundaries. Live PostgreSQL transaction behavior, provider results, actual
  OCR binaries and a running full Docker deployment are not established here.
- Existing MCP 1.30 tests can log standalone-SSE ClosedResourceError messages on
  session cleanup; baseline tests already exhibited these, without test failure.

## Verification

Run from this repository using its local .venv, not the earlier FA3 environment:

    $env:PYTHONPATH='agent/src'
    .venv\Scripts\python.exe -m pytest tests -q --tb=short --disable-warnings
    .venv\Scripts\python.exe -m compileall -q agent/src tests
    git diff --check

The baseline suite passed six tests. After the focused changes the combined
suite passed 36 tests plus six subtests (25.06 seconds), before the final three
execution-boundary checks were added. Final results are recorded below.

Final result: **39 passed, 6 subtests passed, 1 warning**, 33.84 seconds; zero failures. Python compileall and git diff --check also passed. The warning is the dependency deprecation warning reported by pytest.
