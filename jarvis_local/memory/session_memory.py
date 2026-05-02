from __future__ import annotations

import json
import logging
from pathlib import Path


class SessionMemory:
    def __init__(self, path: Path, max_messages: int = 10) -> None:
        self.path = path
        self.max_messages = max_messages
        self.messages: list[dict[str, str]] = []
        self.log = logging.getLogger("jarvis.memory")

    def load(self) -> None:
        if not self.path.exists():
            self.messages = []
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            self.messages = [
                {"role": str(item["role"]), "content": str(item["content"])}
                for item in messages
                if item.get("role") in {"user", "assistant"}
            ][-self.max_messages :]
            self.log.info("Loaded %d memory messages", len(self.messages))
        except Exception as exc:
            self.log.warning("Could not load memory file: %s", exc)
            self.messages = []

    def add(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported memory role: {role}")
        self.messages.append({"role": role, "content": content})
        self.messages = self.messages[-self.max_messages :]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump({"messages": self.messages}, f, indent=2)
        except Exception as exc:
            self.log.warning("Could not save memory file: %s", exc)
