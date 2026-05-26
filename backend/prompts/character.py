from __future__ import annotations


class CharacterExtractPrompt:
    system: str = (
        "You are a character analyst for drama production. "
        "Extract and consolidate all named characters from the provided sources.\n\n"
        "Return valid JSON:\n"
        '{"characters": [\n'
        '  {\n'
        '    "name": "canonical name",\n'
        '    "aliases": ["alternate names or titles"],\n'
        '    "role": "protagonist|antagonist|supporting|minor",\n'
        '    "importance": "primary|secondary|tertiary|background",\n'
        '    "first_appearance": "chapter or scene reference",\n'
        '    "scene_count": 0,\n'
        '    "relationship_to_protagonist": "...",\n'
        '    "narrative_function": "why this character exists in the story",\n'
        '    "is_protagonist": false\n'
        '  }\n'
        ']}\n\n'
        "Rules:\n"
        "- Consolidate name variants into canonical names. Put variants in aliases.\n"
        "- importance: primary = drives the plot, secondary = significant but not central, "
        "tertiary = recurring, background = appears once or twice.\n"
        "- narrative_function: one sentence explaining the character's purpose in the story.\n"
        "- Mark exactly one character as is_protagonist=true.\n"
        "- Include every named entity that appears in the sources.\n"
        "- If a character appears in scenes but not in relationships, still include them."
    )

    user_template: str = (
        "Chapter summaries:\n{chapter_summaries}\n\n"
        "Character relationships (from story extraction):\n{relationships}\n\n"
        "Named entities (from novel parse):\n{entities_persons}\n\n"
        "Characters appearing in scenes:\n{scene_characters}\n\n"
        "Extract the complete unified character list."
    )

    def render(self, chapter_summaries: str, relationships: str,
               entities_persons: str, scene_characters: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                chapter_summaries=chapter_summaries,
                relationships=relationships,
                entities_persons=entities_persons,
                scene_characters=scene_characters,
            ),
        }


class CharacterProfilePrompt:
    system: str = (
        "You are a character designer for short-form drama production. "
        "Generate a complete character profile from narrative context.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "appearance": {\n'
        '    "age_estimate": "e.g. late 20s",\n'
        '    "height": "tall|average|short",\n'
        '    "build": "slender|athletic|stocky|etc.",\n'
        '    "hair": "color, style, length",\n'
        '    "eyes": "color, expression quality",\n'
        '    "distinguishing_features": "scars, marks, unique traits",\n'
        '    "typical_expression": "resting face and common expressions"\n'
        '  },\n'
        '  "voice_profile": {\n'
        '    "pitch": "high|medium-high|medium|medium-low|low",\n'
        '    "tempo": "fast|measured|slow|deliberate",\n'
        '    "accent": "regional or social accent description",\n'
        '    "tone_quality": "warm|cool|rough|smooth|authoritative|etc.",\n'
        '    "speech_patterns": ["distinctive phrases or patterns"]\n'
        '  },\n'
        '  "personality": {\n'
        '    "traits": ["3-5 key personality traits"],\n'
        '    "motivation": "what drives this character",\n'
        '    "fears": ["deepest fears"],\n'
        '    "quirks": ["behavioral quirks"],\n'
        '    "moral_alignment": "lawful good|neutral good|chaotic good|lawful neutral|true neutral|chaotic neutral|lawful evil|neutral evil|chaotic evil"\n'
        '  },\n'
        '  "emotion_range": {\n'
        '    "dominant": "primary emotional state",\n'
        '    "secondary": ["other common emotions"],\n'
        '    "rarely_shows": ["emotions they suppress"],\n'
        '    "trigger_situations": ["situation → emotional response"]\n'
        '  },\n'
        '  "costume_style": {\n'
        '    "era": "time period of clothing",\n'
        '    "style": "clothing style description",\n'
        '    "signature_items": ["items always worn"],\n'
        '    "color_palette": ["dominant colors"],\n'
        '    "notes": "additional costume notes"\n'
        '  },\n'
        '  "backstory": "2-3 sentence backstory grounded in the narrative"\n'
        '}\n\n'
        "Rules:\n"
        "- Derive appearance from narrative context, character role, and era.\n"
        "- Voice profile must align with personality and social status.\n"
        "- Costume must match time_period from world setting.\n"
        "- If information is not in the source, infer reasonably from context.\n"
        "- Do not contradict information established in the narrative."
    )

    user_template: str = (
        "Character: {name}\n"
        "Role: {role}\n"
        "Importance: {importance}\n"
        "Narrative function: {narrative_function}\n\n"
        "Chapter summaries (where they appear):\n{chapter_context}\n\n"
        "Relationships:\n{relationships}\n\n"
        "Scenes they appear in:\n{scene_context}\n\n"
        "World setting:\n{world_setting}\n\n"
        "Generate the complete character profile."
    )

    def render(self, name: str, role: str, importance: str, narrative_function: str,
               chapter_context: str, relationships: str, scene_context: str,
               world_setting: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                name=name, role=role, importance=importance,
                narrative_function=narrative_function,
                chapter_context=chapter_context, relationships=relationships,
                scene_context=scene_context, world_setting=world_setting,
            ),
        }


class CharacterMergePrompt:
    system: str = (
        "You are checking whether two character entries refer to the same person. "
        "Decide if they should be merged.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "is_duplicate": true,\n'
        '  "merged_name": "canonical name",\n'
        '  "reasoning": "brief explanation of the decision",\n'
        '  "merged_profile": {...}  // only if is_duplicate=true, otherwise null\n'
        '}\n\n'
        "Rules:\n"
        "- Names with different spellings or titles (Dr. Smith / John Smith) → same person.\n"
        "- Same role + same relationships → likely duplicate.\n"
        "- Different narrative functions → different people (even if similar names).\n"
        "- If merging, the merged_profile should combine the best information from both.\n"
        "- A character and their alias (e.g. Batman / Bruce Wayne) are the same person."
    )

    user_template: str = (
        "Character A:\n"
        "  Name: {name_a}\n"
        "  Role: {role_a}\n"
        "  Importance: {importance_a}\n"
        "  Profile: {profile_a}\n\n"
        "Character B:\n"
        "  Name: {name_b}\n"
        "  Role: {role_b}\n"
        "  Importance: {importance_b}\n"
        "  Profile: {profile_b}\n\n"
        "Are these the same character?"
    )

    def render(self, name_a: str, role_a: str, importance_a: str, profile_a: str,
               name_b: str, role_b: str, importance_b: str, profile_b: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                name_a=name_a, role_a=role_a, importance_a=importance_a,
                profile_a=profile_a,
                name_b=name_b, role_b=role_b, importance_b=importance_b,
                profile_b=profile_b,
            ),
        }


class CharacterNormalizePrompt:
    system: str = (
        "You are a continuity editor for drama production. "
        "Review all character profiles for consistency and completeness.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "characters": [\n'
        '    {full profile with all fields normalized}\n'
        '  ],\n'
        '  "issues": [\n'
        '    {"character": "name", "field": "age|relationship|role|etc.",\n'
        '     "problem": "description of inconsistency"}\n'
        '  ]\n'
        '}\n\n'
        "Rules:\n"
        "- Age consistency: parent > child, mentor > student.\n"
        "- Relationship symmetry: if A is B's wife, B must be A's husband.\n"
        "- Era consistency: all costumes and voice profiles must match the same time period.\n"
        "- No two characters should have identical narrative functions.\n"
        "- Fill gaps in profiles with reasonable defaults marked as inferred.\n"
        "- Flag contradictions as issues — do NOT silently resolve them.\n"
        "- If no issues, return empty issues array."
    )

    user_template: str = (
        "Character profiles:\n{profiles_json}\n\n"
        "World setting:\n{world_setting}\n\n"
        "Normalize all profiles for consistency."
    )

    def render(self, profiles_json: str, world_setting: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                profiles_json=profiles_json,
                world_setting=world_setting,
            ),
        }
