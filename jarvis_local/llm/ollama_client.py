from __future__ import annotations

import logging
import time
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
        options: dict[str, Any] | None = None,
        keep_alive: str | int | None = None,
    ) -> None:
        self.model = model
        self.chat_url = chat_url
        self.tags_url = tags_url
        self.timeout_seconds = timeout_seconds
        self.options = options or {}
        self.keep_alive = keep_alive
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
            "options": self.options,
        }
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        try:
            started = time.perf_counter()
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
        elapsed = time.perf_counter() - started
        self.log.info("Assistant raw response in %.2fs: %s", elapsed, content)
        return content.strip()

    def warmup(self) -> None:
        self.log.info("Warming up Ollama model %s", self.model)
        warmup_options = dict(self.options)
        warmup_options["num_predict"] = 8
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "stream": False,
            "options": warmup_options,
        }
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        try:
            started = time.perf_counter()
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            self.log.info("Ollama warmup completed in %.2fs", time.perf_counter() - started)
        except requests.RequestException as exc:
            raise OllamaError("Ollama warmup failed. Start Ollama and try again.") from exc

    def _error_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
            return str(data.get("error") or data)
        except ValueError:
            return response.text[:500]
