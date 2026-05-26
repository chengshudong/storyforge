from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    title: str
    full_text: str
    chunks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class NovelParser(ABC):
    @abstractmethod
    async def parse(self, file_path: str, file_format: str) -> ParsedDocument:
        """Parse raw file into plain text + metadata."""

    @abstractmethod
    async def split(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> list[dict]:
        """Split full text into embeddable chunks."""

    @abstractmethod
    async def extract(self, text: str) -> dict:
        """Extract entities: {'persons': [], 'locations': [], 'key_terms': []}."""
