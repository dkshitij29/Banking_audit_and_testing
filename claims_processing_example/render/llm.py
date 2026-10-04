"""The one place this repo talks to an LLM: a small OpenRouter client, cached.

Nothing here decides anything. The model is asked for prose, never for a fact, a
number or a label (render/documents.py), and the result is checked before it
reaches a document.

Three things make renders reproducible and cheap:

- **Cache.** A reply is stored under the hash of the exact request (model,
  parameters, prompt). The same case renders the same way forever, and
  regenerating a dataset costs nothing. Deleting the cache is the only way to
  spend money on a case twice.
- **Deterministic settings.** Temperature 0, top_p 1, a fixed seed, reasoning
  off. Models still drift between versions, which is what the cache is for.
- **A ledger with a cap.** Every call appends its tokens and cost to a ledger,
  and a call that would take the total past the cap is refused before it is
  sent. See BUDGET_USD.

The API key is read from OPENROUTER_API_KEY, in the environment or in a .env
file that git ignores. It is never logged, never written to the cache, and
never printed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".render-cache"
LEDGER = CACHE_DIR / "spend.jsonl"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "deepseek/deepseek-v4.1-flash"
BUDGET_USD = 9.00
"""Stop well short of the $10 loaded, so a long run cannot overshoot it."""

PRICES_PER_MTOK = {  # OpenRouter list prices, for the estimate before a call
    "deepseek/deepseek-v4.1-flash": (0.14, 0.42),
}
DEFAULT_PRICE = (1.00, 5.00)
"""Used for an unknown model: dear enough that the cap still protects us."""

STUB_MODEL = "STUB_NO_LLM"
"""Marks prose written by stub_transport, not by a model. Never releasable."""


class BudgetExhausted(RuntimeError):
    """The cap would be passed. Raise the cap deliberately or stop."""


class MissingApiKey(RuntimeError):
    """No key, and the reply is not cached."""


class LlmError(RuntimeError):
    """The model returned something unusable."""


class AccessDenied(LlmError):
    """The provider refused the key: no credit, a spend cap, or a key that has
    been disabled. An account to sort out, not a bug, and nothing was spent."""


def read_api_key(env_file: Path = ROOT / ".env") -> str | None:
    """OPENROUTER_API_KEY from the environment, or from .env. Never logged."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip() or None
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY":
            return value.strip().strip("'\"") or None
    return None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    @classmethod
    def of(cls, model: str, usage: dict) -> Usage:
        """What a reply cost. OpenRouter reports the real cost; otherwise estimate."""
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        cost = usage.get("cost")
        if cost is None:
            cost = estimate(model, prompt, completion)
        return cls(prompt, completion, float(cost))


def estimate(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = PRICES_PER_MTOK.get(model, DEFAULT_PRICE)
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


class Budget:
    """The ledger, and the cap it enforces."""

    def __init__(self, path: Path = LEDGER, cap_usd: float = BUDGET_USD) -> None:
        self.path, self.cap_usd = path, cap_usd

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def spent(self) -> float:
        return sum(entry["cost_usd"] for entry in self.entries())

    def check(self, model: str, prompt_tokens: int, max_tokens: int) -> None:
        """Refuse before sending, costing the reply at its longest."""
        worst = estimate(model, prompt_tokens, max_tokens)
        spent = self.spent()
        if spent + worst > self.cap_usd:
            raise BudgetExhausted(
                f"spent ${spent:.4f}; this call could cost ${worst:.4f}, over the ${self.cap_usd:.2f} cap"
            )

    def record(self, model: str, usage: Usage, cache_key: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "model": model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": round(usage.cost_usd, 6),
            "cache_key": cache_key,
        }
        with self.path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(entry) + "\n")


Transport = Callable[[dict, str], dict]
"""(request body, api key) -> the API's parsed JSON reply."""


def http_transport(body: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "claims-benchmark document rendering",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:  # the body says why; it never holds the key
        detail = f"HTTP {error.code}: {error.read()[:400].decode(errors='replace')}"
        raise (AccessDenied(detail) if error.code in (401, 402, 403) else LlmError(detail)) from None


class Client:
    """Asks for one JSON object, to a schema. Cached, budgeted, deterministic."""

    def __init__(
        self,
        *,
        model: str = MODEL,
        cache_dir: Path = CACHE_DIR,
        budget: Budget | None = None,
        api_key: str | None = None,
        transport: Transport = http_transport,
        seed: int = 7,
        max_tokens: int = 900,
    ) -> None:
        self.model, self.cache_dir, self.transport = model, cache_dir, transport
        self.budget = budget if budget is not None else Budget()
        self.api_key, self.seed, self.max_tokens = api_key, seed, max_tokens

    def body(self, system: str, prompt: str, schema: dict, name: str, seed: int | None = None) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "top_p": 1,
            "seed": self.seed if seed is None else seed,
            "max_tokens": self.max_tokens,
            "reasoning": {"enabled": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            },
            "usage": {"include": True},
        }

    @staticmethod
    def cache_key(body: dict) -> str:
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32]

    def cached(self, key: str) -> dict | None:
        path = self.cache_dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def complete(self, *, system: str, prompt: str, schema: dict, name: str,
                 seed: int | None = None) -> tuple[dict, dict]:
        """The model's JSON object, and the cache entry it came from.

        A cached reply costs nothing and is returned as it stands. `seed` overrides
        the client's: at temperature 0 the same request gives the same reply, so a
        second attempt at prose that came back unusable has to ask differently.
        """
        body = self.body(system, prompt, schema, name, seed)
        key = self.cache_key(body)
        entry = self.cached(key)
        if entry is not None:
            return entry["content"], entry

        api_key = self.api_key if self.api_key is not None else read_api_key()
        if not api_key:
            raise MissingApiKey(
                "no OPENROUTER_API_KEY (environment or .env), and this render is not cached. "
                "Put the key in .env, which git ignores."
            )
        self.budget.check(self.model, len(prompt) // 4 + len(system) // 4, self.max_tokens)
        reply = self.transport(body, api_key)
        content = _content(reply)
        usage = Usage.of(self.model, reply.get("usage") or {})
        self.budget.record(self.model, usage, key)
        entry = {
            "model": self.model,
            "prompt_name": name,
            "content": content,
            "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
                      "cost_usd": round(usage.cost_usd, 6)},
            "created": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        return content, entry


def _content(reply: dict) -> dict:
    try:
        choice = reply["choices"][0]
    except (KeyError, IndexError):
        raise LlmError(f"no choices in the reply: {json.dumps(reply)[:300]}") from None
    if choice.get("finish_reason") == "length":
        raise LlmError("the reply was cut off by max_tokens")
    text = (choice.get("message") or {}).get("content")
    if not text:
        raise LlmError("the reply carried no content")
    try:
        content = json.loads(text)
    except json.JSONDecodeError:
        raise LlmError(f"the reply was not JSON: {text[:300]}") from None
    if not isinstance(content, dict):
        raise LlmError(f"the reply was not a JSON object: {text[:200]}")
    return content


def stub_transport(body: dict, api_key: str) -> dict:
    """Offline stand-in: fills every string field of the schema with a fixed line.

    It lets the whole pipeline run and be tested without a key or a rupee. The
    prose is obviously not a document, and a dataset rendered with it is marked
    unreleasable (render/documents.py).
    """
    schema = body["response_format"]["json_schema"]["schema"]
    content = {name: f"[{STUB_MODEL}] {name.replace('_', ' ')} not written." for name in schema["properties"]}
    prompt = sum(len(message["content"]) for message in body["messages"]) // 4
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": 0, "cost": 0.0},
    }


def stub_client(**kwargs) -> Client:
    return Client(model=STUB_MODEL, transport=stub_transport, api_key="stub", **kwargs)
