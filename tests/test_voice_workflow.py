from __future__ import annotations

import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from workflows.voice_generation import (
    PHASE_CLONE,
    PHASE_PREVIEW,
    PHASE_SYNTHESIZE,
    VoiceGenerationState,
    build_voice_workflow,
)


class TestVoiceGenerationState:
    def test_defaults(self):
        state = VoiceGenerationState(project_id="00000000-0000-0000-0000-000000000001")
        assert state.project_id == "00000000-0000-0000-0000-000000000001"
        assert state.characters == []
        assert state.scenes == []
        assert state.phases == [PHASE_CLONE, PHASE_SYNTHESIZE, PHASE_PREVIEW]
        assert state.regenerate is False
        assert state.speaker_map == {}
        assert state.status == "pending"

    def test_custom_phases(self):
        state = VoiceGenerationState(
            project_id="p1",
            phases=[PHASE_CLONE],
            regenerate=True,
        )
        assert len(state.phases) == 1
        assert PHASE_CLONE in state.phases
        assert state.regenerate is True


class TestBuildWorkflow:
    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent._library = MagicMock()
        agent._library.get_speaker = AsyncMock(return_value=None)
        agent._library.set_speaker = AsyncMock()
        agent._library.get_synthesis = AsyncMock(return_value=None)
        agent._library.set_synthesis = AsyncMock()
        agent._voices = MagicMock()
        agent._voices.get = AsyncMock(return_value=None)
        agent._voices.create = AsyncMock()
        agent._voices.get_selected = AsyncMock(return_value=None)
        agent._provider = MagicMock()
        agent._provider.health = AsyncMock(return_value=True)
        agent.clone_character_voice = AsyncMock(return_value=str(uuid.uuid4()))
        agent.synthesize_dialogue = AsyncMock(return_value=MagicMock(
            status=MagicMock(value="done"), audio=b"\x00" * 100, duration_ms=100,
        ))
        agent.preview_voice = AsyncMock(return_value=b"\x00" * 100)
        agent.save_voice_asset = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        agent._upload_audio = AsyncMock(return_value="projects/p1/voices/test.wav")
        agent._cache = MagicMock()
        agent._cache.get = AsyncMock(return_value=None)
        agent._cache.set = AsyncMock()
        agent._cache.build_key.return_value = "cache:key"
        return agent

    def test_graph_compiles(self, mock_agent):
        workflow = build_voice_workflow(mock_agent)
        assert workflow is not None

    def test_clone_only_phases(self, mock_agent):
        workflow = build_voice_workflow(mock_agent)
        assert workflow is not None
        state = VoiceGenerationState(
            project_id="00000000-0000-0000-0000-000000000001",
            phases=[PHASE_CLONE],
        )
        assert len(state.phases) == 1

    def test_all_phases_included(self, mock_agent):
        workflow = build_voice_workflow(mock_agent)
        assert workflow is not None
        state = VoiceGenerationState(
            project_id="00000000-0000-0000-0000-000000000001",
            phases=[PHASE_CLONE, PHASE_SYNTHESIZE, PHASE_PREVIEW],
        )
        assert len(state.phases) == 3

    def test_speaker_map_starts_empty(self, mock_agent):
        state = VoiceGenerationState(project_id="p1")
        assert state.speaker_map == {}
        assert state.selected_voice_ids == {}
        assert state.clone_voice_assets == []

    def test_workflow_state_has_batch_id(self):
        state = VoiceGenerationState(project_id="p1")
        assert state.batch_id is not None
        assert len(state.batch_id) > 0

    def test_errors_list_starts_empty(self):
        state = VoiceGenerationState(project_id="p1")
        assert state.errors == []
