"""Standalone ASGI process that exposes the five RAG tools."""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from invoice_auditor.agents.Invoice_RAG_Agent.rag_agent_client import load_mcp_config
from invoice_auditor.tools.rag_tools.chunk_ranker import chunk_ranker
from invoice_auditor.tools.rag_tools.rag_evaluator import rag_evaluator
from invoice_auditor.tools.rag_tools.response_synthesizer import response_synthesizer
from invoice_auditor.tools.rag_tools.semantic_retriever import semantic_retriever
from invoice_auditor.tools.rag_tools.vector_indexer import vector_indexer

def create_mcp_server():
    config = load_mcp_config()
    server = FastMCP(
        config["name"],
        streamable_http_path=config["path"],
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["rag-mcp:*", "localhost:*", "127.0.0.1:*", "[::1]:*"],
            allowed_origins=["http://rag-mcp:*", "http://localhost:*", "http://127.0.0.1:*"],
        ),
    )
    for tool in (vector_indexer, semantic_retriever, chunk_ranker, response_synthesizer, rag_evaluator):
        server.add_tool(tool)


    @server.custom_route("/health", methods=["GET"])
    async def health(_request):
        return JSONResponse({"status": "ok"})
    return server


server = create_mcp_server()
app = server.streamable_http_app()
