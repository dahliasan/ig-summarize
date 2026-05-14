"""Summarize-style transcription: local whisper-cli first, then Groq → AssemblyAI → OpenAI."""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class TranscriptionError(Exception):
    pass


def _disabled_local_whisper() -> bool:
    for k in ("SUMMARIZE_DISABLE_LOCAL_WHISPER_CPP", "IG_DISABLE_LOCAL_WHISPER_CPP"):
        v = os.environ.get(k, "").strip().lower()
        if v in ("1", "true", "yes"):
            return True
    return False


def _whisper_cpp_binary() -> Optional[str]:
    for k in ("SUMMARIZE_WHISPER_CPP_BINARY", "IG_WHISPER_CPP_BIN"):
        p = os.environ.get(k, "").strip()
        if not p:
            continue
        exp = Path(p).expanduser()
        if exp.is_file():
            return str(exp)
        found = shutil.which(p)
        if found:
            return found
    return shutil.which("whisper-cli") or shutil.which("whisper-cpp")


def _whisper_cpp_model() -> Optional[str]:
    for k in ("SUMMARIZE_WHISPER_CPP_MODEL_PATH", "IG_WHISPER_CPP_MODEL"):
        p = os.environ.get(k, "").strip()
        if p and Path(p).expanduser().is_file():
            return str(Path(p).expanduser())
    return None


def _multipart_form(
    fields: Dict[str, str],
    file_field: str,
    file_path: Path,
    content_type: str,
) -> Tuple[bytes, str]:
    boundary = "----igSummarize" + "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(24)
    )
    crlf = "\r\n"
    chunks: list[bytes] = []

    def add(data: str) -> None:
        chunks.append(data.encode("utf-8"))

    for name, value in fields.items():
        add(f"--{boundary}{crlf}")
        add(f'Content-Disposition: form-data; name="{name}"{crlf}{crlf}')
        add(value + crlf)

    fname = file_path.name
    data = file_path.read_bytes()
    add(f"--{boundary}{crlf}")
    add(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{fname}"{crlf}'
        f"Content-Type: {content_type}{crlf}{crlf}"
    )
    chunks.append(data)
    add(crlf)
    add(f"--{boundary}--{crlf}")

    body = b"".join(chunks)
    ctype = f"multipart/form-data; boundary={boundary}"
    return body, ctype


def _http_json(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    timeout: int = 120,
) -> Any:
    h = dict(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise TranscriptionError(f"HTTP {e.code} from {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise TranscriptionError(f"Request failed for {url}: {e}") from e
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise TranscriptionError(f"Invalid JSON from {url}: {raw[:400]}") from e


def transcribe_whisper_cpp(audio_path: Path, work_dir: Path) -> str:
    if _disabled_local_whisper():
        raise TranscriptionError("local whisper disabled")
    binary = _whisper_cpp_binary()
    model = _whisper_cpp_model()
    if not binary or not model:
        raise TranscriptionError("whisper-cli or model path missing")
    out_base = work_dir / "whisper-out"
    cmd = [
        binary,
        "-m",
        model,
        "-f",
        str(audio_path),
        "-otxt",
        "-of",
        str(out_base),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise TranscriptionError(
            f"whisper-cli failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    txt = Path(str(out_base) + ".txt")
    if not txt.is_file():
        raise TranscriptionError(f"whisper-cli did not write expected file: {txt}")
    return txt.read_text(encoding="utf-8", errors="replace").strip()


def transcribe_groq(audio_path: Path) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise TranscriptionError("GROQ_API_KEY not set")
    model = os.getenv("IG_GROQ_TRANSCRIBE_MODEL", "whisper-large-v3").strip()
    body, ctype = _multipart_form(
        {"model": model},
        "file",
        audio_path,
        "application/octet-stream",
    )
    payload = _http_json(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype},
        data=body,
        timeout=600,
    )
    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        return payload["text"].strip()
    raise TranscriptionError(f"Unexpected Groq response: {payload!r}")


def transcribe_openai(audio_path: Path) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise TranscriptionError("OPENAI_API_KEY not set")
    base = os.getenv("OPENAI_WHISPER_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("IG_OPENAI_TRANSCRIBE_MODEL", "whisper-1").strip()
    body, ctype = _multipart_form(
        {"model": model},
        "file",
        audio_path,
        "application/octet-stream",
    )
    payload = _http_json(
        f"{base}/audio/transcriptions",
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype},
        data=body,
        timeout=600,
    )
    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        return payload["text"].strip()
    raise TranscriptionError(f"Unexpected OpenAI transcription response: {payload!r}")


def transcribe_assemblyai(audio_path: Path) -> str:
    key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    if not key:
        raise TranscriptionError("ASSEMBLYAI_API_KEY not set")
    upload_url = "https://api.assemblyai.com/v2/upload"
    req = urllib.request.Request(
        upload_url,
        data=audio_path.read_bytes(),
        headers={
            "authorization": key,
            "content-type": "application/octet-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            up = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise TranscriptionError(f"AssemblyAI upload HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise TranscriptionError(f"AssemblyAI upload failed: {e}") from e
    audio_url = up.get("upload_url") if isinstance(up, dict) else None
    if not isinstance(audio_url, str):
        raise TranscriptionError(f"AssemblyAI upload unexpected: {up!r}")

    create = _http_json(
        "https://api.assemblyai.com/v2/transcript",
        method="POST",
        headers={
            "authorization": key,
            "content-type": "application/json",
        },
        data=json.dumps({"audio_url": audio_url}).encode("utf-8"),
        timeout=120,
    )
    tid = create.get("id") if isinstance(create, dict) else None
    if not isinstance(tid, str):
        raise TranscriptionError(f"AssemblyAI create unexpected: {create!r}")

    poll_url = f"https://api.assemblyai.com/v2/transcript/{tid}"
    for _ in range(180):
        doc = _http_json(
            poll_url,
            headers={"authorization": key},
            timeout=60,
        )
        if not isinstance(doc, dict):
            raise TranscriptionError(f"AssemblyAI poll unexpected: {doc!r}")
        status = doc.get("status")
        if status == "completed":
            text = doc.get("text")
            if isinstance(text, str):
                return text.strip()
            raise TranscriptionError(f"AssemblyAI completed without text: {doc!r}")
        if status == "error":
            err = doc.get("error", doc)
            raise TranscriptionError(f"AssemblyAI error: {err}")
        time.sleep(2)
    raise TranscriptionError("AssemblyAI transcription timed out")


def transcribe_auto(audio_path: Path, work_dir: Path) -> Tuple[str, str]:
    """
    Match steipete/summarize README ordering for Whisper fallback:
    local whisper.cpp → Groq → AssemblyAI → OpenAI.
    Returns (transcript, provider_label).
    """
    steps: list[tuple[str, Any]] = [
        ("whisper-cli (local)", lambda: transcribe_whisper_cpp(audio_path, work_dir)),
        ("groq", lambda: transcribe_groq(audio_path)),
        ("assemblyai", lambda: transcribe_assemblyai(audio_path)),
        ("openai", lambda: transcribe_openai(audio_path)),
    ]
    errors: list[str] = []
    for label, fn in steps:
        try:
            text = fn()
            if text:
                return text, label
            errors.append(f"{label}: empty transcript")
        except TranscriptionError as e:
            errors.append(f"{label}: {e}")
        except OSError as e:
            errors.append(f"{label}: {e}")
    msg_lines = [
        "No transcription provider succeeded. Summarize-style setup:",
        "  Local: install whisper-cli + set SUMMARIZE_WHISPER_CPP_MODEL_PATH (and optionally SUMMARIZE_WHISPER_CPP_BINARY).",
        "  Cloud (any one): GROQ_API_KEY, ASSEMBLYAI_API_KEY, or OPENAI_API_KEY (optional OPENAI_WHISPER_BASE_URL).",
        "  Disable local: SUMMARIZE_DISABLE_LOCAL_WHISPER_CPP=1",
        "Attempts:",
        *[f"  - {line}" for line in errors],
    ]
    raise TranscriptionError("\n".join(msg_lines))
