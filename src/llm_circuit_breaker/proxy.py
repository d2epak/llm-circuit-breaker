"""Local Proxy Bridge for Claude Code, Cursor, and Aider."""

from __future__ import annotations
import os
import sys
import logging
from typing import Optional

try:
    from fastapi import FastAPI, Request, Response
    import uvicorn
    import httpx
except ImportError:
    FastAPI = None

from llm_circuit_breaker.router import UniversalFailoverRouter
from llm_circuit_breaker.classifier import classify_api_error, FailoverReason

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("llm_proxy")


def create_proxy_app(router: Optional[UniversalFailoverRouter] = None) -> FastAPI:
    if FastAPI is None:
        raise ImportError("FastAPI, uvicorn, and httpx are required for the proxy. Install with: pip install 'llm-circuit-breaker[proxy]'")

    app = FastAPI(title="LLM Circuit Breaker Proxy", version="0.1.0")
    active_router = router or UniversalFailoverRouter(configured_fallbacks=[
        {"provider": "nvidia", "model": "nvidia/nemotron-3-ultra-550b-a55b", "base_url": "https://integrate.api.nvidia.com/v1", "key_env": "NVIDIA_API_KEY"},
        {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
    ])

    @app.post("/v1/chat/completions")
    @app.post("/v1/messages")
    async def proxy_completion(request: Request):
        body = await request.json()
        max_retries = len(active_router.fallback_chain) * 2
        attempts = 0

        while attempts < max_retries:
            route = active_router.active_provider
            api_key = route.get("api_key") or os.getenv(route.get("key_env", ""), "")
            target_url = f"{route['base_url'].rstrip('/')}/chat/completions"

            # Re-map model if route dictates
            payload = dict(body)
            payload["model"] = route["model"]

            # Scrub vendor proprietary extra parameters if switching away
            if "thinking" in payload and route.get("provider") not in ("anthropic", "openrouter"):
                payload.pop("thinking", None)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(target_url, json=payload, headers=headers)

                    if resp.status_code == 200:
                        return Response(content=resp.content, status_code=200, media_type="application/json")

                    err = Exception(resp.text)
                    classified = classify_api_error(err, status_code=resp.status_code)
                    logger.warning("Provider %s failed with %s (%d). Triggering failover...", route['provider'], classified.reason, resp.status_code)

                    if not classified.should_fallback:
                        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

                    if classified.reason in (FailoverReason.rate_limit, FailoverReason.upstream_rate_limit):
                        active_router.mark_cooldown(route["provider"], seconds=60.0)
                    elif classified.reason == FailoverReason.model_not_found:
                        active_router.mark_deprecated(route["model"])

                    next_route = active_router.get_next_available_route(reason=classified.reason)
                    if not next_route:
                        return Response(content=b'{"error": "All LLM fallback providers exhausted"}', status_code=503, media_type="application/json")
                    attempts += 1

            except Exception as e:
                classified = classify_api_error(e)
                logger.error("Transport error on %s: %s. Failing over...", route['provider'], e)
                active_router.get_next_available_route(reason=classified.reason)
                attempts += 1

        return Response(content=b'{"error": "Failed to obtain response from any provider"}', status_code=504, media_type="application/json")

    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run local LLM circuit breaker proxy")
    parser.add_argument("--port", type=int, default=8000, help="Proxy port (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    args = parser.parse_args()

    app = create_proxy_app()
    print(f"🚀 LLM Circuit Breaker Proxy running at http://{args.host}:{args.port}")
    print("👉 Point Claude Code, Cursor, or Aider to http://127.0.0.1:8000/v1\n")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
