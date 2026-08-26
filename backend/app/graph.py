from typing import TypedDict

from langgraph.graph import StateGraph, END


class PingState(TypedDict):
    message: str
    reply: str


def _echo(state: PingState) -> PingState:
    return {"reply": f"pong: {state['message']}"}


def build_ping_graph():
    graph = StateGraph(PingState)
    graph.add_node("echo", _echo)
    graph.set_entry_point("echo")
    graph.add_edge("echo", END)
    return graph.compile()


ping_graph = build_ping_graph()

# Re-exported so `app.graph` stays the single place to import a compiled
# LangGraph from. Each graph is defined alongside the domain logic it wraps
# (app.intent_agent, app.buyer_agent, app.checkout) rather than here, since
# graph.py importing them (not the other way around) is what keeps this
# import-safe: none of those modules import app.graph.
from app.intent_agent import intent_graph  # noqa: E402,F401
from app.buyer_agent import buyer_decision_graph  # noqa: E402,F401
from app.checkout import checkout_graph  # noqa: E402,F401
