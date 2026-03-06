---
name: gemini_cli
description: Gemini CLI for one-shot Q&A, summaries, and generation.
homepage: https://ai.google.dev/
metadata:
  {
    "openclaw":
      {
        "emoji": "🌟",
        "requires": { "bins": ["gemini"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "gemini-cli",
              "bins": ["gemini"],
              "label": "Install Gemini CLI (brew)",
            },
          ],
      },
  }
---

# Gemini CLI

Use Gemini in one-shot mode with a positional prompt (avoid interactive mode).

## Model Policy

- Default: `-m gemini-3.1-pro-preview`
- Fallback: `-m auto` (use when default fails, e.g. 403 or 429)

Quick start

- `gemini "Answer this question..."`
- `gemini --model <name> "Prompt..."`
- `gemini --output-format json "Return JSON"`

Extensions

- List: `gemini --list-extensions`
- Manage: `gemini extensions <command>`

Notes

- If auth is required, run `gemini` once interactively and follow the login flow.
- Avoid `--yolo` for safety.
