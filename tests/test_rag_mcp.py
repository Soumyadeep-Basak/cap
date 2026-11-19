"""Exercise the RAG agent and all five tools over real MCP HTTP."""

import asyncio
import os
import socket
import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent/src"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/rag_test")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")

from invoice_auditor.agents.Invoice_RAG_Agent.mcp_tool_server.main import app
from invoice_auditor.agents.Invoice_RAG_Agent.pipeline import (
    augmentation_agent,
    generation_agent,
    indexing_agent,
    reflection_agent,
    retrieval_agent,
)
from invoice_auditor.agents.Invoice_RAG_Agent.rag_agent_client import index_invoice
from invoice_auditor.workflows import rag_workflow


class RagMcpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        cls.addClassCleanup(listener.close)
        cls.url = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()

        def stop():
            server.should_exit = True
            thread.join(timeout=5)

        cls.addClassCleanup(stop)
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        else:
            raise RuntimeError("RAG MCP test server did not start")
        env = patch.dict(os.environ, {"RAG_MCP_URL": cls.url})
        env.start()
        cls.addClassCleanup(env.stop)

    def test_catalog_and_argument_validation(self):
        async def discover():
            async with streamable_http_client(self.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertEqual(names, {
                        "vector_indexer", "semantic_retriever", "chunk_ranker",
                        "response_synthesizer", "rag_evaluator",
                    })
                    result = await session.call_tool("vector_indexer", {"invoice_id": "invalid"})
                    self.assertTrue(result.isError)

        asyncio.run(discover())

    def test_workflow_dispatches_all_five_tools_and_retries(self):
        invoice_id = str(uuid4())
        question = "What does this invoice say about freight?"
        evidence = "Freight was EUR 20."
        chunk = {"invoice_id": invoice_id, "chunk_text": evidence}
        context = f"[invoice_id={invoice_id} source=raw_text]\n{evidence}"
        cited_answer = evidence + " Sources: " + invoice_id
        calls = []
        scores = iter((0.7, 1.0))
        synthesis_attempts = iter((False, True))

        def stage(name, expected, output):
            def invoke(state):
                calls.append(name)
                if name == "synthesize":
                    self.assertEqual(state.pop("bypass_cache"), next(synthesis_attempts))
                self.assertEqual(state, expected)
                return output() if callable(output) else output
            return SimpleNamespace(invoke=invoke)

        def score():
            value = next(scores)
            return {"answer_relevance": value, "groundedness": value, "context_relevance": value}

        def mock(module, name, fn):
            patcher = patch.object(module, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)

        mock(retrieval_agent, "retrieval_graph", stage(
            "retrieve", {"invoice_id": invoice_id, "question": question, "top_k": None},
            {"retrieved_chunks": [chunk]},
        ))
        mock(augmentation_agent, "augmentation_graph", stage(
            "rank", {"question": question, "retrieved_chunks": [chunk]},
            {"reranked_chunks": [chunk], "assembled_context": context},
        ))
        mock(generation_agent, "generation_graph", stage(
            "synthesize", {"question": question, "assembled_context": context},
            {"answer": cited_answer},
        ))
        mock(reflection_agent, "reflection_graph", stage(
            "evaluate", {"question": question, "assembled_context": context, "answer": cited_answer},
            score,
        ))
        mock(indexing_agent, "indexing_graph", stage(
            "index", {"invoice_id": invoice_id, "report": {"amount": "20.00"}},
            {"index_status": "completed", "indexed_chunks": 1},
        ))
        mock(rag_workflow, "input_guardrail_graph", SimpleNamespace(invoke=lambda _: {"is_safe": True}))
        mock(rag_workflow, "_invoke_bedrock_json", lambda **_: {"query_type": "unstructured"})

        result = rag_workflow.rag_query_graph.invoke({"invoice_id": invoice_id, "question": question})
        indexed = index_invoice({"invoice_id": invoice_id, "report": {"amount": Decimal("20.00")}})
        self.assertEqual(result["answer"], cited_answer)
        self.assertEqual(result["query_status"], "completed")
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(indexed["indexed_chunks"], 1)
        self.assertEqual(calls, ["retrieve", "rank", "synthesize", "evaluate"] * 2 + ["index"])

    def test_augmentation_passes_only_three_chunks_to_generation(self):
        chunks = [
            {"invoice_id": str(uuid4()), "chunk_text": f"Evidence {index}", "score": 1 - index / 10}
            for index in range(5)
        ]
        result = augmentation_agent.augmentation_graph.invoke(
            {"question": "Evidence", "retrieved_chunks": chunks}
        )
        self.assertEqual(len(result["reranked_chunks"]), 5)
        self.assertEqual(result["assembled_context"].count("[invoice_id="), 3)
        self.assertNotIn("Evidence 3", result["assembled_context"])

    def test_reflection_rejects_malformed_scores(self):
        for score in (True, None, float("nan"), float("inf"), 1.1, -0.1):
            with self.subTest(score=score), self.assertRaises(ValueError):
                reflection_agent._parse_score(score)

    def test_tool_failure_preserves_index_error(self):
        with patch.object(indexing_agent.indexing_graph, "invoke", side_effect=RuntimeError("test")):
            result = index_invoice({"invoice_id": str(uuid4())})
        self.assertEqual(result["index_status"], "failed")
        self.assertEqual(result["indexed_chunks"], 0)


    def test_field_paths_are_readable_in_query_answers(self):
        from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.rag_pipeline import (
            finalize_unstructured_node,
        )

        invoice_id = str(uuid4())
        state = {
            "answer": "Check line_items[0].unit_price and line_items[2].currency.",
            "evaluation_status": "completed",
            "passed_reflection": True,
            "average_score": 0.95,
            "answer_relevance": 0.95, "groundedness": 0.95, "context_relevance": 0.95,
            "assembled_context": f"[invoice_id={invoice_id} source=raw_text]\nInvoice pricing evidence",
        }
        state["answer"] += " Sources: " + invoice_id
        result = finalize_unstructured_node(state)
        self.assertEqual(result["answer"].split(" Sources:")[0], "Check Line item 1 · Unit price and Line item 3 · Currency.")
        sql_answer = rag_workflow._format_sql_answer(
            "Show discrepancies", [{"field_name": "line_items[0].unit_price"}],
        )
        self.assertIn("Line item 1 · Unit price", sql_answer)


if __name__ == "__main__":
    unittest.main()
