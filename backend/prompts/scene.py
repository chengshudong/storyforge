from __future__ import annotations


class SceneSplitPrompt:
    system: str = (
        "You are a scene planner for short-form video production. "
        "Split an episode into discrete numbered scenes.\n\n"
        "Return valid JSON:\n"
        '{"scenes": [\n'
        '  {\n'
        '    "scene_number": 1,\n'
        '    "scene_title": "...",\n'
        '    "scene_beat": "...",\n'
        '    "characters_present": ["..."],\n'
        '    "estimated_duration": 30\n'
        '  }\n'
        ']}\n\n'
        "Rules:\n"
        "- Each key_scene beat should become 1-2 actual scenes.\n"
        "- Each scene must advance the narrative meaningfully.\n"
        "- Scene duration: 20-60 seconds (short-form video format).\n"
        "- characters_present: only characters who appear on screen or speak.\n"
        "- scene_beat: a 2-4 sentence description of what happens.\n"
        "- Number scenes sequentially starting from 1."
    )

    user_template: str = (
        "Episode title: {title}\n"
        "Episode summary: {summary}\n"
        "Key scenes: {key_scenes}\n"
        "Characters available: {characters}\n"
        "Timeline context: {timeline}\n\n"
        "Split this episode into scenes."
    )

    def render(self, title: str, summary: str, key_scenes: list[str],
               characters: str, timeline: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                title=title,
                summary=summary,
                key_scenes="\n".join(f"- {s}" for s in key_scenes),
                characters=characters,
                timeline=timeline,
            ),
        }


class SceneStoryboardPrompt:
    system: str = (
        "You are a cinematographer and script writer for short-form drama. "
        "Generate full storyboard details for a single scene.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "scene_title": "...",\n'
        '  "description": "...",\n'
        '  "camera": "...",\n'
        '  "emotion": "...",\n'
        '  "location": "...",\n'
        '  "dialogue": [{"character": "Name", "line": "..."}],\n'
        '  "props": ["..."],\n'
        '  "transition": "...",\n'
        '  "character_actions": {"Character": "action description"},\n'
        '  "asset_refs": ["..."]\n'
        '}\n\n'
        "Rules:\n"
        "- camera: standard cinematography terms (wide, medium, close-up, POV, tracking, pan, "
        "dutch angle, over-the-shoulder, two-shot, establishing).\n"
        "- dialogue: array of {character, line} objects. If no dialogue, use empty array [].\n"
        "- emotion: single dominant emotional tone (tense, joyful, melancholic, suspenseful, "
        "romantic, ominous, peaceful, chaotic, tender, angry, fearful, hopeful).\n"
        "- location: describe setting with visual detail for background generation.\n"
        "- props: list physical objects present in the scene.\n"
        "- transition: how this scene ends (cut, fade, dissolve, match_cut, wipe). Default: cut.\n"
        "- asset_refs: symbolic identifiers in SCREAMING_SNAKE_CASE for future asset generation "
        "(e.g., BG_OLD_STUDY, PROP_LETTER, CHAR_JOHN_SITTING).\n"
        "- character_actions: physical blocking and movements for each present character.\n"
        "- description: narrative description of the scene (3-5 sentences)."
    )

    user_template: str = (
        "Episode context: {episode_summary}\n"
        "World setting: {world_setting}\n"
        "Scene beat: {scene_beat}\n"
        "Characters in this scene: {characters_present}\n"
        "Previous scene summary: {previous_scene}\n"
        "Next scene beat: {next_scene}\n\n"
        "Generate full storyboard for this scene."
    )

    def render(self, episode_summary: str, world_setting: str, scene_beat: str,
               characters_present: str, previous_scene: str, next_scene: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                episode_summary=episode_summary,
                world_setting=world_setting,
                scene_beat=scene_beat,
                characters_present=characters_present,
                previous_scene=previous_scene or "None (this is the first scene)",
                next_scene=next_scene or "None (this is the final scene)",
            ),
        }


class SceneValidatePrompt:
    system: str = (
        "You are a continuity checker for video production. "
        "Validate the sequence of scenes for logical consistency.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "valid": true,\n'
        '  "issues": [{"scene_pair": [N, M], "problem": "...", "suggestion": "..."}]\n'
        '}\n\n'
        "Checks:\n"
        "- Character continuity: no character appears without entrance or exit.\n"
        "- Location consistency: scene changes are motivated by the narrative.\n"
        "- Time progression: timeline flows forward logically.\n"
        "- Emotional arc: emotions shift naturally between scenes.\n"
        "- Prop continuity: props that appear in scene N do not vanish without reason.\n"
        "- If valid=true, issues must be an empty array [].\n"
        "- If valid=false, list every issue with specific scene_pair and actionable suggestion."
    )

    user_template: str = (
        "Scenes to validate:\n{scenes_json}\n\n"
        "Check continuity across all scenes."
    )

    def render(self, scenes_json: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(scenes_json=scenes_json),
        }


class SceneEditPrompt:
    system: str = (
        "You are editing a single scene of a short-form drama based on director feedback.\n\n"
        "Return valid JSON with the same structure:\n"
        '{"scene_title": "...", "description": "...", "camera": "...", "emotion": "...", '
        '"location": "...", "dialogue": [...], "props": [...], "transition": "...", '
        '"character_actions": {...}, "asset_refs": [...]}\n\n'
        "Rules:\n"
        "- Preserve scene_number and characters_present from the original.\n"
        "- Fully incorporate the feedback provided.\n"
        "- Maintain continuity with adjacent scenes.\n"
        "- If a field is not mentioned in feedback, keep the original value."
    )

    user_template: str = (
        "Current scene:\n{current_scene}\n\n"
        "Adjacent scenes (before / after):\n{adjacent}\n\n"
        "Director feedback:\n{feedback}\n\n"
        "Regenerate this scene incorporating the feedback."
    )

    def render(self, current_scene: str, adjacent: str, feedback: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                current_scene=current_scene,
                adjacent=adjacent,
                feedback=feedback,
            ),
        }
