"""src/answer_schema.py — Answer JSON validator.

Required answer format from the assignment:

    {
      "answer": "Answer supported by retrieved evidence.",
      "sources": [{"book_id": "...", "page": 143, "chunk_id": "..."}],
      "insufficient_evidence": false
    }

We allow but do not require the optional extension keys "conflicts" (list of
strings) and "mode" (inference-path label: "local-llm" | "extractive" |
"hosted-approved") so that the UI can surface conflicts and demote/instrument
the answer while still validating against the strict 3-key contract of the
assignment. Use to_contract_payload() to strip extensions before sending the
answer to the 130-group router.
"""
from __future__ import annotations

from typing import Any


def validate_answer(obj: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["answer payload is not a JSON object"]
    for key in ("answer", "sources", "insufficient_evidence"):
        if key not in obj:
            errs.append(f"missing required key: {key}")
    if not isinstance(obj.get("answer"), str) or not obj.get("answer", "").strip():
        errs.append("'answer' must be a non-empty string")
    if not isinstance(obj.get("sources"), list):
        errs.append("'sources' must be a list")
    else:
        for s in obj["sources"]:
            if not isinstance(s, dict):
                errs.append("each source must be an object")
                continue
            for key in ("book_id", "page", "chunk_id"):
                if key not in s:
                    errs.append(f"each source must include '{key}'")
            if "page" in s and not (isinstance(s["page"], int) or s["page"] is None):
                errs.append("'page' must be an int or null")
    if not isinstance(obj.get("insufficient_evidence"), bool):
        errs.append("'insufficient_evidence' must be a bool")
    if obj.get("insufficient_evidence") is True and obj.get("sources") not in ([], None):
        # Abstention means we must not present evidence we failed to ground;
        # empty list is the contract when the model chooses to abstain.
        errs.append("'insufficient_evidence': true requires sources to be []")
    allowed = {"answer", "sources", "insufficient_evidence", "conflicts", "mode"}
    extra = set(obj.keys()) - allowed
    if extra:
        errs.append(f"unexpected keys: {sorted(extra)}")
    return errs


def to_contract_payload(payload: dict) -> dict:
    """Strip optional extension keys, returning the strict 3-key contract JSON.

    The 130-group router and the evaluation runner expect exactly
    {answer, sources, insufficient_evidence}. Extension keys ("conflicts",
    "mode") are for local display only and must never leak into the shared
    interface response.
    """
    return {"answer": payload["answer"],
            "sources": payload["sources"],
            "insufficient_evidence": payload["insufficient_evidence"]}


def is_contradictory(a_text: str, b_text: str) -> bool:
    """Very lightweight heuristic: opposite polarities on numbers/currency.

    Real conflict detection is handled by the human review step; this is a
    cheap guard so obviously conflicting retrieved passages are surfaced.
    """
    neg = ("not ", "cannot", "cannot", "does not", "do not", "never",
           "no such", "impossible")
    a_low, b_low = a_text.lower(), b_text.lower()
    if any(n in a_low for n in neg) and not any(n in b_low for n in neg):
        return True
    if any(n in b_low for n in neg) and not any(n in a_low for n in neg):
        return True
    return False
