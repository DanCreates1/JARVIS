from __future__ import annotations

import logging
from pathlib import Path


class SpeechToTextError(RuntimeError):
    pass


class SpeechToText:
    def __init__(
        self,
        model_name: str = "base.en",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.log = logging.getLogger("jarvis.audio.stt")

    def transcribe(self, audio_path: Path) -> str:
        model = self._load_model()
        try:
            segments, _info = model.transcribe(
                str(audio_path),
                language="en",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            self.log.info("Transcript: %s", text)
            return text
        except Exception as exc:
            raise SpeechToTextError(f"Whisper transcription failed: {exc}") from exc

    def _load_model(self):
        if self.model is not None:
            return self.model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise SpeechToTextError(
                "faster-whisper is not installed. Run: pip install -r requirements.txt"
            ) from exc

        load_attempts = self._load_attempts()
        last_error: Exception | None = None
        for device, compute_type in load_attempts:
            try:
                self.log.info(
                    "Loading Whisper model %s on %s (%s)",
                    self.model_name,
                    device,
                    compute_type,
                )
                self.model = WhisperModel(
                    self.model_name,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=4,
                )
                self.log.info("Whisper model loaded on %s", device)
                return self.model
            except Exception as exc:
                last_error = exc
                self.log.warning(
                    "Could not load Whisper on %s (%s): %s",
                    device,
                    compute_type,
                    exc,
                )
        raise SpeechToTextError(f"Could not load Whisper model: {last_error}")

    def _load_attempts(self) -> list[tuple[str, str]]:
        if self.device != "auto":
            return [(self.device, self._compute_type_for(self.device))]
        return [
            ("cuda", "float16"),
            ("cpu", "int8"),
        ]

    def _compute_type_for(self, device: str) -> str:
        if self.compute_type != "auto":
            return self.compute_type
        return "float16" if device == "cuda" else "int8"
