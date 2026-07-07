"""Pluggable LLM providers.

Anthropic (Claude) uses the official SDK. Every other provider speaks the
OpenAI-compatible chat-completions protocol over httpx — which covers
OpenAI, Google Gemini, OpenRouter, Groq, a local Ollama, and any custom
endpoint (LM Studio, Together, DeepSeek, vLLM, ...).

Configuration lives in the settings DB (key 'llm', editable in the UI);
environment variables are the fallback for API keys. With nothing
configured the app still works — callers fall back to templates.
"""
import json
import os

import httpx

from .database import get_db

try:
    import anthropic
    _HAS_ANTHROPIC_SDK = True
except ImportError:
    _HAS_ANTHROPIC_SDK = False

# Providers other than 'anthropic' are OpenAI-compatible: POST {base_url}/chat/completions.
PROVIDERS = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "default_model": "claude-opus-4-8",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": None,
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-5.1",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    },
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    "openrouter": {
        "label": "OpenRouter",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
    },
    "groq": {
        "label": "Groq",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "ollama": {
        "label": "Ollama (local, free)",
        "default_model": "llama3.2",
        "env_key": None,          # local server — no key needed
        "base_url": "http://localhost:11434/v1",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "default_model": "",
        "env_key": "LLM_API_KEY",
        "base_url": "",
    },
}

DEFAULT_LLM_CONFIG = {"provider": "anthropic", "model": "", "api_key": "", "base_url": ""}


# ---------------------------------------------------------------- config

def get_llm_config() -> dict:
    """Stored config with defaults filled in. api_key here is the real one —
    mask it before returning to the browser."""
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'llm'").fetchone()
    cfg = dict(DEFAULT_LLM_CONFIG)
    if row:
        try:
            cfg.update(json.loads(row["value"]))
        except json.JSONDecodeError:
            pass
    if cfg["provider"] not in PROVIDERS:
        cfg["provider"] = "anthropic"
    return cfg


def save_llm_config(cfg: dict):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('llm', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(cfg),),
        )


def _resolved(cfg: dict | None = None) -> dict:
    """Effective provider/model/key/base_url after defaults + env fallback."""
    cfg = cfg or get_llm_config()
    spec = PROVIDERS[cfg["provider"]]
    env_key = spec["env_key"]
    return {
        "provider": cfg["provider"],
        "model": cfg.get("model") or spec["default_model"],
        "api_key": cfg.get("api_key") or (os.environ.get(env_key, "") if env_key else ""),
        "base_url": (cfg.get("base_url") or spec["base_url"] or "").rstrip("/"),
    }


def available(cfg: dict | None = None) -> bool:
    r = _resolved(cfg)
    if r["provider"] == "anthropic":
        if not _HAS_ANTHROPIC_SDK:
            return False
        # The SDK also resolves ANTHROPIC_AUTH_TOKEN and `ant auth login` profiles.
        return bool(
            r["api_key"]
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.path.exists(os.path.expanduser("~/.config/anthropic"))
        )
    if r["provider"] == "ollama":
        return True  # local server, no key — the Test button verifies reachability
    if r["provider"] == "custom":
        return bool(r["base_url"])
    return bool(r["api_key"])


def status() -> dict:
    """Safe-for-browser summary of the active provider."""
    cfg = get_llm_config()
    r = _resolved(cfg)
    return {
        "provider": r["provider"],
        "model": r["model"],
        "base_url": cfg.get("base_url", ""),
        "api_key_set": bool(r["api_key"]),
        "available": available(cfg),
        "providers": {k: {"label": v["label"], "default_model": v["default_model"],
                          "default_base_url": v["base_url"] or "", "needs_key": bool(v["env_key"])}
                      for k, v in PROVIDERS.items()},
    }


# ---------------------------------------------------------------- completion

def complete(system: str, user: str, max_tokens: int = 2048,
             json_schema: dict | None = None) -> str | None:
    """One-shot completion on the configured provider.
    Returns the text, or None when no provider is usable / the call fails
    (callers fall back to templates)."""
    r = _resolved()
    if not available():
        return None
    try:
        if r["provider"] == "anthropic":
            return _complete_anthropic(r, system, user, max_tokens, json_schema)
        return _complete_openai_compat(r, system, user, json_schema)
    except Exception:
        return None


def try_complete(system: str, user: str, max_tokens: int = 2048) -> tuple[bool, str]:
    """Like complete(), but surfaces the error — used by the Test button."""
    r = _resolved()
    if not available():
        return False, "No provider configured — pick one and add an API key in Settings."
    try:
        if r["provider"] == "anthropic":
            text = _complete_anthropic(r, system, user, max_tokens, None)
        else:
            text = _complete_openai_compat(r, system, user, None)
        if not text:
            return False, "Provider returned an empty response."
        return True, text
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:300]
        return False, f"{e.response.status_code} from {r['provider']}: {detail}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _complete_anthropic(r: dict, system: str, user: str,
                        max_tokens: int, json_schema: dict | None) -> str | None:
    client = anthropic.Anthropic(api_key=r["api_key"] or None)
    kwargs: dict = {
        "model": r["model"],
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if json_schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
    resp = client.messages.create(**kwargs)
    return next((b.text for b in resp.content if b.type == "text"), "").strip() or None


def _complete_openai_compat(r: dict, system: str, user: str,
                            json_schema: dict | None) -> str | None:
    if not r["base_url"]:
        return None
    if json_schema is not None:
        # response_format json_object is widely (not universally) supported;
        # the explicit schema in the prompt is what actually does the work.
        user += (
            "\n\nRespond with ONLY valid JSON matching this schema — "
            "no code fences, no commentary:\n" + json.dumps(json_schema)
        )
    body: dict = {
        "model": r["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_schema is not None:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if r["api_key"]:
        headers["Authorization"] = f"Bearer {r['api_key']}"
    resp = httpx.post(f"{r['base_url']}/chat/completions", json=body,
                      headers=headers, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return (content or "").strip() or None


def parse_json_response(text: str) -> dict | None:
    """Lenient JSON parse — strips markdown code fences some models emit."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip().rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # last resort: grab the outermost JSON object
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None
