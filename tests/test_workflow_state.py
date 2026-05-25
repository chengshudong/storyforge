import uuid

from domain.models import Project, ProjectStatus
from workflows.state import ProjectState


def test_project_state_empty():
    state = ProjectState()
    assert state.project is None
    assert state.project_id is None
    assert state.episodes == []
    assert state.characters == []
    assert state.scenes == []


def test_project_state_with_project():
    project = Project(
        id=uuid.uuid4(),
        name="Test",
        status=ProjectStatus.PENDING,
    )
    state = ProjectState(project=project)
    assert state.project_id == project.id
    assert state.status == ProjectStatus.PENDING


def test_project_state_to_dict():
    project = Project(
        id=uuid.uuid4(),
        name="Test",
        status=ProjectStatus.EPISODES,
    )
    state = ProjectState(project=project)
    d = state.to_dict()
    assert d["project_id"] == str(project.id)
    assert d["status"] == "episodes"
    assert d["episode_count"] == 0
    assert d["character_count"] == 0
