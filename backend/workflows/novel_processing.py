from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END

from agents.novel_agent import NovelAgent


@dataclass
class ParseNovelState:
    project_id: str = ""
    file_path: str = ""
    file_format: str = ""
    result: dict | None = None
    error: str | None = None
    status: str = "pending"


async def parse_node(state: ParseNovelState, agent: NovelAgent) -> dict:
    try:
        result = await agent.process(state.file_path, state.file_format, state.project_id)
        return {"result": result, "status": "parsed", "error": None}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


def build_parse_workflow(agent: NovelAgent) -> StateGraph:
    graph = StateGraph(ParseNovelState)

    async def _parse_node(state: ParseNovelState) -> dict:
        return await parse_node(state, agent)

    graph.add_node("parse", _parse_node)
    graph.set_entry_point("parse")
    graph.add_edge("parse", END)

    return graph.compile()
