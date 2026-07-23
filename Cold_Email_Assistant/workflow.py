from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from nodes import (
    check_reply_node,
    enrich_lead_node,
    generate_draft_node,
    human_review_gate,
    route_after_review,
    send_email_node,
)
from state import ColdEmailState


def build_graph() -> StateGraph:
    graph = StateGraph(ColdEmailState)

    graph.add_node("enrich_lead_node", enrich_lead_node)
    graph.add_node("generate_draft_node", generate_draft_node)
    graph.add_node("human_review_gate", human_review_gate)
    graph.add_node("send_email_node", send_email_node)
    graph.add_node("check_reply_node", check_reply_node)

    graph.set_entry_point("enrich_lead_node")

    graph.add_edge("enrich_lead_node", "generate_draft_node")
    graph.add_edge("generate_draft_node", "human_review_gate")

    graph.add_conditional_edges(
        "human_review_gate",
        route_after_review,
        {
            "approved": "send_email_node",
            "revise": "generate_draft_node",
            "rejected": END,
        },
    )

    graph.add_edge("send_email_node", "check_reply_node")
    graph.add_edge("check_reply_node", END)

    return graph


def compile_workflow():
    graph = build_graph()
    checkpointer = MemorySaver()

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review_gate"],
    )
