"""Distillr: trim what is irrelevant, encode what is left efficiently, and account for every token saved.

import distillr
result = distillr.compress(rows, query="orders shipped to Berlin", top_k=20)
print(result.savings_pct, result.text)
flags = result.check_answer(model_answer)
"""

from .core import (
    AuditFlag,
    AuditStage,
    CompressionResult,
    EncodeStage,
    Ledger,
    Payload,
    Pipeline,
    Removal,
    RetrieveStage,
    SemanticStage,
    StageReport,
    check_answer,
    compress,
    load,
    toon,
    wrap,
)

__version__ = "0.1.0"
__all__ = [
    "AuditFlag",
    "AuditStage",
    "CompressionResult",
    "EncodeStage",
    "Ledger",
    "Payload",
    "Pipeline",
    "Removal",
    "RetrieveStage",
    "SemanticStage",
    "StageReport",
    "__version__",
    "check_answer",
    "compress",
    "load",
    "toon",
    "wrap",
]
