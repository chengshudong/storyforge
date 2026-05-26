from __future__ import annotations


class ExtractionPrompt:
    system: str = (
        "You are a narrative structure analyzer. Extract structured information "
        "from the story summary provided.\n\n"
        "Return valid JSON:\n"
        "{\n"
        '  "timeline": [{"event": "...", "chapter_ref": N, "characters_involved": ["..."]}],\n'
        '  "conflicts": [{"type": "person_vs_person|person_vs_self|person_vs_society|person_vs_nature|person_vs_technology", '
        '"description": "...", "parties": ["..."], "stakes": "..."}],\n'
        '  "relationships": [{"character_a": "...", "character_b": "...", '
        '"relation_type": "...", "evolution": "...", "significance": "..."}],\n'
        '  "world_setting": {"time_period": "...", "primary_locations": ["..."], '
        '"social_rules": "...", "atmosphere": "...", "notable_systems": "..."}\n'
        "}\n\n"
        "Rules:\n"
        "- timeline: chronological events with approximate chapter references.\n"
        "- conflicts: classify each by type; include stakes.\n"
        "- relationships: capture significant character pairs and how their relationship evolves.\n"
        "- world_setting: describe the world in which the story takes place.\n"
        "- If information is not available, use null or empty list."
    )

    user_template: str = (
        "Story summary:\n{story_summary}\n\n"
        "Entities (for reference):\n{entities}\n\n"
        "Extract timeline, conflicts, relationships, and world setting."
    )

    def render(self, story_summary: str, entities: str = "") -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                story_summary=story_summary,
                entities=entities or "{}",
            ),
        }
