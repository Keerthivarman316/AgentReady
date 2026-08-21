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
