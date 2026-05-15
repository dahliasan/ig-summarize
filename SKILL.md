---
name: ig-summarize
description: Instagram /p/ or /reel/ URL → download (Instaloader) → Summarize-style transcription (local whisper with auto model resolve/download → Groq → AssemblyAI → OpenAI) → optional OpenRouter summary (default openrouter/free).
---

# ig-summarize

Use when the user wants a **transcript** or **optional summary** of an **Instagram video** from a `/p/`, `/reel/`, `/reels/`, or `/tv/` URL in **one command** (no separate transcribe step).

## References

- Repo: https://github.com/dahliasan/ig-summarize
- Summarize (transcription ordering / env names): https://github.com/steipete/summarize/blob/main/README.md
- Instaloader: https://instaloader.github.io/
- OpenRouter: https://openrouter.ai/docs/api/reference/overview

## Preconditions

1. **`instaloader`** and **`ffmpeg`** on `PATH` (or `*_BIN` overrides).
2. **At least one transcription path** (same tiers as Summarize’s media docs, minus Gemini/FAL):
   - Local: **`whisper-cli`** on `PATH`; weights are **auto-discovered** (XDG `ig-summarize/models`, `~/.summarize/models`, etc.) or **downloaded once** (`ggml-tiny.en.bin`) unless `IG_SUMMARIZE_SKIP_AUTO_WHISPER_MODEL_DOWNLOAD=1`. Optional: **`SUMMARIZE_WHISPER_CPP_MODEL_PATH`**, or **`ig-summarize config set-whisper-model /path/to.bin`**
   - Or cloud: **`GROQ_API_KEY`**, **`ASSEMBLYAI_API_KEY`**, or **`OPENAI_API_KEY`**
3. For **`--summary`**: **`OPENROUTER_API_KEY`** or `config save-openrouter`.

## Model resolution (summary only)

`--openrouter-model` → **`OPENROUTER_MODEL`** → **`openrouter_model`** in config → **`openrouter/free`**. Shorthand **`free`** → **`openrouter/free`**.

## Commands

```bash
ig-summarize "https://www.instagram.com/p/SHORTCODE/"
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --print-transcript
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --summary
ig-summarize config save-openrouter --from-env
ig-summarize config refresh-free
ig-summarize config set-model openrouter/free
```

Default transcript path is cwd, or **`~/Downloads`** when cwd is home; **`--out-dir`** overrides.

## Failure handling

- No transcript: list which providers were tried; local tier needs `whisper-cli` (weights auto-resolve or one-time download). Cloud: suggest `GROQ_API_KEY` or `OPENAI_API_KEY` — never ask for pasted secrets in chat.
- Missing OpenRouter key for `--summary`: suggest `config save-openrouter`.
- Instaloader failures: `--instaloader-arg` for login/cookies. Anonymous GraphQL 403 is common even when download succeeds; `ig-summarize` collapses that noise to one warning.
