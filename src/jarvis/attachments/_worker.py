"""Fixed isolated parser program. Input never becomes code, path, URL or command."""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import warnings


def resource_limits() -> None:
    """Fail closed if OS cannot impose 512 MiB worker allocation ceiling."""
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1_024 * 1_024, 512 * 1_024 * 1_024))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        return
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("minimum", ctypes.c_size_t),
            ("maximum", ctypes.c_size_t),
            ("processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", ctypes.c_ulonglong * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100 | 0x8  # PROCESS_MEMORY | ACTIVE_PROCESS; no child processes.
    limits.basic.processes = 1
    limits.process_memory = 512 * 1_024 * 1_024
    if (
        not job
        or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())
    ):
        raise ValueError("worker resource policy unavailable")
    # Keep job handle open for worker lifetime; OS closes it at process exit.


def extract(body: bytes, media_type: str) -> dict[str, object]:
    if media_type == "text/plain":
        text = body.decode("utf-8-sig", errors="strict")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise ValueError("binary text")
        if len(text) > 100_000:
            raise ValueError("text limit")
        text = text.strip()
        if not text:
            raise ValueError("empty text")
        return {"text": text}
    if media_type == "application/pdf":
        if not body.startswith(b"%PDF-"):
            raise ValueError("PDF signature")
        from pypdf import PdfReader, filters

        for name in (
            "JBIG2_MAX_OUTPUT_LENGTH",
            "LZW_MAX_OUTPUT_LENGTH",
            "RUN_LENGTH_MAX_OUTPUT_LENGTH",
            "ZLIB_MAX_OUTPUT_LENGTH",
            "MAX_DECLARED_STREAM_LENGTH",
            "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
            "IMAGE_MAX_BUFFER_SIZE",
        ):
            if hasattr(filters, name):
                setattr(filters, name, 8 * 1_024 * 1_024)
        if hasattr(filters, "JBIG2DEC_BINARY"):
            filters.JBIG2DEC_BINARY = None
        reader = PdfReader(io.BytesIO(body), strict=True)
        if reader.is_encrypted or len(reader.pages) > 50:
            raise ValueError("PDF policy")
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            total += len(text)
            if total > 100_000:
                raise ValueError("PDF text limit")
            parts.append(text)
        result = "\n".join(parts).strip()
        if not result:
            raise ValueError("no PDF text; scanned PDF requires separate OCR")
        return {"text": result}
    if media_type in {"image/png", "image/jpeg"}:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 8_000_000
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        expected = "PNG" if media_type == "image/png" else "JPEG"
        with Image.open(io.BytesIO(body), formats=[expected]) as image:
            if image.format != expected or getattr(image, "n_frames", 1) != 1:
                raise ValueError("image policy")
            if image.width * image.height > 8_000_000:
                raise ValueError("image pixels")
            image.load()
            normalized = image.convert("RGB")
            normalized.thumbnail((2_048, 2_048))
            # Newly encoded pixels omit EXIF, comments and other source metadata.
            output = io.BytesIO()
            normalized.save(output, format="JPEG", quality=85)
            value = output.getvalue()
            if len(value) > 2 * 1_024 * 1_024:
                raise ValueError("image bytes")
            return {
                "image_base64": base64.b64encode(value).decode("ascii"),
                "width": normalized.width,
                "height": normalized.height,
            }
    raise ValueError("unsupported type")


def main() -> int:
    try:
        resource_limits()
        raw = sys.stdin.buffer.read(7_100_000 + 1)
        if len(raw) > 7_100_000:
            raise ValueError("input limit")
        payload = json.loads(raw)
        body = base64.b64decode(payload["body_base64"], validate=True)
        if not body or len(body) > 5 * 1_024 * 1_024:
            raise ValueError("byte limit")
        result = extract(body, payload["media_type"])
        # Remove non-whitespace control codes from extracted PDF text.
        if "text" in result:
            result["text"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(result["text"]))
        sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except ImportError:
        sys.stdout.write('{"error":"dependency_unavailable"}')
        return 1
    except Exception:
        sys.stdout.write('{"error":"processing_rejected"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
