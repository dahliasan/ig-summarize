"""Summarize-style transcription: local whisper-cli first, then Groq → AssemblyAI → OpenAI."""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import subprocess
import sys
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


def _ig_config_json_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = (
        Path(xdg).expanduser() / "ig-summarize"
        if xdg
        else Path.home() / ".config" / "ig-summarize"
    )
    return base / "config.json"


def _whisper_model_path_from_ig_config() -> Optional[str]:
    p = _ig_config_json_path()
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    for key in ("whisper_cpp_model_path", "summarize_whisper_cpp_model_path"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            exp = Path(val).expanduser()
            if exp.is_file():
                return str(exp)
    return None


def _xdg_data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser()
    return Path.home() / ".local" / "share"


def _discover_model_search_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p)
        if key not in seen:
            seen.add(key)
            roots.append(p)

    add(_xdg_data_home() / "ig-summarize" / "models")
    add(Path.home() / ".local" / "share" / "ig-summarize" / "models")
    add(Path.home() / "whisper.cpp" / "models")
    add(Path.home() / ".cache" / "whisper")
    add(Path.home() / ".summarize" / "models")

    bin_p = _whisper_cpp_binary()
    if bin_p:
        bp = Path(bin_p).resolve()
        if "Cellar" in bp.parts:
            try:
                i = bp.parts.index("Cellar")
                if i + 2 < len(bp.parts):
                    cellar_pkg = Path(*bp.parts[: i + 3])
                    add(cellar_pkg / "share" / "whisper-cpp")
            except (ValueError, IndexError):
                pass
        add(bp.parent / "models")

    summarize_home = os.environ.get("SUMMARIZE_HOME", "").strip()
    if summarize_home:
        add(Path(summarize_home).expanduser() / "models")

    return roots


def _is_whisper_weights_file(path: Path) -> bool:
    if not path.is_file():
        return False
    n = path.name.lower()
    if n.startswith("."):
        return False
    if not (n.endswith(".bin") or n.endswith(".gguf")):
        return False
    if n.endswith(".gguf"):
        return True
    return "ggml-" in n


def _model_preference_rank(name: str) -> int:
    """Lower is better (prefer larger models when multiple are installed)."""
    n = name.lower()
    ordered = (
        "large-v3-turbo",
        "large-v3",
        "large-v2",
        "large-v1",
        "large",
        "medium",
        "small",
        "base",
        "tiny",
    )
    for i, key in enumerate(ordered):
        if key in n:
            return i
    return len(ordered)


def _discovered_whisper_models() -> list[Path]:
    found: list[Path] = []
    for root in _discover_model_search_roots():
        if not root.is_dir():
            continue
        for pattern in ("*.bin", "*.gguf"):
            for p in root.glob(pattern):
                if _is_whisper_weights_file(p):
                    found.append(p)
        try:
            for sub in root.iterdir():
                if sub.is_dir():
                    for pattern in ("*.bin", "*.gguf"):
                        for p in sub.glob(pattern):
                            if _is_whisper_weights_file(p):
                                found.append(p)
        except OSError:
            pass
    uniq: dict[str, Path] = {}
    for p in found:
        try:
            uniq[str(p.resolve())] = p
        except OSError:
            continue
    return list(uniq.values())


def _pick_best_whisper_model(candidates: list[Path]) -> Optional[Path]:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda p: (_model_preference_rank(p.name), -p.stat().st_size),
    )[0]


_DEFAULT_WHISPER_REMOTE = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
)
_DEFAULT_WHISPER_FILENAME = "ggml-tiny.en.bin"
_MIN_MODEL_BYTES = 8_000_000


def _skip_auto_whisper_download() -> bool:
    for k in (
        "IG_SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD",
        "SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD",
    ):
        v = os.environ.get(k, "").strip().lower()
        if v in ("1", "true", "yes"):
            return True
    return False


def _download_default_whisper_model(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".download")
    if tmp.is_file():
        tmp.unlink()
    print(
        f"ig-summarize: downloading default Whisper model to {dest} (~75MB, one-time)…",
        file=sys.stderr,
    )
    req = urllib.request.Request(
        _DEFAULT_WHISPER_REMOTE,
        headers={"User-Agent": "ig-summarize (https://github.com/dahliasan/ig-summarize)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            chunk = 256 * 1024
            with open(tmp, "wb") as out:
                while True:
                    block = resp.read(chunk)
                    if not block:
                        break
                    out.write(block)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        try:
            tmp.unlink()
        except OSError:
            pass
        raise TranscriptionError(f"model download HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise TranscriptionError(f"model download failed: {e}") from e

    try:
        sz = tmp.stat().st_size
    except OSError as e:
        raise TranscriptionError(f"model download incomplete: {e}") from e
    if sz < _MIN_MODEL_BYTES:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise TranscriptionError("downloaded model file too small; check network and retry")

    os.replace(tmp, dest)


def _whisper_cpp_model() -> Optional[str]:
    for k in ("SUMMARIZE_WHISPER_CPP_MODEL_PATH", "IG_WHISPER_CPP_MODEL"):
        p = os.environ.get(k, "").strip()
        if p and Path(p).expanduser().is_file():
            return str(Path(p).expanduser())
    cfg = _whisper_model_path_from_ig_config()
    if cfg:
        return cfg
    best = _pick_best_whisper_model(_discovered_whisper_models())
    if best:
        return str(best)
    if _skip_auto_whisper_download() or _disabled_local_whisper():
        return None
    if not _whisper_cpp_binary():
        return None
    dest = _xdg_data_home() / "ig-summarize" / "models" / _DEFAULT_WHISPER_FILENAME
    if dest.is_file() and dest.stat().st_size >= _MIN_MODEL_BYTES:
        return str(dest)
    try:
        _download_default_whisper_model(dest)
    except TranscriptionError:
        return None
    if dest.is_file() and dest.stat().st_size >= _MIN_MODEL_BYTES:
        return str(dest)
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
        "  Local: install whisper-cli on PATH; ig-summarize looks for weights under XDG data dirs "
        "(e.g. ~/.local/share/ig-summarize/models), ~/.summarize/models, ~/whisper.cpp/models, "
        "or config whisper_cpp_model_path; otherwise downloads ggml-tiny.en.bin once unless "
        "IG_SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD=1. Optional override: SUMMARIZE_WHISPER_CPP_MODEL_PATH.",
        "  Cloud (any one): GROQ_API_KEY, ASSEMBLYAI_API_KEY, or OPENAI_API_KEY (optional OPENAI_WHISPER_BASE_URL).",
        "  Disable local: SUMMARIZE_DISABLE_LOCAL_WHISPER_CPP=1",
        "Attempts:",
        *[f"  - {line}" for line in errors],
    ]
    raise TranscriptionError("\n".join(msg_lines))
