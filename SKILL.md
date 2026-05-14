---
name: ig-summarize
description: Download an Instagram post/reel with Instaloader, transcribe via OpenAI audio API (transcribe_diarize helper), optionally summarize with OpenRouter (default openrouter/free).
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
5. Optional OpenRouter key: **`OPENROUTER_API_KEY`** or save with **`config save-openrouter`** to `~/.config/ig-summarize/config.json` (env overrides file).

## CLI path

```bash
export IG_SUMMARIZE_CLI="${IG_SUMMARIZE_CLI:-$HOME/projects/ig-summarize/scripts/ig_summarize.py}"
# or clone path:
# export IG_SUMMARIZE_CLI="$HOME/src/ig-summarize/scripts/ig_summarize.py"
```

## Commands

```bash
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/"
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --keep
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --out-dir ./out
python3 "$IG_SUMMARIZE_CLI" config save-openrouter --from-env   # after OPENROUTER_API_KEY is set
python3 "$IG_SUMMARIZE_CLI" "https://www.instagram.com/p/SHORTCODE/" --summary
```

## Failure handling

- Missing OpenRouter key for `--summary`: suggest `config save-openrouter` or `OPENROUTER_API_KEY`; never ask the user to paste secrets into chat.
- Missing **`OPENAI_API_KEY`**: name the env var only.
- Instaloader failures: suggest `--login` / `--load-cookies` via `--instaloader-arg`.
- No `.mp4`: image-only post or removal.
