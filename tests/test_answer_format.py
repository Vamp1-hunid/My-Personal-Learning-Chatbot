from src.answer_schema import validate_answer


def test_valid_payload_accepts():
    payload = {"answer": "V = I * R.",
               "sources": [{"book_id": "G014_BOOK_003", "page": 143,
                            "chunk_id": "G014_BOOK_003_P143_C02"}],
               "insufficient_evidence": False}
    assert validate_answer(payload) == []


def test_missing_key_rejected():
    assert validate_answer({"answer": "x", "sources": []}) != []


def test_bad_source_missing_chunk_id():
    payload = {"answer": "x",
               "sources": [{"book_id": "G014_BOOK_003", "page": 143}],
               "insufficient_evidence": False}
    errs = validate_answer(payload)
    assert any("chunk_id" in e for e in errs)


def test_abstention_with_sources_rejected():
    payload = {"answer": "x",
               "sources": [{"book_id": "b", "page": 1, "chunk_id": "c"}],
               "insufficient_evidence": True}
    errs = validate_answer(payload)
    assert any("sources" in e for e in errs)


def test_unexpected_keys_rejected():
    payload = {"answer": "x", "sources": [], "insufficient_evidence": False,
               "hidden": 1}
    errs = validate_answer(payload)
    assert any("hidden" in e for e in errs)


def test_conflicts_key_allowed():
    payload = {"answer": "x", "sources": [], "insufficient_evidence": False,
               "conflicts": ["Passages A and B disagree"]}
    assert validate_answer(payload) == []


def test_mode_key_allowed():
    payload = {"answer": "x", "sources": [], "insufficient_evidence": False,
               "mode": "extractive"}
    assert validate_answer(payload) == []


def test_contract_helper_strips_extensions():
    from src.answer_schema import to_contract_payload
    payload = {"answer": "x", "sources": [], "insufficient_evidence": False,
               "mode": "local-llm", "conflicts": ["A vs B"]}
    strict = to_contract_payload(payload)
    assert sorted(strict.keys()) == ["answer", "insufficient_evidence", "sources"]
    assert validate_answer(strict) == []


def test_contradiction_heuristic_flags_negation():
    from src.answer_schema import is_contradictory
    assert is_contradictory("It is NOT allowed.", "It is allowed.")
    assert is_contradictory("It is allowed.", "It is NOT allowed.")
    assert not is_contradictory("It is allowed.", "It is permitted.")
