# LocalMind

LocalMind is a small CLI-first Python scaffold for talking to a local LLM server through an OpenAI-compatible API. This repository intentionally keeps the first version minimal: configuration loading, provider abstraction, simple agent flow, and a small SQLite-backed persistent session store.

## Features

- Python package installable with `pip install -e .`
- Typer CLI with `init`, `ask`, `chat`, `sessions`, `config show`, and `models test`
- Config loading from `./localmind.yaml`, then `~/.config/localmind/config.yaml`, then defaults
- OpenAI-compatible provider defaults aimed at `llama.cpp` server mode
- Persistent SQLite sessions and message history
- Small, typed, testable package layout for future growth

## Installation

```bash
python -m pip install -e .
```

For running tests:

```bash
python -m pip install -e .[dev]
pytest
```

## llama.cpp Setup

Start an OpenAI-compatible `llama.cpp` server. Example:

```bash
./llama-server \
  -m /path/to/model.gguf \
  --host 127.0.0.1 \
  --port 8080
```

LocalMind defaults to:

- Base URL: `http://127.0.0.1:8080/v1`
- API key: none
- Model: `openbmb/MiniCPM5-1B-GGUF:Q4_K_M`

If your server exposes a different model identifier, update `localmind.yaml` after initialization.

## First Run

Initialize a local config file:

```bash
localmind init
```

Inspect the effective configuration:

```bash
localmind config show
```

Verify model connectivity:

```bash
localmind models test
```

Ask a single question:

```bash
localmind ask "Summarize the purpose of this project."
```

Ask within an existing session:

```bash
localmind ask "Continue the earlier plan." --session SESSION_ID
```

Start an interactive chat:

```bash
localmind chat
```

Resume or manage sessions:

```bash
localmind chat --session SESSION_ID
localmind chat --new
localmind sessions list
localmind sessions show SESSION_ID
localmind sessions delete SESSION_ID
```

Exit the chat REPL with `exit`, `quit`, or `Ctrl+D`.

## Configuration Files

Load order:

1. `./localmind.yaml`
2. `~/.config/localmind/config.yaml`
3. built-in defaults

An example configuration is included in `config.example.yaml`.

## History

LocalMind stores persistent chat state in SQLite at `memory.db_path`.

- `chat` creates a new session automatically unless `--session` is provided
- `ask` stays one-shot by default, but `--session` appends to an existing session
- The model context always starts with `app.system_prompt`
- Recent history is capped by `app.max_history_messages` and defaults to `12`
