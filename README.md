# ig-summarize

Turn an **Instagram post or reel URL** into a **transcript** and, optionally, a **short summary** via [OpenRouter](https://openrouter.ai/). One command does **download → extract audio → transcribe → (optional) summarize**, similar in spirit to [steipete/summarize](https://github.com/steipete/summarize).

Runtime uses **Python’s standard library only** (plus your installed **`instaloader`** and **`ffmpeg`**).

---

## Prerequisites

```bash
pipx install instaloader
brew install ffmpeg
```

---

## Install `ig-summarize`

```bash
pipx install "git+https://github.com/dahliasan/ig-summarize.git"
# or from a clone:
cd /path/to/ig-summarize && pipx install .
```

Then use the global command **`ig-summarize`**.

**Without pipx:** clone the repo, `chmod +x ig-summarize`, run `./ig-summarize …`, or `python3 -m ig_summarize …` from the repo root.

---

## Transcription (same *idea* as Summarize)

[`summarize`’s README](https://github.com/steipete/summarize) describes Whisper fallback order for media:

> Prefers local **whisper.cpp** when installed + model available.  
> Otherwise uses cloud transcription in this order: **Groq** → **AssemblyAI** → **Gemini** → **OpenAI** → **FAL**.

**`ig-summarize`** implements the same **first four** tiers (no Gemini/FAL yet), using **the same env names Summarize documents for whisper.cpp**:

| Order | Provider | What you need |
|------:|----------|----------------|
| 1 | **Local `whisper-cli`** | `whisper-cli` on `PATH` (Homebrew: `brew install whisper-cpp`). **Weights are resolved automatically:** `ig-summarize` searches common dirs (e.g. `~/.local/share/ig-summarize/models`, `~/.summarize/models`, `~/whisper.cpp/models`), reads optional **`whisper_cpp_model_path`** from `~/.config/ig-summarize/config.json` (`ig-summarize config set-whisper-model /path/to.gguf`), then **`SUMMARIZE_WHISPER_CPP_MODEL_PATH`** if set. If nothing is found, it **downloads `ggml-tiny.en.bin` once** to the XDG data dir (skip with **`IG_SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD=1`**). Optional: **`SUMMARIZE_WHISPER_CPP_BINARY`**, or disable local with **`SUMMARIZE_DISABLE_LOCAL_WHISPER_CPP=1`**. |
| 2 | **Groq** | **`GROQ_API_KEY`** (OpenAI-compatible Whisper API). Optional: **`IG_GROQ_TRANSCRIBE_MODEL`** (default `whisper-large-v3`). |
| 3 | **AssemblyAI** | **`ASSEMBLYAI_API_KEY`** |
| 4 | **OpenAI** | **`OPENAI_API_KEY`**. Optional: **`OPENAI_WHISPER_BASE_URL`** (default `https://api.openai.com/v1`), **`IG_OPENAI_TRANSCRIBE_MODEL`** (default `whisper-1`). |

Audio is extracted as **16 kHz mono WAV** so **`whisper-cli`** and cloud APIs stay happy.

You only need **one** working path from the table (Groq alone is enough for a zero-local setup).

---

## Summarization (OpenRouter)

**`--summary`** calls OpenRouter chat completions. Default model: **`openrouter/free`**. Override with **`--openrouter-model`**, **`OPENROUTER_MODEL`**, or **`ig-summarize config set-model`**.

Save API key once:

```bash
export OPENROUTER_API_KEY="…"
ig-summarize config save-openrouter --from-env
```

Refresh cached free model ids (list-only, like Summarize’s `refresh-free` concept):

```bash
ig-summarize config refresh-free
ig-summarize config list-free
```

---

## One-shot usage

```bash
# Transcript only (needs one transcription provider from the table above)
ig-summarize "https://www.instagram.com/p/SHORTCODE/"

# Transcript + summary (add OpenRouter key via env or config save-openrouter)
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --summary
```

Artifacts: by default, **`SHORTCODE.transcript.txt`** in the current directory (and **`SHORTCODE.summary.txt`** with `--summary`). Use **`--keep`** or **`--out-dir`** to keep downloads.

---

## Environment cheat sheet

| Variable | Role |
|----------|------|
| `GROQ_API_KEY` | Cloud transcription (preferred cloud tier in `ig-summarize`). |
| `ASSEMBLYAI_API_KEY` | Cloud transcription fallback. |
| `OPENAI_API_KEY` | Cloud transcription fallback; also used if only OpenAI is set. |
| `OPENAI_WHISPER_BASE_URL` | Custom OpenAI-compatible STT endpoint. |
| `SUMMARIZE_WHISPER_CPP_MODEL_PATH` | Force a specific local whisper weights file (optional; auto-discovery + one-time default download otherwise). |
| `IG_SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD` / `SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD` | Set to `1` to never auto-download `ggml-tiny.en.bin` when no weights are found. |
| `SUMMARIZE_WHISPER_CPP_BINARY` | Local binary override (same as Summarize). |
| `SUMMARIZE_DISABLE_LOCAL_WHISPER_CPP` | Set to `1` to skip local whisper. |
| `OPENROUTER_API_KEY` | Summary step; optional if saved in config. |
| `OPENROUTER_MODEL` | Default summary model override. |
| `INSTALOADER_BIN`, `FFMPEG_BIN` | Binary overrides. |

`IG_*` aliases exist for a few vars (see `ig_summarize/transcribe.py`).

---

## Troubleshooting

### `can't find '__main__' module in '/Users/…'`

You pointed **`IG_SUMMARIZE_CLI`** at a directory (often `$HOME`). Use **`pipx install`**, or set the var to the **`.py` file** path. Prefer: **`pipx install`** and run **`ig-summarize`** with no env var.

---

## Limits

- Private Instagram posts may need Instaloader login/cookies (`--instaloader-arg`).
- Very large audio may hit provider limits.
- Respect Instagram’s terms and rate limits.

## License

MIT
