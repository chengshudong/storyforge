from __future__ import annotations

import re
from pathlib import Path

from interfaces.parser import NovelParser, ParsedDocument


class UnstructuredAdapter(NovelParser):
    """Wraps Unstructured to implement the NovelParser interface."""

    async def parse(self, file_path: str, file_format: str) -> ParsedDocument:
        path = Path(file_path)
        title = path.stem
        metadata: dict = {"format": file_format, "file_path": file_path}

        if file_format == "txt":
            text = path.read_text(encoding="utf-8")
            metadata["encoding"] = "utf-8"

        elif file_format in ("docx", "epub"):
            from unstructured.partition.auto import partition

            elements = partition(filename=str(path))
            text = "\n\n".join(str(el) for el in elements)

        else:
            raise ValueError(f"Unsupported format: {file_format}")

        metadata["char_count"] = len(text)
        metadata["size_bytes"] = path.stat().st_size

        return ParsedDocument(title=title, full_text=text, metadata=metadata)

    async def split(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> list[dict]:
        from unstructured.chunking.title import chunk_by_title
        from unstructured.documents.elements import NarrativeText

        element = NarrativeText(text=text)
        chunks = chunk_by_title(
            [element],
            max_characters=chunk_size,
            overlap=chunk_overlap,
        )
        return [
            {"index": i, "text": chunk.text, "char_count": len(chunk.text)}
            for i, chunk in enumerate(chunks)
        ]

    async def extract(self, text: str) -> dict:
        persons = list(set(re.findall(r"[一-鿿]{2,4}(?:先生|女士|小姐|老师|医生|经理|总裁|导演|老板|夫人|公子|小姐|殿下)?", text)))
        locations = list(set(re.findall(r"(?:[一-鿿]{2,4})(?:市|县|省|镇|村|街|路|广场|大厦|酒店|学校|医院|公园|花园|山|河|湖|海|岛|国|城|楼|房|舍|仓|阁|院|府|宅|庙|观|寺|庵|堂|园|林)", text)))
        return {"persons": persons[:50], "locations": locations[:50], "key_terms": []}
