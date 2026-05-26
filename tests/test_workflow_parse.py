import asyncio

import pytest

from workflows.novel_processing import build_parse_workflow, ParseNovelState


class MockAgent:
    async def process(self, file_path, file_format, project_id):
        return {
            "title": "Test",
            "char_count": 100,
            "chunk_count": 3,
            "chunk_ids": ["a", "b", "c"],
            "entities": {"persons": [], "locations": [], "key_terms": []},
            "collection": f"novel_{project_id}",
        }


@pytest.fixture
def workflow():
    return build_parse_workflow(MockAgent())


def test_workflow_parses_successfully(workflow):
    state = ParseNovelState(
        project_id="wf-001",
        file_path="/tmp/test.txt",
        file_format="txt",
    )
    result = asyncio.run(workflow.ainvoke(state))
    assert result["status"] == "parsed"
    assert result["error"] is None
    assert result["result"]["chunk_count"] == 3
    assert result["result"]["collection"] == "novel_wf-001"


def test_workflow_handles_error():
    class FailingAgent:
        async def process(self, file_path, file_format, project_id):
            raise RuntimeError("parse failed")

    wf = build_parse_workflow(FailingAgent())
    state = ParseNovelState(
        project_id="wf-002",
        file_path="/tmp/bad.txt",
        file_format="txt",
    )
    result = asyncio.run(wf.ainvoke(state))
    assert result["status"] == "failed"
    assert "parse failed" in result["error"]


def test_parse_state_defaults():
    state = ParseNovelState()
    assert state.project_id == ""
    assert state.status == "pending"
    assert state.result is None
    assert state.error is None
