from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path


class TextToSpeech:
    def __init__(
        self,
        piper_exe: str,
        model_path: Path,
        config_path: Path | None = None,
        voice_name: str = "en_US-lessac-medium",
    ) -> None:
        self.piper_exe = piper_exe
        self.model_path = model_path
        self.config_path = config_path
        self.voice_name = voice_name
        self.log = logging.getLogger("jarvis.audio.tts")
        self.available = self._is_available()

    def speak(self, text: str) -> None:
        text = self._clean_text(text)
        if not text:
            return
        if not self.available:
            self.log.warning("TTS unavailable; skipped speech: %s", text)
            return

        wav_path = Path(tempfile.gettempdir()) / "jarvis_local_tts.wav"
        command = [
            self.piper_exe,
            "--model",
            str(self.model_path),
            "--output_file",
            str(wav_path),
        ]
        if self.config_path and self.config_path.exists():
            command.extend(["--config", str(self.config_path)])

        try:
            subprocess.run(
                command,
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                creationflags=self._creation_flags(),
            )
            self._play_wav(wav_path)
        except Exception as exc:
            self.log.error("Piper TTS failed: %s", exc)
            self.available = False
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _is_available(self) -> bool:
        if not self.model_path.exists():
            self.log.warning(
                "Piper voice model not found: %s. Download %s.onnx to voices/ or update config.",
                self.model_path,
                self.voice_name,
            )
            return False
        return True

    def _play_wav(self, wav_path: Path) -> None:
        if os.name == "nt":
            import winsound

            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
            return

        try:
            import sounddevice as sd

            with wave.open(str(wav_path), "rb") as wav:
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
            import numpy as np

            audio = np.frombuffer(frames, dtype=np.int16)
            sd.play(audio, samplerate=sample_rate)
            sd.wait()
        except Exception as exc:
            self.log.error("Audio playback failed: %s", exc)

    def _clean_text(self, text: str) -> str:
        return " ".join(text.replace("\n", " ").split())

    def _creation_flags(self) -> int:
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0
