from src.citations import extract_citations, validate_citations

PASSAGES = {
    "G014_BOOK_003_P143_C02": {"book_id": "G014_BOOK_003", "page": 143,
                               "title": "Fundamentals of Electric Circuits"},
    "G014_BOOK_005_P201_C02": {"book_id": "G014_BOOK_005", "page": 201,
                               "title": "Signals and Systems"},
}

RETRIEVED = [
    {"chunk_id": "G014_BOOK_003_P143_C02", "book_id": "G014_BOOK_003",
     "page": 143, "title": "Fundamentals of Electric Circuits", "text": "V=IR", "score": 0.9},
]


def test_extract_pulls_chunk_ids():
    text = "As stated in [G014_BOOK_003_P143_C02] and [G014_BOOK_005_P201_C02]."
    ids = extract_citations(text)
    assert ids == ["G014_BOOK_003_P143_C02", "G014_BOOK_005_P201_C02"]


def test_dedupes_citations():
    text = "Cite [G014_BOOK_003_P143_C02] twice: [G014_BOOK_003_P143_C02]."
    ids = extract_citations(text)
    assert ids == ["G014_BOOK_003_P143_C02"]


def test_validated_citations_are_kept_when_retrieved():
    text = "The law [G014_BOOK_003_P143_C02] governs this."
    srcs = validate_citations(text, RETRIEVED, PASSAGES)
    assert srcs == [{"book_id": "G014_BOOK_003", "page": 143,
                     "chunk_id": "G014_BOOK_003_P143_C02",
                     "title": "Fundamentals of Electric Circuits"}]


def test_invented_citation_is_rejected():
    text = "Completely [G014_BOOK_999_P999_C99] invented citation."
    srcs = validate_citations(text, RETRIEVED, PASSAGES)
    assert srcs == []


def test_citation_not_retrieved_this_question_is_rejected():
    text = "Refers to [G014_BOOK_005_P201_C02] which was not retrieved."
    srcs = validate_citations(text, RETRIEVED, PASSAGES)
    assert srcs == []


def test_page_drift_is_rejected():
    tampered = [dict(RETRIEVED[0])]
    tampered[0]["page"] = 999  # drifted from store
    text = "Law [G014_BOOK_003_P143_C02]."
    srcs = validate_citations(text, tampered, PASSAGES)
    assert srcs == []
