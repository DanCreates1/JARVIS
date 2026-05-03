from __future__ import annotations

import logging
import os
import site
from pathlib import Path
from typing import Any


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
        self.model: Any | None = None
        self.active_device = ""
        self.active_compute_type = ""
        self._dll_directory_handles: list[Any] = []
        self.log = logging.getLogger("jarvis.audio.stt")

    def transcribe(self, audio_path: Path) -> str:
        model = self._load_model()
        try:
            return self._transcribe_with_model(model, audio_path)
        except Exception as exc:
            if self.active_device == "cuda" and self._is_cuda_runtime_error(exc):
                self.log.warning(
                    "CUDA Whisper failed during transcription, falling back to CPU: %s",
                    exc,
                )
                self.model = None
                self.device = "cpu"
                self.compute_type = "int8"
                try:
                    return self._transcribe_with_model(self._load_model(), audio_path)
                except Exception as retry_exc:
                    raise SpeechToTextError(
                        f"Whisper CPU fallback failed: {retry_exc}"
                    ) from retry_exc
            raise SpeechToTextError(f"Whisper transcription failed: {exc}") from exc

    def _transcribe_with_model(self, model: Any, audio_path: Path) -> str:
        segments, _info = model.transcribe(
            str(audio_path),
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        self.log.info("Transcript: %s", text)
        return text

    def _load_model(self):
        if self.model is not None:
            return self.model
        self._add_cuda_dll_dirs()
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
                self.active_device = device
                self.active_compute_type = compute_type
                self.log.info("Whisper model loaded on %s (%s)", device, compute_type)
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

    def _is_cuda_runtime_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "cuda",
            "cublas",
            "cudnn",
            "ctranslate2",
            "dll",
            "out of memory",
        )
        return any(marker in message for marker in markers)

    def _add_cuda_dll_dirs(self) -> None:
        if os.name != "nt" or not hasattr(os, "add_dll_directory"):
            return
        candidates: list[Path] = []
        for base in site.getsitepackages():
            root = Path(base) / "nvidia"
            candidates.extend(
                [
                    root / "cublas" / "bin",
                    root / "cudnn" / "bin",
                    root / "cuda_nvrtc" / "bin",
                ]
            )
        for path in candidates:
            if not path.exists():
                continue
            text_path = str(path)
            if text_path not in os.environ.get("PATH", ""):
                os.environ["PATH"] = text_path + os.pathsep + os.environ.get("PATH", "")
            try:
                handle = os.add_dll_directory(text_path)
                self._dll_directory_handles.append(handle)
                self.log.info("Added CUDA DLL directory: %s", text_path)
            except OSError as exc:
                self.log.debug("Could not add CUDA DLL directory %s: %s", text_path, exc)
