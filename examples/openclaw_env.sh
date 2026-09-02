#!/usr/bin/env bash
# ============================================================================
# Environment exports for OpenClaw with LLM Circuit Breaker
# ============================================================================
# Source this file before launching openclaw:
#   source examples/openclaw_env.sh

export OPENAI_BASE_URL="http://127.0.0.1:4001/v1"
export OPENAI_API_KEY="sk-circuit-breaker-token"
export OPENAI_MODEL_NAME="openclaw-default"

echo "✔ OpenClaw environment configured for LLM Circuit Breaker (http://127.0.0.1:4001/v1)"
