"""Wire the unstructured RAG path into the invoice query graph."""

from langgraph.graph import END, StateGraph

from invoice_auditor.agents.Invoice_RAG_Agent.pipeline import rag_pipeline as rag


def add_rag_path(workflow: StateGraph) -> None:
    workflow.add_node("retrieve", rag.retrieve_node)
    workflow.add_node("augment", rag.augment_node)
    workflow.add_node("generate", rag.generate_node)
    workflow.add_node("reflect", rag.reflect_node)
    workflow.add_node("finalize_unstructured", rag.finalize_unstructured_node)
    workflow.add_node("prepare_retry", rag.prepare_retry_node)
    workflow.add_edge("retrieve", "augment")
    workflow.add_edge("augment", "generate")
    workflow.add_edge("generate", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        rag.route_after_reflection,
        {
            "accept": "finalize_unstructured",
            "retry": "prepare_retry",
            "reject": "finalize_unstructured",
        },
    )
    workflow.add_edge("prepare_retry", "retrieve")
    workflow.add_edge("finalize_unstructured", END)
