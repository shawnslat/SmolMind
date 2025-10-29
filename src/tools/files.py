from __future__ import annotations

import re
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, field_validator

from . import ToolContext


class SummarizeFileInput(BaseModel):
    path: str = Field(..., description="Path to the text or markdown file to summarise.")
    max_sentences: int = Field(
        5, ge=1, le=12, description="Maximum number of sentences to include in the summary."
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Path cannot be empty.")
        return value


SENTENCE_REGEX = re.compile(r"(?<=[.!?])\s+")


def _load_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, "Could not decode file content.")


def _sentences_from_text(text: str) -> List[str]:
    candidates = [segment.strip() for segment in SENTENCE_REGEX.split(text) if segment.strip()]
    return candidates or [text.strip()]


def summarize_file(params: SummarizeFileInput, context: ToolContext) -> str:
    """Summarise a text or markdown file using a deterministic heuristic."""
    file_path = Path(params.path)
    if not file_path.is_absolute():
        file_path = context.base_path / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"File '{file_path}' does not exist.")
    if not file_path.is_file():
        raise IsADirectoryError(f"Expected a file but received '{file_path}'.")

    text = _load_text(file_path)

    # Remove markdown code blocks to avoid noisy summaries.
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    sentences = _sentences_from_text(cleaned)
    summary_sentences = sentences[: params.max_sentences]

    bullet_points = "\n".join(f"- {sentence}" for sentence in summary_sentences if sentence)
    if not bullet_points:
        bullet_points = "- (file was empty)"

    return (
        f"Summary of '{file_path.name}':\n{bullet_points}\n\n"
        "Tip: Use `max_sentences` to control summarisation length."
    )


__all__ = ["SummarizeFileInput", "summarize_file"]
