---
name: ig-summarize
description: Instagram /p/ or /reel/ URL → download (Instaloader) → Summarize-style transcription (whisper-cli → Groq → AssemblyAI → OpenAI) → optional OpenRouter summary (default openrouter/free).
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
   - Local: **`whisper-cli`** + **`SUMMARIZE_WHISPER_CPP_MODEL_PATH`**
   - Or cloud: **`GROQ_API_KEY`**, **`ASSEMBLYAI_API_KEY`**, or **`OPENAI_API_KEY`**
3. For **`--summary`**: **`OPENROUTER_API_KEY`** or `config save-openrouter`.

## Model resolution (summary only)

`--openrouter-model` → **`OPENROUTER_MODEL`** → **`openrouter_model`** in config → **`openrouter/free`**. Shorthand **`free`** → **`openrouter/free`**.

## Commands

```bash
ig-summarize "https://www.instagram.com/p/SHORTCODE/"
ig-summarize "https://www.instagram.com/p/SHORTCODE/" --summary
ig-summarize config save-openrouter --from-env
ig-summarize config refresh-free
ig-summarize config set-model openrouter/free
```

## Failure handling

- No transcript: list which providers were tried; suggest `GROQ_API_KEY` or `OPENAI_API_KEY` or local whisper model path — never ask for pasted secrets in chat.
- Missing OpenRouter key for `--summary`: suggest `config save-openrouter`.
- Instaloader failures: `--instaloader-arg` for login/cookies.
