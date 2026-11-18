"""Q&A is grounded: answers come only from the provided documents, otherwise a clear 'cannot be answered'."""
import json

import pytest

from seam.audit import ask, route
from seam.engine import Engine
from seam.governance import ROOT
from seam.llm import CachedLLM
from seam.qa import NOT_ANSWERABLE, answer, build_corpus, key_terms


@pytest.fixture(scope="module")
def eng(tmp_path_factory):
    d = tmp_path_factory.mktemp("qa")
    e = Engine(ROOT / "data", d / "a.jsonl", d / "s.json")
    e.run()
    return e


def test_corpus_covers_documents_and_audit_results(eng):
    sources = {c["source"] for c in build_corpus(eng)}
    assert "hr/roster.csv#E004" in sources and "finance/approval_limits.csv#E008" in sources
    assert any(s.startswith("legal/legal_policies_excerpt.md") for s in sources)
    assert any(s.startswith("audit result:") for s in sources)
    assert not any("answer_key" in s for s in sources)          # never answer from the grading key


def test_key_terms_drop_question_words_and_stray_letters():
    assert key_terms("What is Meera Iyer's favourite food?") == ["meera", "iyer", "favourite", "food"]


@pytest.mark.parametrize("q", ["What is the capital of France?", "Who won the world cup?", "What is the weather in London?",
                               "What is Meera Iyer's favourite food?", "Who is the CEO of Google?"])
def test_outside_the_documents_is_declined(eng, q):
    a = answer(eng, q)
    assert a["answerable"] is False and a["message"] == NOT_ANSWERABLE and a["citations"] == []


def test_document_question_without_a_model_shows_closest_passages(eng):
    a = answer(eng, "What is the approval limit for E008?", llm=None) if eng.llm is None else None
    assert a["answerable"] and a["via"] == "extract"
    assert any("E008" in c["quote"] and "50000" in c["quote"] for c in a["citations"])


def test_model_answer_is_accepted_only_with_a_verifiable_quote(eng):
    def good(prompt):
        assert "ONLY the numbered passages" in prompt
        return json.dumps({"answerable": True, "answer": "Yusuf Demir's limit is £50,000.",
                           "citations": [{"passage": 1, "quote": "limit_gbp: 50000"}]})
    a = answer(eng, "What is the approval limit for E008?", llm=good)
    assert a["via"] == "llm" and a["answerable"] and a["citations"][0]["quote"] == "limit_gbp: 50000"


def test_invented_quote_is_rejected_and_falls_back_to_the_documents(eng):
    def invented(prompt):
        return json.dumps({"answerable": True, "answer": "It is £1m.",
                           "citations": [{"passage": 1, "quote": "limit is one million pounds"}]})
    a = answer(eng, "What is the approval limit for E008?", llm=invented)
    assert a["via"] == "extract" and "one million" not in json.dumps(a)


def test_model_saying_not_answerable_is_respected(eng):
    a = answer(eng, "What is the approval limit for E008?",
               llm=lambda p: json.dumps({"answerable": False, "answer": "", "citations": []}))
    assert a["answerable"] is False and a["message"] == NOT_ANSWERABLE


def test_no_model_call_when_nothing_in_the_documents_matches(eng):
    calls = []
    a = answer(eng, "What is the capital of France?", llm=lambda p: calls.append(p) or "{}")
    assert not a["answerable"] and calls == []


def test_routing_separates_lookups_from_audits():
    assert route("What is the approval limit for E008?")["intent"] == "qa"
    assert route("Is HR compliant?")["intent"] == "audit"
    llm = CachedLLM(lambda p: json.dumps({"intent": "audit", "domains": ["Finance"]}), cache_dir=ROOT / "runs" / "_t")
    assert route("What is the approval limit for E008?", llm)["intent"] == "qa"   # a lookup is never an audit run


def test_ask_end_to_end_answers_declines_and_logs(eng):
    out = ask(eng, "When does Meera Iyer leave?")
    assert out["answer"]["answerable"] and any("E004" in c["source"] or "EV-05" in c["source"] for c in out["answer"]["citations"])
    out = ask(eng, "Who won the world cup?")
    assert out["answer"]["message"] == NOT_ANSWERABLE
    last = eng.audit.entries()[-1]
    assert last["kind"] == "audit_question" and last["data"]["answerable"] is False
