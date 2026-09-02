<div align="center">

# ⚡ LLM Circuit Breaker

**Zero-Downtime Multi-Provider LLM Failover & Autonomous Free-Model Discovery for AI Agents**

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](https://docs.python.org/3/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

*Run **Claude Code**, **Hermes Agent**, and **OpenClaw** simultaneously on free-tier LLM APIs without rate-limit crashes, mid-stream disconnects, or cross-agent starvation.*

</div>

---

## 🚀 Why LLM Circuit Breaker?

Autonomous coding agents (Claude Code, Cursor, Aider, Hermes Agent, OpenClaw) push LLM APIs to their absolute limits. Traditional reverse proxies and wrapper libraries break down in multi-agent environments:

- 💥 **Protocol Incompatibilities**: Claude Code requires Anthropic `/v1/messages` with complex `tool_use` schemas. Forwarding requests to OpenAI `/chat/completions` fails with `HTTP 400: Unrecognized parameter`.
- 💥 **Streaming Dropouts**: Mid-stream 429s or network blips break SSE streams, terminating the agent's work session.
- 💥 **Protobuf Schema Crashes**: Google AI Studio's 1M context Gemini models reject standard Draft-07 `$schema` tags in tool definitions.
- 💥 **Context Window Overflow**: Failing over from a 1M context model to a 32k/64k model causes fatal `HTTP 413: context_length_exceeded` errors.
- 💥 **Cross-Agent Starvation**: Running Claude Code and conversational agents on a shared endpoint exhausts rate limits and cascades failures across all agents.

**LLM Circuit Breaker** solves all of these challenges natively with an agent-first resilience layer.

---

## ✨ Features

- 🛡️ **Dual-Pool Isolation (`coding` vs `general_agent`)**: Dedicated pools with independent cooldown timers. Claude Code's heavy token bursts never starve Hermes or OpenClaw.
- 🔄 **Bidirectional Anthropic ↔ OpenAI Translation**: Seamlessly converts Anthropic messages, thinking blocks, and tool definitions to OpenAI format and back.
- 🌊 **Synthetic SSE Streaming**: Buffers upstream completions and verifies HTTP 200 before emitting synthetic Anthropic SSE events. Seamless, dropout-free failovers.
- 🧹 **Google Gemini REST Protobuf Sanitizer**: Automatically cleans tool parameter schemas (`clean_gemini_schema`) to unlock Google AI Studio's free 1,048,576 token context window.
- 🗜️ **Dynamic Sliding-Window Context Pruner**: Automatically compacts historical `tool_result` blocks when falling back from a 1M model to a 32k/64k model without losing initial goals.
- ⏱️ **25-Second Fast Failover**: Strict socket timeouts prevent agents from freezing on stalled upstream connections.
- 🔍 **Autonomous $0 Model Discovery**: Queries live aggregator catalogs for verified free models with native tool support.
- 📦 **Zero Mandatory Dependencies**: Runs 100% on Python 3 standard library (`http.server.ThreadingHTTPServer`, `urllib`).

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/d2epak/llm-circuit-breaker.git
cd llm-circuit-breaker

# Optional: Install as an editable package
pip install -e .

# Optional: With ASGI FastAPI support
pip install -e ".[asgi]"
```

---

## 🛠️ Plug-and-Play Quickstart

### Step 1: Start the Gateway
Run the local gateway on port `4001`:

```bash
python3 src/llm_circuit_breaker/proxy.py --port 4001
# Or via CLI script if installed:
# llm-proxy --port 4001
```

The gateway exposes:
- **Claude Code (Coding Pool)**: `http://127.0.0.1:4001/v1/messages`
- **Hermes / OpenClaw (Agent Pool)**: `http://127.0.0.1:4001/v1/chat/completions`
- **Health Diagnostics**: `http://127.0.0.1:4001/health`

---

### Step 2: Configure Your Agents

#### A. Claude Code
Point Claude Code to the local gateway:

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:4001/v1"
export ANTHROPIC_API_KEY="sk-circuit-breaker-token"
claude
```
*(Or use the 1-click script: `./examples/claude_code_setup.sh`)*

#### B. Hermes Agent
Add the custom provider to `~/.hermes/config.yaml`:

```yaml
custom_providers:
  - name: circuit-breaker
    base_url: http://127.0.0.1:4001/v1
    api_key: sk-circuit-breaker-token
    model: hermes-default

default_provider: circuit-breaker
default_model: hermes-default
```

#### C. OpenClaw
Set the OpenAI environment variables:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:4001/v1"
export OPENAI_API_KEY="sk-circuit-breaker-token"
export OPENAI_MODEL_NAME="openclaw-default"
```

---

## 🐍 Direct Python API

For custom agents and scripts, use the `UniversalFailoverRouter` directly:

```python
from llm_circuit_breaker import UniversalFailoverRouter, classify_api_error, FailoverReason

# Initialize router with priority endpoints + auto-discovered free backups
router = UniversalFailoverRouter()

payload = {
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a binary search algorithm in Python."}
    ],
    "max_tokens": 1024
}

# Dispatch with automatic multi-provider failover
status, response, route = router.dispatch("coding", payload)

if status == 200:
    print(response["choices"][0]["message"]["content"])
else:
    print("All fallback routes exhausted:", response)
```

---

## 🔍 Free-Model Discovery CLI

Find active $0 free models with native tool support right from your terminal:

```bash
python3 src/llm_circuit_breaker/discovery.py --limit 5
```

```text
🔍 Querying live aggregator catalog for $0 free models with native tool support...

💻 Coding Pool (8 discovered):
  1. qwen/qwen-2.5-coder-32b-instruct:free (32,768 tokens context)
  2. mistralai/devstral-2512:free (262,144 tokens context)

🤖 General Agent Pool (14 discovered):
  1. google/gemma-4-26b-a4b-it:free (262,144 tokens context)
  2. nvidia/nemotron-3-nano-30b-a3b:free (32,768 tokens context)
```

---

## 🧪 Testing

Run the full self-contained unit test suite (13/13 passing):

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 📚 Deep-Dive Architecture

For detailed design notes on Protobuf schema sanitization, synthetic SSE streaming, dual-pool cooldown isolation, and context compaction algorithms, see [**`ARCHITECTURE.md`**](ARCHITECTURE.md).

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
