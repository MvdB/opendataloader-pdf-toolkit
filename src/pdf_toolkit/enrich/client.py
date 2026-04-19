from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    chat_model: str | None = None
    embedding_model: str | None = None
    vlm_model: str | None = None
    # Optional per-function base-URL overrides. Useful when the chat model and
    # the embedding model live behind different endpoints — e.g. vLLM serving
    # Gemma 4 for chat + Ollama serving nomic-embed-text for embeddings.
    # When unset, each call uses `base_url`.
    embedding_base_url: str | None = None
    vlm_base_url: str | None = None
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            # vLLM / Ollama / LM Studio accept any non-empty string; "EMPTY" is the convention.
            api_key=os.environ.get("LLM_API_KEY", "EMPTY"),
            chat_model=os.environ.get("LLM_MODEL"),
            embedding_model=os.environ.get("EMBEDDING_MODEL"),
            vlm_model=os.environ.get("VLM_MODEL"),
            embedding_base_url=os.environ.get("EMBEDDING_BASE_URL") or None,
            vlm_base_url=os.environ.get("VLM_BASE_URL") or None,
            timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
        )


class LLMClient:
    """Provider-neutral OpenAI-compatible client. Works with OpenAI, vLLM, Ollama, LM Studio, enterprise gateways."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._clients: dict[str, OpenAI] = {}

    def _client(self, base_url: str | None) -> OpenAI:
        url = base_url or self.config.base_url
        if url not in self._clients:
            self._clients[url] = OpenAI(
                base_url=url,
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._clients[url]

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        json_mode: bool = False,
        system: str | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client(None).chat.completions.create(
            model=_resolve(model, self.config.chat_model, "LLM_MODEL"),
            messages=messages,
            **kwargs,
        )
        return (resp.choices[0].message.content or "").strip()

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        resp = self._client(self.config.embedding_base_url).embeddings.create(
            model=_resolve(model, self.config.embedding_model, "EMBEDDING_MODEL"),
            input=texts,
        )
        return [d.embedding for d in resp.data]

    def describe_image(
        self,
        image_path: Path,
        *,
        hint: str | None = None,
        model: str | None = None,
    ) -> str:
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        suffix = image_path.suffix.lstrip(".").lower() or "png"
        mime = f"image/{'jpeg' if suffix in ('jpg', 'jpeg') else suffix}"
        user_prompt = "Describe this figure for a RAG index. Be concise (1-3 sentences)."
        if hint:
            user_prompt += f" {hint}"
        resp = self._client(self.config.vlm_base_url).chat.completions.create(
            model=_resolve(model, self.config.vlm_model, "VLM_MODEL"),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
        )
        return (resp.choices[0].message.content or "").strip()


def _resolve(explicit: str | None, default: str | None, env_name: str) -> str:
    model = explicit or default
    if not model:
        raise ValueError(f"model not configured; set ${env_name} or pass model= explicitly")
    return model
