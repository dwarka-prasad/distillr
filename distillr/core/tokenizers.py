"""Token counting.

Accuracy matters here: the whole product is "how many tokens did we save", so we use real tokenizers
(tiktoken) wherever possible and only fall back to a character heuristic when the encoding files
cannot be loaded (offline first run). The fallback is flagged so the ledger never presents an estimate
as a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

# model prefix -> tiktoken encoding. Anthropic/Gemini have no public tokenizer; cl100k is the closest
# approximation and is flagged as such in TokenCounter.exact.
MODEL_ENCODINGS: list[tuple[str, str, bool]] = [
    ("gpt-4o", "o200k_base", True),
    ("gpt-4.1", "o200k_base", True),
    ("o1", "o200k_base", True),
    ("o3", "o200k_base", True),
    ("o4", "o200k_base", True),
    ("gpt-4", "cl100k_base", True),
    ("gpt-3.5", "cl100k_base", True),
    ("text-embedding", "cl100k_base", True),
    ("claude", "cl100k_base", False),
    ("gemini", "cl100k_base", False),
    ("llama", "cl100k_base", False),
    ("mistral", "cl100k_base", False),
]
DEFAULT_ENCODING = "o200k_base"


@dataclass
class TokenCounter:
    """Counts tokens for one encoding. `exact` is False when we are approximating."""

    encoding: str = DEFAULT_ENCODING
    exact: bool = True

    def __post_init__(self) -> None:
        self._enc = _load_encoding(self.encoding)
        if self._enc is None:
            self.exact = False

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._enc is not None:
            return len(self._enc.encode(text, disallowed_special=()))
        # Heuristic: English prose is ~4 chars/token; JSON punctuation is denser, so weight structure.
        structural = sum(text.count(c) for c in '{}[]:,"')
        return math.ceil((len(text) - structural) / 4 + structural * 0.6)

    @property
    def label(self) -> str:
        return self.encoding + ("" if self.exact else " (approx)")


@lru_cache(maxsize=8)
def _load_encoding(name: str):
    try:
        import tiktoken

        return tiktoken.get_encoding(name)
    except Exception:  # noqa: BLE001 - missing package or no network for the BPE download
        return None


def for_model(model: str | None) -> TokenCounter:
    """Pick the right tokenizer for a model id ("gpt-4o-mini", "claude-sonnet-5", ...)."""
    if not model:
        return TokenCounter()
    m = model.lower()
    for prefix, enc, exact in MODEL_ENCODINGS:
        if m.startswith(prefix):
            c = TokenCounter(enc)
            c.exact = c.exact and exact
            return c
    return TokenCounter()


def for_encoding(name: str | None) -> TokenCounter:
    return TokenCounter(name or DEFAULT_ENCODING)
