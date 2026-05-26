from __future__ import annotations


class EpisodePlanPrompt:
    system: str = (
        "You are a drama series planner converting novels into serialized episodes "
        "for short-form video production.\n\n"
        "Return valid JSON:\n"
        '{"episodes": [\n'
        '  {\n'
        '    "episode_number": 1,\n'
        '    "title": "...",\n'
        '    "summary": "...",\n'
        '    "chapter_range": [start_chapter, end_chapter],\n'
        '    "cliffhanger": "...",\n'
        '    "key_scenes": ["scene beat 1", "scene beat 2", "..."]\n'
        '  }\n'
        ']}\n\n'
        "Rules:\n"
        "- Each episode must be a self-contained narrative unit.\n"
        "- End every episode EXCEPT the final one with a cliffhanger or hook.\n"
        "- The final episode should provide narrative closure.\n"
        "- Distribute turning points evenly across episodes for good pacing.\n"
        "- Target episode count based on novel length: short (<20 chapters) → 5-8 episodes, "
        "medium (20-50 chapters) → 8-15 episodes, long (>50 chapters) → 12-20 episodes.\n"
        "- Every chapter MUST be assigned to exactly one episode — no gaps, no overlaps.\n"
        "- chapter_range uses 1-based chapter numbers (first chapter = 1).\n"
        "- key_scenes: 3-5 scene beats that capture the narrative arc of this episode.\n"
        "- cliffhanger: a compelling hook into the next episode. Use null for the final episode."
    )

    user_template: str = (
        "Story summary:\n{story_summary}\n\n"
        "Timeline:\n{timeline}\n\n"
        "Chapter count: {chapter_count}\n\n"
        "Plan the episode breakdown."
    )

    def render(self, story_summary: str, timeline: str, chapter_count: int) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                story_summary=story_summary,
                timeline=timeline,
                chapter_count=chapter_count,
            ),
        }


class EpisodeRegeneratePrompt:
    system: str = (
        "You are editing a single episode of a serialized drama series based on "
        "human feedback.\n\n"
        "Return valid JSON:\n"
        '{"title": "...", "summary": "...", "cliffhanger": "...", "key_scenes": ["..."]}\n\n'
        "Rules:\n"
        "- Incorporate the feedback while preserving the original chapter_range and episode_number.\n"
        "- Maintain consistency with adjacent episodes.\n"
        "- Improve based on the feedback provided."
    )

    user_template: str = (
        "Original episode:\n"
        "  Number: {episode_number}\n"
        "  Title: {title}\n"
        "  Summary: {summary}\n"
        "  Key scenes: {key_scenes}\n"
        "  Cliffhanger: {cliffhanger}\n\n"
        "Adjacent episodes (for context):\n{adjacent}\n\n"
        "Feedback to incorporate:\n{feedback}\n\n"
        "Regenerate this episode."
    )

    def render(self, episode: dict, adjacent: str, feedback: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                episode_number=episode.get("episode_number", 0),
                title=episode.get("title", ""),
                summary=episode.get("summary", ""),
                key_scenes=episode.get("key_scenes", []),
                cliffhanger=episode.get("cliffhanger", ""),
                adjacent=adjacent,
                feedback=feedback,
            ),
        }
