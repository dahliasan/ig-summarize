# ig-summarize

Turn an **Instagram post or reel URL** into a **transcript** (speech-to-text) and, optionally, a **short summary** via [OpenRouter](https://openrouter.ai/). Runtime uses only the Python standard library; you bring [Instaloader](https://instaloader.github.io/), [ffmpeg](https://ffmpeg.org/), and an OpenAI-compatible transcription helper.

## Prerequisites (not installed by this repo)

```bash
pipx install instaloader   # recommended on macOS (PEP 668)
# brew install ffmpeg
```

You also need the Codex **transcribe** helper `transcribe_diarize.py` (typically `~/.codex/skills/transcribe/scripts/transcribe_diarize.py`) or set `TRANSCRIBE_CLI` to that file.

---

## Setup (pick one)

### A. **`pipx` (closest to “npm install -g”)** — recommended

Installs a global **`ig-summarize`** command (isolated venv, upgrades with `pipx upgrade ig-summarize`).

```bash
pipx install "git+https://github.com/dahliasan/ig-summarize.git"
# or from a local clone:
cd /path/to/ig-summarize
pipx install .
```

Then run:

```bash
ig-summarize config path
ig-summarize "https://www.instagram.com/p/SHORTCODE/"
```

You do **not** need `IG_SUMMARIZE_CLI` when using this path.

### B. **Git clone + repo launcher (no pip install)**

```bash
git clone https://github.com/dahliasan/ig-summarize.git
cd ig-summarize
chmod +x ig-summarize
./ig-summarize config path
```

Or add the repo to `PATH` and run `ig-summarize` from anywhere:

```bash
export PATH="/path/to/ig-summarize:$PATH"
ig-summarize config path
```

### C. **`python3` against the script file (advanced)**

Use this only if you point at the **actual script file**, not your home directory.

```bash
python3 /path/to/ig-summarize/scripts/ig_summarize.py config path
```

Optional env var (must be a **file path ending in `.py`**):

```bash
export IG_SUMMARIZE_CLI="/path/to/ig-summarize/scripts/ig_summarize.py"
python3 "$IG_SUMMARIZE_CLI" config path
```

### D. **`python -m` from a clone**

```bash
cd /path/to/ig-summarize
python3 -m ig_summarize config path
```

---

## Usage

```bash
export OPENAI_API_KEY="…"   # required for transcription

ig-summarize "https://www.instagram.com/p/SHORTCODE/"

# Keep Instaloader output under ./ig-summarize-<shortcode>/
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --keep

# Pin all artifacts under one directory
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --out-dir ./out

# Summary (uses OPENROUTER_API_KEY or ~/.config/ig-summarize/config.json)
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --summary
```

If you did not use `pipx` and did not add the repo to `PATH`, replace `ig-summarize` with `./ig-summarize` or `python3 path/to/scripts/ig_summarize.py` as in the setup section.

---

## OpenRouter API key (config file)

Keys are stored under **`~/.config/ig-summarize/config.json`** (or `$XDG_CONFIG_HOME/ig-summarize/config.json`). The file is written with mode **`0600`**. **`OPENROUTER_API_KEY` in the environment always overrides** the file when set.

```bash
export OPENROUTER_API_KEY="sk-or-…"
ig-summarize config save-openrouter --from-env

# Or paste at a prompt
ig-summarize config save-openrouter

# Or pipe (avoid shell history)
ig-summarize config save-openrouter < /path/to/keyfile

ig-summarize config path
```

---

## Summarization model (OpenRouter)

**Default for `--summary`:** **`openrouter/free`** — OpenRouter’s free-tier **router** (not one fixed weights snapshot).

**Precedence (highest first):** `--openrouter-model` → **`OPENROUTER_MODEL`** → **`openrouter_model`** in `~/.config/ig-summarize/config.json` (via **`ig-summarize config set-model`**) → **`openrouter/free`**.

Shorthand: **`--openrouter-model free`** means **`openrouter/free`**.

### Like `summarize refresh-free` ([install.md](https://github.com/steipete/summarize/blob/main/docs/install.md))

After you set **`OPENROUTER_API_KEY`**, Summarize recommends **`summarize refresh-free`** to refresh the free-model preset. **`ig-summarize config refresh-free`** does a **lighter** step: it calls OpenRouter’s public **`/api/v1/models`** endpoint (no key required), finds models with **listed $0** prompt and completion pricing, and stores **`openrouter_free_model_ids`** plus a timestamp in your config. It does **not** run summarize-style latency probes or ranking.

```bash
ig-summarize config refresh-free
ig-summarize config list-free
ig-summarize config set-model google/gemma-3-4b-it:free   # example pinned default
```

---

## Troubleshooting

### `can't find '__main__' module in '/Users/…'`

Python is trying to run a **directory** (usually **`$HOME`**) as the script. That almost always means **`IG_SUMMARIZE_CLI` is wrong**: empty, unset, or set to `$HOME` / `~` instead of the **`.py` file**.

**Fix:** unset it and use `pipx` / `./ig-summarize`, or set it to the full path of `scripts/ig_summarize.py` (see setup C).

```bash
unset IG_SUMMARIZE_CLI
```

---

## How it works

1. Parse the **shortcode** from `/p/`, `/reel/`, `/reels/`, or `/tv/` URLs (or pass the shortcode alone).
2. Run **Instaloader**: `instaloader -q … -- -<shortcode>` (see Instaloader docs).
3. Take the **largest `.mp4`** (handles carousels).
4. **ffmpeg** extracts mono AAC for the transcription API.
5. **`transcribe_diarize.py … --stdout`** produces the transcript.
6. With **`--summary`**, call OpenRouter chat completions using the **resolved model** (default **`openrouter/free`**; see README “Summarization model”).

## Environment

| Variable | Role |
|----------|------|
| `OPENAI_API_KEY` | Required for transcription. |
| `OPENROUTER_API_KEY` | Optional if key is in `~/.config/ig-summarize/config.json`; when set, **overrides** the file. |
| `TRANSCRIBE_CLI` | Path to `transcribe_diarize.py` if not under `~/.codex/skills/transcribe/scripts/`. |
| `CODEX_HOME` | Base for default transcribe helper (default `~/.codex`). |
| `INSTALOADER_BIN`, `FFMPEG_BIN`, `PYTHON_BIN` | Override binaries on PATH. |
| `OPENROUTER_MODEL` | Default summary model; overrides `openrouter_model` in config. |
| `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE` | Optional OpenRouter attribution headers. |
| `IG_SUMMARIZE_CLI` | Optional; only if you invoke `python3 "$IG_SUMMARIZE_CLI" …` — must be the **script file path**, not `$HOME`. |

## Cursor skill

See [`SKILL.md`](./SKILL.md).

## Limits and caveats

- **Private posts** need Instaloader login or cookies (`--instaloader-arg` forwarding).
- Transcription helper enforces a **~25 MB** audio limit; very long reels may need manual splitting.
- Respect Instagram’s terms and rate limits; this tool is for personal/archival use cases.

## License

MIT
