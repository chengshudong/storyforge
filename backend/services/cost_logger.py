from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from interfaces.llm import ModelResponse

logger = logging.getLogger(__name__)

LOG_DIR = Path("logs/cost")


class CostLogger:
    """Logs per-request model usage to daily JSONL files per MODEL_POLICY §6."""

    @staticmethod
    def _ensure_dir() -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def log(
        request_id: str,
        project_id: str,
        provider: str,
        model: str,
        task: str,
        tokens_input: int,
        tokens_output: int,
        duration_ms: int,
        cached: bool = False,
        retry_count: int = 0,
        status: str = "success",
        cost_usd: float = 0.0,
        error: str | None = None,
    ) -> None:
        try:
            CostLogger._ensure_dir()
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            entry = {
                "request_id": request_id,
                "project_id": project_id,
                "provider": provider,
                "model": model,
                "task": task,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
                "cached": cached,
                "retry_count": retry_count,
                "status": status,
            }
            if error:
                entry["error"] = error
            log_path = LOG_DIR / f"{date_str}.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("cost log write failed: %s", e)

    @staticmethod
    def from_response(
        request_id: str,
        project_id: str,
        task: str,
        response: ModelResponse,
        cached: bool = False,
        retry_count: int = 0,
    ) -> None:
        CostLogger.log(
            request_id=request_id,
            project_id=project_id,
            provider=response.provider,
            model=response.model,
            task=task,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            duration_ms=response.duration_ms,
            cached=cached,
            retry_count=retry_count,
            status="success",
        )
