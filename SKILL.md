---
name: ig-summarize
description: Download an Instagram post/reel with Instaloader, transcribe via OpenAI audio API (transcribe_diarize helper), optionally summarize with OpenRouter (default openrouter/free; config refresh-free / set-model).
---

# ig-summarize

Use when the user wants a **transcript** or **optional summary** of an **Instagram video** from a `/p/`, `/reel/`, `/reels/`, or `/tv/` URL.

## References

- Repo: https://github.com/dahliasan/ig-summarize
- Instaloader: https://instaloader.github.io/ — post target: `instaloader … -- -<shortcode>`
- OpenRouter API: https://openrouter.ai/docs/api/reference/overview

## Preconditions

1. **Instaloader** on `PATH` (`pipx install instaloader`) or `INSTALOADER_BIN`.
2. **ffmpeg** on `PATH` or `FFMPEG_BIN`.
3. **`OPENAI_API_KEY`** for transcription.
4. **`transcribe_diarize.py`** at `~/.codex/skills/transcribe/scripts/` or `TRANSCRIBE_CLI`.
5. Optional OpenRouter: **`OPENROUTER_API_KEY`** or **`config save-openrouter`**. Optional default summary model: **`config set-model`** or **`OPENROUTER_MODEL`**. Default model if unset: **`openrouter/free`**. Run **`config refresh-free`** periodically to refresh the cached list of $0-priced model ids (Summarize-style; list-only, no probes).

## Model resolution

`--openrouter-model` → **`OPENROUTER_MODEL`** → **`openrouter_model`** in config → **`openrouter/free`**. Shorthand **`free`** → **`openrouter/free`**.

## CLI

Prefer the global command after **`pipx install .`** or **`pipx install git+https://github.com/dahliasan/ig-summarize.git`**:

```bash
ig-summarize "https://www.instagram.com/p/SHORTCODE/"
```

From a clone without install: **`./ig-summarize`** (repo root) or **`python3 -m ig_summarize`** from the repo directory.

Only if you shell-wrap **`python3 "$IG_SUMMARIZE_CLI" …`**: `IG_SUMMARIZE_CLI` must be the **full path to `scripts/ig_summarize.py`**, never `$HOME` or a directory (otherwise Python raises `can't find '__main__' module in '/Users/…'`).

## Commands

```bash
ig-summarize "https://www.instagram.com/p/SHORTCODE/"
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --keep
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --out-dir ./out
ig-summarize config save-openrouter --from-env
ig-summarize config refresh-free
ig-summarize config list-free
ig-summarize config set-model openrouter/free
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --summary
```

## Failure handling

- Missing OpenRouter key for `--summary`: suggest `config save-openrouter` or `OPENROUTER_API_KEY`; never ask the user to paste secrets into chat.
- Missing **`OPENAI_API_KEY`**: name the env var only.
- Instaloader failures: suggest `--login` / `--load-cookies` via `--instaloader-arg`.
- No `.mp4`: image-only post or removal.
