# LocalMind

LocalMind is a small CLI-first Python scaffold for talking to a local LLM server through an OpenAI-compatible API. This repository intentionally keeps the first version minimal: configuration loading, provider abstraction, simple agent flow, and a tiny SQLite-backed session placeholder.

## Features

- Python package installable with `pip install -e .`
- Typer CLI with `init`, `ask`, `chat`, `config show`, and `models test`
- Config loading from `./localmind.yaml`, then `~/.config/localmind/config.yaml`, then defaults
- OpenAI-compatible provider defaults aimed at `llama.cpp` server mode
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

Start an interactive chat:

```bash
localmind chat
```

Exit the chat REPL with `exit`, `quit`, or `Ctrl+D`.

## Configuration Files

Load order:

1. `./localmind.yaml`
2. `~/.config/localmind/config.yaml`
3. built-in defaults

An example configuration is included in `config.example.yaml`.
