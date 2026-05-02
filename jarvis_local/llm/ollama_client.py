from __future__ import annotations

import logging
from typing import Any

import requests


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        model: str,
        chat_url: str = "http://localhost:11434/api/chat",
        tags_url: str = "http://localhost:11434/api/tags",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.chat_url = chat_url
        self.tags_url = tags_url
        self.timeout_seconds = timeout_seconds
        self.log = logging.getLogger("jarvis.llm.ollama")

    def list_models(self) -> list[str]:
        try:
            response = requests.get(self.tags_url, timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(
                "Ollama is not running. Start Ollama, then run: ollama run qwen2.5:3b"
            ) from exc

        payload = response.json()
        return [model.get("name", "") for model in payload.get("models", [])]

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096,
            },
        }
        try:
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise OllamaError(
                "Could not reach Ollama at localhost:11434. Start Ollama and try again."
            ) from exc

        if response.status_code == 404:
            raise OllamaError(
                f"Ollama model '{self.model}' was not found. Run: ollama run {self.model}"
            )
        if not response.ok:
            detail = self._error_detail(response)
            raise OllamaError(f"Ollama request failed: {detail}")

        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise OllamaError("Ollama returned an empty response.")
        self.log.info("Assistant raw response: %s", content)
        return content.strip()

    def _error_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
            return str(data.get("error") or data)
        except ValueError:
            return response.text[:500]
