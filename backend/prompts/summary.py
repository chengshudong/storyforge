from __future__ import annotations


class StorySummarizePrompt:
    system: str = (
        "You are a senior story analyst. Your task is to produce a comprehensive "
        "narrative summary from novel chapter data.\n\n"
        "Structure your response as valid JSON:\n"
        '  {"narrative_summary": "...", "protagonist_arc": "...", '
        '"central_conflict": "...", "turning_points": ["..."]}\n\n'
        "Rules:\n"
        "- Preserve the original tone and genre of the source material.\n"
        "- Identify literary devices (foreshadowing, symbolism) where present.\n"
        "- Mark uncertain inferences with [inferred: ...].\n"
        "- Write narrative_summary as 3-5 cohesive paragraphs.\n"
        "- protagonist_arc: describe the main character's journey across the story.\n"
        "- central_conflict: identify the primary narrative tension.\n"
        "- turning_points: list 3-7 key moments that shift the story direction."
    )

    user_template: str = (
        "Chapter data:\n{chapters}\n\n"
        "Entities (for reference):\n{entities}\n\n"
        "Produce a structured story summary."
    )

    def render(self, chapters: str, entities: str = "") -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(chapters=chapters, entities=entities or "{}"),
        }


class ChapterSummaryPrompt:
    system: str = (
        "You are a narrative summarizer. Summarize the given chapter text into "
        "a concise but complete overview.\n\n"
        "Return valid JSON:\n"
        '  {"chapter_summary": "...", "key_events": ["..."], '
        '"characters_appearing": ["..."], "location": "..."}\n\n'
        "Rules:\n"
        "- chapter_summary: 200-400 words covering the main events.\n"
        "- key_events: 3-8 bullet events in chronological order.\n"
        "- characters_appearing: list characters who appear or are mentioned.\n"
        "- location: primary setting of this chapter."
    )

    user_template: str = (
        "Chapter {chapter_index}:\n{chapter_text}\n\n"
        "Summarize this chapter."
    )

    def render(self, chapter_index: int, chapter_text: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                chapter_index=chapter_index,
                chapter_text=chapter_text[:12000],  # ~48K chars max for safety
            ),
        }


class MergeSummaryPrompt:
    system: str = (
        "You are merging multiple chapter summaries into one cohesive story-level summary.\n\n"
        "Return valid JSON:\n"
        '  {"merged_summary": "...", "key_themes": ["..."], "narrative_throughline": "..."}'
    )

    user_template: str = (
        "Chapter summaries to merge:\n{summaries}\n\n"
        "Produce a merged summary that captures the narrative arc."
    )

    def render(self, summaries: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(summaries=summaries),
        }
