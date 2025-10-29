from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class ModelSettings(BaseSettings):
    """Configuration controlling how the language model is loaded."""

    model_id: str = Field(
        "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        description="Default HF model to use for chat completions.",
        env="SMOLMIND_MODEL_ID",
    )
    device_map: str = Field(
        "auto",
        description="Device placement strategy passed to transformers.pipeline.",
        env="SMOLMIND_DEVICE",
    )
    dtype: Optional[str] = Field(
        None,
        description="Optional torch dtype (e.g. float16, bfloat16).",
        env="SMOLMIND_DTYPE",
    )
    max_new_tokens: int = Field(
        512,
        ge=32,
        le=1024,
        description="Maximum tokens generated per assistant turn.",
        env="SMOLMIND_MAX_NEW_TOKENS",
    )
    temperature: float = Field(
        0.3,
        ge=0.0,
        le=1.5,
        description="Sampling temperature applied during generation.",
        env="SMOLMIND_TEMPERATURE",
    )
    top_p: float = Field(
        0.9,
        ge=0.1,
        le=1.0,
        description="Top-p nucleus sampling parameter.",
        env="SMOLMIND_TOP_P",
    )
    hf_token: Optional[str] = Field(
        None, description="Optional Hugging Face access token for gated models.", env="HUGGING_FACE_HUB_TOKEN"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _resolve_torch_dtype(dtype_name: Optional[str]):
    if not dtype_name:
        return None
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on optional torch install
        raise RuntimeError("Torch is required when specifying SMOLMIND_DTYPE.") from exc

    try:
        return getattr(torch, dtype_name)
    except AttributeError as exc:
        raise ValueError(f"Unsupported torch dtype '{dtype_name}'.") from exc


def _default_dtype_for_device(device_map: str | None) -> Optional[str]:
    try:
        import torch
    except ImportError:
        return None

    device_map = (device_map or "auto").lower()
    # On Apple MPS, float16 often leads to NaNs; default to float32 unless user overrides.
    if "mps" in device_map or (device_map == "auto" and torch.backends.mps.is_available()):
        return "float32"
    return None


@lru_cache(maxsize=2)
def _load_pipeline(model_id: str, device_map: str, dtype_name: Optional[str]):
    """Internal cache to avoid re-loading models repeatedly."""
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("transformers is required. Install via `pip install transformers`.") from exc

    pipeline_kwargs: Dict[str, Any] = {
        "task": "text-generation",
        "model": model_id,
        "device_map": device_map,
    }
    dtype = _resolve_torch_dtype(dtype_name)
    if dtype is not None:
        pipeline_kwargs["torch_dtype"] = dtype

    logger.info("Loading transformers pipeline for %s", model_id)
    try:
        return pipeline(**pipeline_kwargs)
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load model '{model_id}'. "
            "Ensure the identifier is public or provide a Hugging Face token via SMOLMIND_MODEL_ID / HUGGING_FACE_HUB_TOKEN."
        ) from exc


def get_chat_pipeline(settings: ModelSettings | None = None):
    """Load and cache the transformers pipeline backing the assistant."""
    settings = settings or ModelSettings()
    dtype_name = settings.dtype or _default_dtype_for_device(settings.device_map)
    return _load_pipeline(settings.model_id, settings.device_map, dtype_name)


def generate_completion(messages: List[Dict[str, str]], settings: ModelSettings | None = None) -> str:
    """Proxy that converts a chat history into a prompt and calls the pipeline."""
    settings = settings or ModelSettings()
    pipe = get_chat_pipeline(settings)

    formatted = _format_chat_messages(messages)
    generation_args: Dict[str, Any] = {
        "max_new_tokens": settings.max_new_tokens,
        "do_sample": True,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "return_full_text": False,
    }
    outputs = pipe(formatted, **generation_args)
    if not outputs:
        raise RuntimeError("Pipeline returned no output.")

    reply = outputs[0].get("generated_text", "").strip()
    if not reply:
        raise RuntimeError("Model returned an empty response.")
    return reply


CHAT_TEMPLATE_HEADER = (
    "You are SmolMind, a local-first assistant composed of specialised micro-agents."
    " Always provide helpful, concise answers.\n"
)


def _format_chat_messages(messages: List[Dict[str, str]]) -> str:
    parts = [CHAT_TEMPLATE_HEADER]
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        parts.append(f"<|{role}|>\n{content}\n")
    parts.append("<|assistant|>\n")
    return "\n".join(parts)


def get_hf_action_agent(settings: ModelSettings | None = None):
    """Optional helper loading the Hugging Face Agents API for extended tool use."""
    try:
        from transformers.agents import HfAgent  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional feature
        raise ImportError(
            "hf-agents is not installed. Install via `pip install hf-agents` to enable this feature."
        ) from exc

    settings = settings or ModelSettings()
    return HfAgent(settings.model_id, token=settings.hf_token)


__all__ = [
    "ModelSettings",
    "generate_completion",
    "get_chat_pipeline",
    "get_hf_action_agent",
]
