# LocalMind

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-TBD-lightgrey)
![Status](https://img.shields.io/badge/Status-Early--stage%20but%20functional-orange)
![Local-first](https://img.shields.io/badge/AI-Local--first-green)
![llama.cpp](https://img.shields.io/badge/Backend-llama.cpp%20API-black)

Local-first AI assistant for Linux, built for the terminal.

LocalMind is a lightweight Python 3.11+ project that provides a CLI-first AI assistant experience on Linux using a local LLM backend. It is built with Typer, stores chat history in SQLite, loads configuration from local or user-level YAML files, and currently targets a `llama.cpp` server through an OpenAI-compatible API.

## What Is LocalMind?

LocalMind is an independent local AI assistant project focused on a small, readable core and a practical command-line workflow. Today, it provides a usable terminal experience for one-shot prompts, interactive chat, persistent sessions, configuration inspection, and local model connectivity checks.

The current default backend is a local `llama.cpp` server exposed through an OpenAI-compatible API at `http://127.0.0.1:8080/v1`, with the initial target model set to `openbmb/MiniCPM5-1B-GGUF:Q4_K_M`.

## Why LocalMind?

- Local-first: designed to run against a local model server on your Linux machine.
- Lightweight: small Python codebase with a narrow initial scope.
- CLI-first: built around direct terminal workflows instead of a browser UI.
- Privacy-friendly: conversation state is stored locally in SQLite.
- Provider-agnostic architecture: current default is `llama.cpp`, but the structure is intended to support other OpenAI-compatible or future providers over time.
- Designed to grow: planned evolution includes richer memory, a local API, and broader project assistance.

## Current Features

Only features that exist today are listed here.

| Feature | Status | Notes |
| --- | --- | --- |
| CLI with Typer | Available | Includes `init`, `ask`, `chat`, `sessions`, `memory`, `config show`, `models test`, and `files` commands |
| `llama.cpp` / OpenAI-compatible provider | Available | Current backend flow targets a local `llama.cpp` server through an OpenAI-compatible API |
| Config loading | Available | Loads `./localmind.yaml`, then `~/.config/localmind/config.yaml`, else defaults |
| Persistent SQLite sessions | Available | Stores session and message history locally |
| Manual local memory | Available | Supports explicit memory add/list/show/search/delete/clear commands plus deterministic prompt injection |
| `ask` and `chat` commands | Available | Supports one-shot prompts plus interactive chat with new or resumed sessions |
| Sessions management | Available | Supports listing, showing, deleting, and resuming saved sessions |
| Model connectivity test | Available | Verifies provider access and reported model availability |
| Safe local file commands | Available | Explicit `files list`, `read`, `search`, `summarize`, and `summarize-project` commands with size and path safety checks |
| Clean modular Python layout | Available | Split into focused packages for CLI, config, LLM/provider, and tools infrastructure |
| `pytest` test suite | Available | Repository includes automated tests covering imports, sessions, behavior, and CLI chat flows |

Not included: plugins, WebUI, vector RAG, embeddings, MCP, autonomous tool-calling, or a built-in local API/server.

## Architecture Overview

```text
User
  ↓
LocalMind CLI
  ↓
Agent
  ↓
Context Builder + Session Store
  ↓
OpenAI-compatible Provider
  ↓
llama.cpp Server
  ↓
Local LLM
```

### Layers

| Layer | Role |
| --- | --- |
| User | Interacts through terminal commands or interactive chat |
| LocalMind CLI | Exposes the command-line interface via Typer |
| Agent | Orchestrates prompt handling and assistant replies |
| Context Builder + Session Store | Builds prompt context and persists chat history in SQLite |
| OpenAI-compatible Provider | Sends requests using an OpenAI-style API contract |
| `llama.cpp` Server | Serves the local model over HTTP |
| Local LLM | The GGUF model running on your machine |

## Requirements

- Linux
- Python 3.11+
- A running `llama.cpp` server
- A local GGUF model, initially `openbmb/MiniCPM5-1B-GGUF:Q4_K_M`

## Installation

Clone the repository:

```bash
git clone https://github.com/eobarretooo/localmind
cd localmind
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install LocalMind with development dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

## `llama.cpp` Setup

Start a local `llama.cpp` server with the initial target model:

```bash
./build/bin/llama-server \
  -hf openbmb/MiniCPM5-1B-GGUF:Q4_K_M \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096
```

LocalMind currently expects the OpenAI-compatible API at:

```text
http://127.0.0.1:8080/v1
```

If your server uses a different URL or model identifier, update the LocalMind configuration after initialization.

## Configuration

LocalMind resolves configuration in this order:

| Path | Purpose |
| --- | --- |
| `./localmind.yaml` | Project-local override for the current working directory |
| `~/.config/localmind/config.yaml` | User-level default configuration |
| built-in defaults | Used when no config file exists |

The repository also includes `config.example.yaml` as a reference template.

Current defaults:

| Setting | Default |
| --- | --- |
| Provider type | `openai_compatible` |
| Provider URL | `http://127.0.0.1:8080/v1` |
| Default model | `openbmb/MiniCPM5-1B-GGUF:Q4_K_M` |
| Max file bytes | `200000` |
| Max injected memory items | `5` |

Generate a local config file with:

```bash
localmind init
```

## Usage

Initialize a local config file:

```bash
localmind init
```

Show the effective configuration:

```bash
localmind config show
```

Test connectivity to the configured model provider:

```bash
localmind models test
```

Ask a one-shot question:

```bash
localmind ask "Say hello in one short sentence."
```

Start a new interactive chat session:

```bash
localmind chat --new
```

List saved sessions:

```bash
localmind sessions list
```

Show a specific saved session:

```bash
localmind sessions show SESSION_ID
```

Resume a saved chat session:

```bash
localmind chat --session SESSION_ID
```

Send another one-shot message into an existing session:

```bash
localmind ask "What is my name?" --session SESSION_ID
```

Add a manual local memory item:

```bash
localmind memory add "My name is Antonio" --tag profile
```

List saved memories:

```bash
localmind memory list
```

Search memories:

```bash
localmind memory search Antonio
```

List files recursively under the current directory, skipping common build, cache, virtualenv, VCS, and `references/` folders:

```bash
localmind files list .
```

Read a safe text file with truncation if needed:

```bash
localmind files read README.md
```

Search text files for a string:

```bash
localmind files search . LocalMind
```

Summarize one file without creating a persistent chat session unless `--session` is provided:

```bash
localmind files summarize README.md
```

Summarize a project from a compact file context:

```bash
localmind files summarize-project .
```

## Roadmap

This roadmap separates what is already implemented from what is next or planned.

### Phase 1 — Core CLI and `llama.cpp` provider

- Status: done
- CLI scaffold
- config loading
- provider abstraction
- model connectivity test

### Phase 2 — Persistent sessions

- Status: done
- SQLite sessions
- chat history
- session resume
- history limit

### Phase 3 — Safe file tools

- Status: done
- list files
- read files
- search files
- summarize files
- summarize project
- workspace safety

### Phase 4 — Local memory

- Status: in progress
- manual memory
- memory search
- deterministic relevant-memory injection
- session summaries

### Phase 5 — Plugin system

- Status: planned
- plugin discovery
- `plugin.yaml`
- commands and tools from plugins

### Phase 6 — Project/code agent

- Status: planned
- project scan
- code review
- README generation
- bug explanation

### Phase 7 — Local API

- Status: planned
- FastAPI backend
- local endpoints
- OpenAI-compatible optional API

### Phase 8 — WebUI

- Status: planned
- chat UI
- settings panel
- sessions browser
- model/provider selector

### Phase 9 — Multi-provider support

- Status: planned
- Ollama
- LM Studio
- other OpenAI-compatible local servers
- future cloud-compatible adapters

### Phase 10 — Integrations

- Status: future
- Discord
- Telegram
- automation
- MCP-like tools

## Project Status

LocalMind is early-stage but functional. The current codebase already supports real CLI usage, persistent sessions, configuration loading, and local model connectivity testing, the current test suite passes, and larger capabilities remain on the roadmap.

## Design Principles

- Local-first
- Small core
- Modular architecture
- Explicit over magical
- Safe tool execution
- No unnecessary complexity

## Inspirations

- `HKUDS/nanobot` inspired the idea of a small, readable core.
- `AstrBotDevs/AstrBot` inspired parts of the future direction around lifecycle, plugins, and dashboard-oriented expansion.
- LocalMind is an independent project and does not reuse those projects' branding or identity.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Run `pytest`.
4. Open a pull request.

## License

License: TBD
