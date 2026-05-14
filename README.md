# ig-summarize

Turn an **Instagram post or reel URL** into a **transcript** (speech-to-text) and, optionally, a **short summary** via [OpenRouter](https://openrouter.ai/). No Python dependencies beyond the standard library; bring your own [Instaloader](https://instaloader.github.io/), [ffmpeg](https://ffmpeg.org/), and OpenAI-compatible transcription helper.

## Install

```bash
pipx install instaloader   # recommended on macOS (PEP 668)
# brew install ffmpeg
```

Clone this repo and point `IG_SUMMARIZE_CLI` at the script (or call it by path).

You also need the Codex **transcribe** helper `transcribe_diarize.py` (typically `~/.codex/skills/transcribe/scripts/transcribe_diarize.py`) or set `TRANSCRIBE_CLI` to that file.

## Usage

```bash
export OPENAI_API_KEY="…"   # required for transcription
export IG_SUMMARIZE_CLI="$PWD/scripts/ig_summarize.py"

python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/"

# Keep Instaloader output under ./ig-summarize-<shortcode>/
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --keep

# Pin all artifacts under one directory
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --out-dir ./out

# Summary (uses OPENROUTER_API_KEY or ~/.config/ig-summarize/config.json)
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --summary
```

## OpenRouter API key (config file)

Keys are stored under **`~/.config/ig-summarize/config.json`** (or `$XDG_CONFIG_HOME/ig-summarize/config.json`). The file is written with mode **`0600`**. **`OPENROUTER_API_KEY` in the environment always overrides** the file when set.

```bash
# Save key from your environment (good for one-liner setup)
export OPENROUTER_API_KEY="sk-or-…"
python3 "$IG_SUMMARIZE_CLI" config save-openrouter --from-env

# Or paste at a prompt (stdin stays empty)
python3 "$IG_SUMMARIZE_CLI" config save-openrouter

# Or pipe (avoid shell history)
python3 "$IG_SUMMARIZE_CLI" config save-openrouter < /path/to/keyfile

# Show resolved config path
python3 "$IG_SUMMARIZE_CLI" config path
```

After saving, you can run **`--summary`** without exporting `OPENROUTER_API_KEY` each session.

By default, without `--keep` or `--out-dir`, media is downloaded to a temp folder that is deleted after success; `SHORTCODE.transcript.txt` is written in the **current directory**.

## How it works

1. Parse the **shortcode** from `/p/`, `/reel/`, `/reels/`, or `/tv/` URLs (or pass the shortcode alone).
2. Run **Instaloader**: `instaloader -q … -- -<shortcode>` (see Instaloader docs).
3. Take the **largest `.mp4`** (handles carousels).
4. **ffmpeg** extracts mono AAC for the transcription API.
5. **`transcribe_diarize.py … --stdout`** produces the transcript.
6. With **`--summary`**, resolve OpenRouter key from **`OPENROUTER_API_KEY`** (if set) else **`openrouter_api_key`** in **`~/.config/ig-summarize/config.json`**, then call OpenRouter **`/api/v1/chat/completions`** (default model **`openrouter/free`**).

## Environment

| Variable | Role |
|----------|------|
| `OPENAI_API_KEY` | Required for transcription. |
| `OPENROUTER_API_KEY` | Optional if key is in `~/.config/ig-summarize/config.json`; when set, **overrides** the file. |
| `TRANSCRIBE_CLI` | Path to `transcribe_diarize.py` if not under `~/.codex/skills/transcribe/scripts/`. |
| `CODEX_HOME` | Base for default transcribe helper (default `~/.codex`). |
| `INSTALOADER_BIN`, `FFMPEG_BIN`, `PYTHON_BIN` | Override binaries on PATH. |
| `OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE` | OpenRouter defaults. |

## Cursor skill

See [`SKILL.md`](./SKILL.md) for agent-oriented instructions (same workflow, `IG_SUMMARIZE_CLI`).

## Limits and caveats

- **Private posts** need Instaloader login or cookies (`--instaloader-arg` forwarding).
- Transcription helper enforces a **~25 MB** audio limit; very long reels may need manual splitting.
- Respect Instagram’s terms and rate limits; this tool is for personal/archival use cases.

## License

MIT
