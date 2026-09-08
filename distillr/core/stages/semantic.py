"""Stage 2: semantic compression via LLMLingua-2 (Phase 1).

Optional dependency: `pip install distillr[semantic]`. The stage operates on the encoded text (or on the
string fields of structured data when `fields` is given) and records the dropped tokens as a single
Removal so the audit checker can still flag answers that lean on pruned content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import Context, Removal, StageReport, preview

DEFAULT_MODEL = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"


class SemanticUnavailable(RuntimeError):
    pass


@dataclass
class SemanticStage:
    rate: float = 0.5  # keep this fraction of tokens
    model: str = DEFAULT_MODEL
    force_tokens: tuple[str, ...] = ("\n", ":", ",", "[", "]", "{", "}")  # never prune structure
    name: str = field(default="semantic", init=False)
    _compressor: Any = field(default=None, init=False, repr=False)

    def available(self) -> bool:
        try:
            import llmlingua  # noqa: F401

            return True
        except ImportError:
            return False

    def _get(self):
        if self._compressor is None:
            try:
                from llmlingua import PromptCompressor
            except ImportError as e:  # pragma: no cover - exercised only without the extra
                raise SemanticUnavailable("LLMLingua-2 is not installed. Run: pip install 'distillr[semantic]'") from e
            self._compressor = PromptCompressor(model_name=self.model, use_llmlingua2=True)
        return self._compressor

    def run(self, data: Any, ctx: Context) -> tuple[Any, StageReport]:
        text = data if isinstance(data, str) else ctx.render(data)
        before = ctx.counter.count(text)
        out = self._get().compress_prompt(text, rate=self.rate, force_tokens=list(self.force_tokens))
        compressed = out["compressed_prompt"]
        after = ctx.counter.count(compressed)
        removals = []
        if after < before:
            # LLMLingua does not return the pruned spans; approximate the removed text as the set-difference of words.
            kept = set(compressed.split())
            dropped = " ".join(w for w in text.split() if w not in kept)
            removals.append(Removal(self.name, "tokens", "$", f"pruned to rate={self.rate}", preview(dropped, 400), before - after))
        return compressed, StageReport(self.name, before, after, removals, {"model": self.model, "rate": self.rate})
