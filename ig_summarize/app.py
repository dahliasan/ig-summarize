#!/usr/bin/env python3
"""ig-summarize: download an Instagram post/reel, transcribe audio, optionally summarize via OpenRouter."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

INSTAGRAM_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:instagram\.com|instagr\.am)/(?:p|reel|reels|tv)/([^/?#]+)",
    re.IGNORECASE,
)

DEFAULT_OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_OPENROUTER_REFERER = "https://github.com/dahliasan/ig-summarize"
DEFAULT_OPENROUTER_TITLE = "ig-summarize"


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "ig-summarize"
    return Path.home() / ".config" / "ig-summarize"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_user_config() -> Dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def resolve_openrouter_api_key() -> Optional[str]:
    env = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env:
        return env
    key = str(load_user_config().get("openrouter_api_key", "")).strip()
    return key or None


def normalize_openrouter_model(model: str) -> str:
    m = model.strip()
    if m.lower() == "free":
        return "openrouter/free"
    return m


def default_openrouter_model() -> str:
    env = os.getenv("OPENROUTER_MODEL", "").strip()
    if env:
        return env
    raw = load_user_config().get("openrouter_model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return DEFAULT_OPENROUTER_MODEL


def resolved_openrouter_model(cli_value: Optional[str]) -> str:
    if cli_value is not None and str(cli_value).strip() != "":
        return normalize_openrouter_model(str(cli_value))
    return normalize_openrouter_model(default_openrouter_model())


def fetch_openrouter_free_model_ids() -> list[str]:
    req = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={"User-Agent": "ig-summarize (https://github.com/dahliasan/ig-summarize)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        die(f"OpenRouter models HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"OpenRouter models request failed: {e}")

    out: list[str] = []
    for m in payload.get("data") or []:
        mid = m.get("id")
        if not isinstance(mid, str) or not mid:
            continue
        pricing = m.get("pricing") or {}
        p, c = pricing.get("prompt"), pricing.get("completion")
        if p == "0" and c == "0":
            out.append(mid)
        elif mid.endswith(":free"):
            out.append(mid)
    return sorted(set(out))


def write_user_config(updates: Dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged: Dict[str, Any] = dict(load_user_config())
    merged.update(updates)
    tmp = path.with_suffix(".json.tmp")
    data = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def read_openrouter_key_for_save(from_env: bool) -> str:
    if from_env:
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            die("OPENROUTER_API_KEY is empty or unset (used with --from-env).")
        return key
    if not sys.stdin.isatty():
        key = sys.stdin.read().strip()
        if key:
            return key
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    key = getpass.getpass("OpenRouter API key: ").strip()
    if not key:
        die("No API key provided.")
    return key


def run_config_command(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="ig-summarize config")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser(
        "save-openrouter",
        help="Write OPENROUTER_API_KEY to ~/.config/ig-summarize/config.json (mode 0600).",
    )
    p_save.add_argument(
        "--from-env",
        action="store_true",
        help="Read the key from OPENROUTER_API_KEY instead of stdin / prompt.",
    )

    p_path = sub.add_parser("path", help="Print the config file path and exit.")

    p_refresh = sub.add_parser(
        "refresh-free",
        help=(
            "Fetch OpenRouter models with $0 listed pricing and cache their ids in config "
            "(similar to `summarize refresh-free`; list-only, no latency probes)."
        ),
    )

    p_set = sub.add_parser(
        "set-model",
        help="Save default OpenRouter model id in config (overridden by OPENROUTER_MODEL / --openrouter-model).",
    )
    p_set.add_argument(
        "model",
        help="Model id (e.g. openrouter/free, google/gemini-2.0-flash-001:free). Shorthand: free → openrouter/free.",
    )

    p_list = sub.add_parser(
        "list-free",
        help="Print cached free model ids from the last refresh-free (first 60 lines).",
    )

    args = p.parse_args(argv)
    if args.cmd == "path":
        print(config_path())
        return
    if args.cmd == "save-openrouter":
        key = read_openrouter_key_for_save(from_env=args.from_env)
        out = write_user_config({"openrouter_api_key": key})
        print(f"Saved OpenRouter API key to {out} (permissions 0600).")
        return
    if args.cmd == "refresh-free":
        ids = fetch_openrouter_free_model_ids()
        write_user_config(
            {
                "openrouter_free_model_ids": ids,
                "openrouter_free_models_refreshed_at": int(time.time()),
            }
        )
        print(f"Cached {len(ids)} OpenRouter models with listed $0 input/output pricing.")
        print("Sample (up to 12):")
        for mid in ids[:12]:
            print(f"  {mid}")
        print("Use `ig-summarize config list-free` for more, or `config set-model <id>` to pin a default.")
        return
    if args.cmd == "set-model":
        mid = normalize_openrouter_model(args.model)
        write_user_config({"openrouter_model": mid})
        print(f"Saved default OpenRouter model to config: {mid}")
        return
    if args.cmd == "list-free":
        raw = load_user_config().get("openrouter_free_model_ids")
        if not isinstance(raw, list) or not raw:
            die("No cached list. Run `ig-summarize config refresh-free` first.")
        ts = load_user_config().get("openrouter_free_models_refreshed_at")
        if ts is not None:
            print(f"# refreshed_at: {ts}")
        for mid in raw[:60]:
            if isinstance(mid, str):
                print(mid)
        if len(raw) > 60:
            print(f"# … {len(raw) - 60} more (see {config_path()})")
        return
    die(f"Unknown config command: {args.cmd}")


def die(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def extract_shortcode(target: str) -> str:
    t = target.strip()
    m = INSTAGRAM_URL_RE.search(t)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", t):
        return t
    die(
        "Could not parse Instagram shortcode. Pass a full /p/, /reel/, or /tv/ URL, "
        "or a bare shortcode."
    )
    return ""


def which_or_env(binary: str, env_var: str) -> str:
    override = os.environ.get(env_var, "").strip()
    if override:
        p = Path(override)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        die(f"{env_var} is set but not an executable file: {override}")
    found = shutil.which(binary)
    if not found:
        die(f"`{binary}` not found on PATH. Install it or set {env_var}.")
    return found


def transcribe_cli_path() -> Path:
    explicit = os.environ.get("TRANSCRIBE_CLI", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
        die(f"TRANSCRIBE_CLI is not a file: {explicit}")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    candidate = codex_home / "skills" / "transcribe" / "scripts" / "transcribe_diarize.py"
    if candidate.is_file():
        return candidate
    die(
        "Transcribe helper not found. Install the transcribe skill under "
        f"{codex_home}/skills/transcribe/scripts/transcribe_diarize.py or set TRANSCRIBE_CLI."
    )
    return candidate


def find_largest_mp4(root: Path) -> Optional[Path]:
    best: Optional[Path] = None
    best_size = -1
    for path in root.rglob("*.mp4"):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > best_size:
            best = path
            best_size = size
    return best


def run_instaloader(instaloader: str, shortcode: str, cwd: Path, extra_args: list[str]) -> None:
    cmd = [
        instaloader,
        "-q",
        "--no-metadata-json",
        "--no-compress-json",
        *extra_args,
        "--",
        f"-{shortcode}",
    ]
    subprocess.run(cmd, cwd=str(cwd), check=True)


def extract_audio_ffmpeg(ffmpeg: str, video: Path, audio_out: Path) -> None:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(audio_out),
    ]
    subprocess.run(cmd, check=True)


def run_transcribe(python: str, transcribe_py: Path, audio: Path) -> str:
    cmd = [
        python,
        str(transcribe_py),
        str(audio),
        "--stdout",
    ]
    proc = subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.stdout


def openrouter_summarize(
    api_key: str,
    model: str,
    transcript: str,
    referer: str,
    title: str,
) -> str:
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You summarize transcripts from social video. Be faithful to the text; "
                    "do not invent facts. Use short paragraphs or bullets."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Summarize this Instagram video transcript for a busy reader.\n\n"
                    f"{transcript}"
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 900,
    }
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-OpenRouter-Title": title,
    }
    req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        die(f"OpenRouter HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"OpenRouter request failed: {e}")

    try:
        choice = payload["choices"][0]
        msg = choice.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except (KeyError, IndexError, TypeError):
        pass
    die(f"Unexpected OpenRouter response: {json.dumps(payload)[:800]}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ig-summarize",
        description=(
            "Download Instagram post/reel media with Instaloader, transcribe audio via "
            "the transcribe_diarize OpenAI helper, and optionally summarize with OpenRouter."
        ),
        epilog=(
            "Config: `%(prog)s config save-openrouter`, `config refresh-free`, `config set-model`, "
            "`config list-free`, `config path`. "
            "Env OPENROUTER_API_KEY overrides saved key; OPENROUTER_MODEL overrides saved default model."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "target",
        help="Instagram URL (/p/, /reel/, /tv/) or bare post shortcode",
    )
    p.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Also call OpenRouter to summarize the transcript. Uses OPENROUTER_API_KEY "
            "if set, else openrouter_api_key from ~/.config/ig-summarize/config.json "
            "(see: ig-summarize config save-openrouter)."
        ),
    )
    p.add_argument(
        "--openrouter-model",
        default=None,
        metavar="MODEL",
        help=(
            "OpenRouter model id for --summary. Shorthand: free → openrouter/free. "
            "Default order: this flag, then $OPENROUTER_MODEL, then openrouter_model in "
            f"{config_path()}, else {DEFAULT_OPENROUTER_MODEL}."
        ),
    )
    p.add_argument(
        "--openrouter-referer",
        default=os.environ.get("OPENROUTER_HTTP_REFERER", DEFAULT_OPENROUTER_REFERER),
        help="HTTP-Referer header for OpenRouter (optional attribution).",
    )
    p.add_argument(
        "--openrouter-title",
        default=os.environ.get("OPENROUTER_APP_TITLE", DEFAULT_OPENROUTER_TITLE),
        help="X-OpenRouter-Title header for OpenRouter.",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for transcript (and summary) files. Default: temp dir unless --keep.",
    )
    p.add_argument(
        "--keep",
        action="store_true",
        help="Keep downloaded media and work directory (implies stable --out-dir default).",
    )
    p.add_argument(
        "--instaloader-arg",
        action="append",
        default=[],
        help="Extra args passed to instaloader before the `--` target (repeatable). "
        "Example: --instaloader-arg --login --instaloader-arg YOUR_USER",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        die("OPENAI_API_KEY is not set (required for transcription).")

    shortcode = extract_shortcode(args.target)
    instaloader = which_or_env("instaloader", "INSTALOADER_BIN")
    ffmpeg = which_or_env("ffmpeg", "FFMPEG_BIN")
    python = which_or_env("python3", "PYTHON_BIN")
    transcribe_py = transcribe_cli_path()

    staging_ephemeral = False
    if args.out_dir:
        staging = args.out_dir.expanduser().resolve()
        staging.mkdir(parents=True, exist_ok=True)
        artifact_dir = staging
    elif args.keep:
        staging = (Path.cwd() / f"ig-summarize-{shortcode}").resolve()
        staging.mkdir(parents=True, exist_ok=True)
        artifact_dir = staging
    else:
        staging = Path(tempfile.mkdtemp(prefix=f"ig-sum-{shortcode}-"))
        staging_ephemeral = True
        artifact_dir = Path.cwd()

    download_dir = staging / "download"
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        run_instaloader(instaloader, shortcode, download_dir, args.instaloader_arg)
    except subprocess.CalledProcessError:
        die(
            "Instaloader failed. For private posts use session login "
            "(see Instaloader docs: --login, --load-cookies, or pass "
            "`--instaloader-arg ...`)."
        )

    video = find_largest_mp4(download_dir)
    if not video:
        die("No .mp4 found after download. This post may be image-only or blocked.")

    audio = staging / f"{shortcode}.m4a"
    extract_audio_ffmpeg(ffmpeg, video, audio)

    transcript_text = run_transcribe(python, transcribe_py, audio)
    transcript_path = artifact_dir / f"{shortcode}.transcript.txt"
    transcript_path.write_text(transcript_text, encoding="utf-8")
    print(f"Wrote transcript: {transcript_path}")

    if args.summary:
        key = resolve_openrouter_api_key()
        if not key:
            die(
                "No OpenRouter API key found. Set OPENROUTER_API_KEY, or run "
                "`ig-summarize config save-openrouter` (see --help)."
            )
        summary = openrouter_summarize(
            api_key=key,
            model=resolved_openrouter_model(args.openrouter_model),
            transcript=transcript_text,
            referer=args.openrouter_referer,
            title=args.openrouter_title,
        )
        summary_path = artifact_dir / f"{shortcode}.summary.txt"
        summary_path.write_text(summary, encoding="utf-8")
        print(f"Wrote summary: {summary_path}")
        print("\n--- Summary ---\n")
        print(summary)

    if staging_ephemeral:
        shutil.rmtree(staging, ignore_errors=True)
        warn(
            f"Removed temp staging dir {staging}; transcript/summary were written under "
            f"{artifact_dir}."
        )


def entrypoint() -> None:
    rest = sys.argv[1:]
    if rest and rest[0] == "config":
        run_config_command(rest[1:])
    else:
        main()
