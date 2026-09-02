"""Automated Model Discovery & Catalog Maintenance Engine.

Discovers $0 free models, validates tool-calling support and context window,
tracks upstream deprecations, and persists a local model catalog.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("llm_circuit_breaker.discovery")

_OPENROUTER_CATALOG_URL = "https://openrouter.ai/api/v1/models"
_DEFAULT_CATALOG_PATH = Path(os.path.expanduser("~/.hermes/model_catalog.json"))
_MIN_CONTEXT_LENGTH = 16384


def is_model_free(pricing: Any) -> bool:
    """Return True if prompt, completion, request, and image pricing are $0."""
    if not isinstance(pricing, dict):
        return False
    try:
        p = float(pricing.get("prompt", "0") or 0)
        c = float(pricing.get("completion", "0") or 0)
        r = float(pricing.get("request", "0") or 0)
        i = float(pricing.get("image", "0") or 0)
        return p == 0 and c == 0 and r == 0 and i == 0
    except (TypeError, ValueError):
        return False


def supports_tool_calling(item: dict[str, Any]) -> bool:
    """Return True if the model advertises tool calling capabilities."""
    if not isinstance(item, dict):
        return True
    params = item.get("supported_parameters")
    if not isinstance(params, list):
        return True  # Permissive if metadata is omitted
    return "tools" in params


def fetch_openrouter_catalog(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Fetch live catalog from OpenRouter."""
    req = urllib.request.Request(
        _OPENROUTER_CATALOG_URL,
        headers={"User-Agent": "llm-circuit-breaker/0.1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception as e:
        logger.warning("Failed to fetch model catalog: %s", e)
        return []


def discover_models(
    force: bool = False,
    min_context: int = _MIN_CONTEXT_LENGTH,
    catalog_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Discover free models, track deprecations, and save catalog snapshot."""
    path = catalog_path or _DEFAULT_CATALOG_PATH
    existing_catalog = load_model_catalog(path)

    if not force and existing_catalog:
        last_updated = existing_catalog.get("last_updated_epoch", 0)
        if (time.time() - last_updated) < 86400 and existing_catalog.get("free_models"):
            return existing_catalog

    raw_models = fetch_openrouter_catalog()
    if not raw_models and existing_catalog:
        return existing_catalog

    known_prev_ids: Set[str] = set()
    if existing_catalog:
        for m in existing_catalog.get("free_models", []):
            known_prev_ids.add(m.get("id", ""))

    active_free: List[Dict[str, Any]] = []
    current_ids: Set[str] = set()

    for item in raw_models:
        mid = item.get("id")
        if not mid:
            continue
        current_ids.add(mid)

        pricing = item.get("pricing", {})
        context_len = int(item.get("context_length", 0) or 0)
        is_free = is_model_free(pricing) or mid.endswith(":free")

        if is_free and supports_tool_calling(item) and context_len >= min_context:
            active_free.append({
                "id": mid,
                "name": item.get("name") or mid,
                "provider": "openrouter",
                "context_length": context_len,
                "pricing": {"prompt": "0", "completion": "0"},
                "supports_tools": True,
                "description": item.get("description", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })

    # Rank models: prioritize high-context and well-tested model architectures
    def _rank(m: dict[str, Any]) -> int:
        mid = m["id"].lower()
        score = 0
        if "llama-3" in mid or "llama3" in mid: score += 100
        elif "qwen" in mid: score += 90
        elif "deepseek" in mid: score += 80
        elif "mistral" in mid or "gemma" in mid: score += 70
        score += min(m.get("context_length", 0) // 1000, 100)
        return score

    active_free.sort(key=_rank, reverse=True)

    # Deprecation tracking
    existing_deprecated = set(existing_catalog.get("deprecated_models", []) if existing_catalog else [])
    newly_deprecated = (known_prev_ids - current_ids) if (known_prev_ids and current_ids) else set()
    all_deprecated = sorted(list(existing_deprecated.union(newly_deprecated)))

    catalog = {
        "version": "1.0",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "last_updated_epoch": time.time(),
        "total_free_models_discovered": len(active_free),
        "total_deprecated_models_tracked": len(all_deprecated),
        "free_models": active_free,
        "deprecated_models": all_deprecated,
    }

    save_model_catalog(catalog, path)
    return catalog


def save_model_catalog(catalog: dict[str, Any], path: Optional[Path] = None) -> None:
    target = path or _DEFAULT_CATALOG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
    except Exception as e:
        logger.error("Failed to save catalog to %s: %s", target, e)


def load_model_catalog(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    target = path or _DEFAULT_CATALOG_PATH
    if not target.exists():
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_top_free_models(limit: int = 5, path: Optional[Path] = None) -> list[dict[str, Any]]:
    catalog = load_model_catalog(path) or discover_models(force=False, catalog_path=path)
    return catalog.get("free_models", [])[:limit]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Discover 100% free models and update local catalog")
    parser.add_argument("--force", action="store_true", help="Force refresh catalog")
    parser.add_argument("--limit", type=int, default=10, help="Number of models to display")
    args = parser.parse_args()

    print("🔍 Querying provider catalog...")
    cat = discover_models(force=args.force)
    print(f"✅ Discovered {cat['total_free_models_discovered']} free tool-capable models (>=16k context)")
    print(f"📦 Tracking {cat['total_deprecated_models_tracked']} deprecated models\n")
    print(f"Top {args.limit} Free Models:")
    for i, m in enumerate(cat.get("free_models", [])[:args.limit], 1):
        print(f"  {i}. {m['id']} ({m['context_length']:,} tokens context)")


if __name__ == "__main__":
    main()
