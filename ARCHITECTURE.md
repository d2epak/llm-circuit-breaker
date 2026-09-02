# Architecture & Engineering Notes: LLM Circuit Breaker

**Version:** 0.2.0  
**Author:** Deepak & Community Contributors  
**License:** MIT  

---

## 1. The Core Challenge: Free LLMs for Autonomous Agents

Building autonomous AI coding agents (such as **Claude Code**, **Hermes Agent**, and **OpenClaw**) requires sustained, high-context reasoning across hundreds of conversational turns. While commercial frontier APIs (Anthropic, OpenAI) cost significant money over multi-hour sessions, dozens of top-tier open-weights models and aggregators (Google AI Studio, Groq, Cerebras, Mistral, NVIDIA NIM, OpenRouter) offer **free tier quotas**.

However, attempting to run autonomous agents directly on free-tier APIs inevitably fails due to four brutal failure modes:

1. **Protocol Incompatibility**: Claude Code exclusively expects the Anthropic `/v1/messages` protocol with nested `tool_use` blocks and `input_schema` schemas. Open-weights models and aggregators speak OpenAI `/v1/chat/completions` with `tool_calls`. Dumb reverse proxies forward raw JSON and fail with `HTTP 400: Unrecognized parameter`.
2. **Streaming Dropouts**: Claude Code streams responses via Server-Sent Events (SSE). If a provider rate-limits (HTTP 429) or crashes midway through a streamed response, the client experiences a broken pipe and terminates the agent's work session.
3. **Protobuf Schema Rejection**: Google AI Studio provides a free 1,048,576 token (1M) context window (via Gemini 2.5 Flash), which is ideal for long-horizon coding. However, Google's API parser strictly rejects standard JSON Schema Draft-07 keys (`$schema`, `additionalProperties`, `default`, and lowercase types), returning `HTTP 400: unknown name "$schema"`.
4. **Context Overflow Cascades**: Switching from a 1M token model to a 32k/64k backup model causes an immediate `HTTP 413: context_length_exceeded` fatal crash.
5. **Cross-Agent Starvation**: Running Claude Code, Hermes, and OpenClaw on a single shared endpoint causes Claude Code's heavy coding requests to consume rate limits, starving Hermes and OpenClaw of conversational turns.

**LLM Circuit Breaker** solves all of these challenges natively in a zero-dependency, self-healing gateway.

---

## 2. Architecture Overview

```
                        +---------------------------------------+
                        |           AI AGENT CLIENTS            |
                        | Claude Code | Hermes Agent | OpenClaw |
                        +-------------------+-------------------+
                                            |
                         HTTP Requests (Anthropic / OpenAI)
                                            v
+-----------------------------------------------------------------------------------+
|                           LLM CIRCUIT BREAKER GATEWAY                             |
|                                                                                   |
|  +---------------------------+             +-----------------------------------+  |
|  |   Anthropic /v1/messages  |             |     OpenAI /v1/chat/completions   |  |
|  |     (for Claude Code)     |             |     (for Hermes & OpenClaw)       |  |
|  +-------------+-------------+             +-----------------+-----------------+  |
|                |                                             |                    |
|                v                                             v                    |
|  +---------------------------+             +-----------------------------------+  |
|  |   Protocol Translator     |             |       Dynamic Context Pruner      |  |
|  | - Anthropic <-> OpenAI    |             | - Compacts old tool_results       |  |
|  | - Synthetic SSE Streamer  |             | - Preserves Goal & System Turn    |  |
|  | - Gemini Protobuf Cleaner |             +-----------------+-----------------+  |
|  +-------------+-------------+                               |                    |
|                +----------------------+----------------------+                    |
|                                       v                                           |
|                     +-----------------------------------+                         |
|                     |     Universal Failover Router     |                         |
|                     +-----------------+-----------------+                         |
|                                       |                                           |
|          +----------------------------+----------------------------+              |
|          v                                                         v              |
|  +--------------------------------+             +-------------------------------+ |
|  |     POOL 1: 'CODING'           |             |     POOL 2: 'GENERAL_AGENT'   | |
|  | - Gemini 2.5 Flash (1M)        |             | - Cerebras Llama 3.3 70B      | |
|  | - Mistral Codestral            |             | - Groq Llama 3.3 70B          | |
|  | - Cerebras Llama 3.3 70B       |             | - Gemini 2.5 Flash            | |
|  | - Groq Llama 3.3 70B           |             | - Discovered Free Models      | |
|  | - Discovered $0 Coder Models   |             | - Local Ollama Qwen/Llama     | |
|  +--------------------------------+             +-------------------------------+ |
|          |                                                         |              |
|          +----------------------------+----------------------------+              |
|                                       v                                           |
|                     +-----------------------------------+                         |
|                     |     Error Classifier & Cooldown   |                         |
|                     | - Independent Cooldown Timers     |                         |
|                     | - Instant 404 Auto-Deprecation    |                         |
|                     | - 25s Socket Timeout Guarantee    |                         |
|                     +-----------------------------------+                         |
+-----------------------------------------------------------------------------------+
```

---

## 3. Deep-Dive: Key Innovations

### A. Dual-Pool Multi-Agent Isolation
Instead of maintaining a single linear fallback chain, the engine separates routing into two independent pools:
* **`coding` Pool**: Tuned for AST manipulation, large multi-file diffs, and strict JSON tool schema validation.
* **`general_agent` Pool**: Tuned for ultra-low latency inference, multi-turn dialogue, web search synthesis, and general planning.

**Independent Cooldowns**:
If Claude Code exhausts Groq's tokens per minute with a massive prompt, Groq is placed on cooldown **only for the `coding` pool**. Hermes and OpenClaw can continue using Groq for conversational steps without interruption.

### B. Synthetic SSE Streaming
Claude Code always requests streaming (`stream: true`). Rather than piping raw network chunks (which breaks failover if an upstream provider dies mid-chunk), the Circuit Breaker:
1. Buffers the upstream completion completely.
2. If the provider errors (429, 503, 500, timeout), it immediately fails over to the next provider silently.
3. Once a healthy HTTP 200 is secured, it synthesizes standard Anthropic SSE events:
   - `message_start`
   - `content_block_start` / `content_block_delta` (for text, thinking, and tool_use)
   - `content_block_stop`
   - `message_delta`
   - `message_stop`

Claude Code receives a clean, unbroken stream every single turn.

### C. Google Gemini Protobuf Sanitizer (`clean_gemini_schema`)
Google AI Studio's Gemini REST API (`/v1beta/models/...:generateContent`) uses Protobuf definitions that reject Draft-07 schema keywords.

`clean_gemini_schema()` recursively:
- Strips `$schema`, `additionalProperties`, `default`, `title`, `$id`, `$comment`, `definitions`.
- Normalizes type declarations to Gemini uppercase strings (`OBJECT`, `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `ARRAY`).
- Resolves `["string", "null"]` type unions.
- Tracks `tool_id_to_name` so subsequent tool execution turns accurately report `functionResponse.name` back to Gemini.

### D. Dynamic Sliding-Window Context Compaction
When failing over from a 1M token model to a 32k/64k model:
- Compaction isolates historical `tool_result` payloads in older turns (file contents and terminal outputs) and truncates them to a 500-character representative excerpt.
- The system prompt, the root user objective, and the latest 6 execution turns are strictly preserved.
- Prevents fatal `HTTP 413` errors on open-weights fallback models.

### E. 25-Second Fast Failover & Socket Timeouts
Default HTTP client timeouts (60s–120s) cause agents to freeze when an upstream provider hangs on an open TCP socket. The Circuit Breaker enforces:
- Global socket read timeout of **25 seconds** (`socket.setdefaulttimeout(25)`).
- **Instant 404 Deprecation**: Any endpoint returning HTTP 404 is permanently blacklisted for the session, preventing recurring round-robin delays.

### F. Tool Argument JSON Healing
Open-weights models frequently wrap JSON arguments in markdown code blocks (` ```json ... ``` `) or append trailing commas before closing brackets. `repair_json_string()` sanitizes these anomalies before passing tool calls to Claude Code.

---

## 4. Zero-Dependency Runtime Philosophy

The core proxy and library run **100% on standard Python 3.9+ libraries**:
- `http.server.ThreadingHTTPServer`
- `urllib.request`
- `socket`
- `json`
- `sqlite3`
- `threading`

No external virtual environments, wheels, or compiled extensions are required. Optional ASGI integration (`fastapi`, `uvicorn`) is available via `pip install 'llm-circuit-breaker[asgi]'`.

---

## 5. Live Production Verification

The architecture has been verified under real-world multi-hour autonomous runs:
* **Task**: Distributed Raft consensus implementation and 15-minute network partition chaos test (`chaos_tester.py`).
* **Harness**: Claude Code v2.1 CLI.
* **Duration**: 45+ minutes continuous unattended operation.
* **Results**: Flawless tool schema execution, automated code modifications, subprocess execution, and sub-3-second response latency on Gemini 2.5 Flash.
