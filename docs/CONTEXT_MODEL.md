# Hierarchical Context Budgeting & Compaction Model

An authoritative guide to context estimation, token budgeting, and diagnostic extraction in **LLM Circuit Breaker (V3)**.

---

## 1. Context Budget Calculation

Before dispatching to an endpoint, the gateway computes the effective budget:

$$\text{AvailableBudget} = W_{\text{model}} - (T_{\text{desired\_output}} + T_{\text{safety\_margin}})$$

Where:
- $W_{\text{model}}$: Target endpoint's context window (e.g. 32,768 tokens).
- $T_{\text{desired\_output}}$: Reserved tokens for model generation (default 2,048).
- $T_{\text{safety\_margin}}$: Buffer for tokenization variance (default 512).

If estimated input tokens $T_{\text{input}} > \text{AvailableBudget}$, context compaction is triggered.

---

## 2. Hierarchical Compaction Priorities

Compaction proceeds through prioritized stages:

1. **Stage 1 — Immutable Preservation (Never Modified):**
   - System instruction (`system_instruction`).
   - Root user prompt / goal (`messages[0]`).
   - Recent agent turn history (`preserve_tail_turns = 2`).
2. **Stage 2 — Structured Tool Log Extraction:**
   - Multi-thousand-line shell outputs and stack traces in historical tool results are parsed.
   - The compactor extracts:
     - Exit code (`exit_code = 0` or nonzero).
     - Target file paths (`/var/log/syslog`).
     - Error diagnostics (`Connection refused`, `SyntaxError`).
   - The noisy payload is replaced with an explicit diagnostic summary, reducing token consumption by up to 90% while retaining full continuation context.
3. **Stage 3 — Middle Turn Summarization:**
   - Intermediate conversational turns between the root goal and tail turns are summarized into compact semantic milestones.
