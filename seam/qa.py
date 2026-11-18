"""Grounded Q&A: answer a question ONLY from the provided documents and data, or say it can't be answered.

The corpus is what the tool was given: every HR / Finance / Legal / Product file (policies, rosters,
contracts, budgets, approvals, the product record), the event stream, and the current audit results
(seams and department findings). Nothing else is used: no outside knowledge.

    answer(engine, "When does Meera Iyer leave?")
      -> {"answerable": True,  "answer": "...", "citations": [{"source", "quote"}], "via": "llm" | "extract"}
      -> {"answerable": False, "message": NOT_ANSWERABLE, "via": "none"}

Flow: retrieve the most relevant passages (BM25, no extra dependencies) -> if a language model is
configured, it writes the answer but must quote the passages word for word, and every quote is checked
against the passage text (an answer with no verifiable quote is rejected, so it cannot invent facts) ->
without a model, or if the model's answer fails the check, the closest passages are shown as-is.
If nothing in the corpus covers the question, the answer is the fixed "cannot be answered" message.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Callable

from .llm import parse_json

NOT_ANSWERABLE = (
    "This question can't be answered from the documents or data provided. I can only answer from the HR, "
    "Finance and Legal files loaded in this tool (policies, roster, training, budgets, purchase orders, "
    "contracts, approvals, the product record and the event stream) and the current audit results, and "
    "none of them cover this. Try asking about something in those files, for example “What is the approval "
    "limit for E008?”, “When does Meera Iyer leave?” or “What does the Conduct Policy say about training?”"
)

STOP = set("""a an and are as at be been being but by can could did do does for from had has have how i if in into is it its
me my of on or our please should so than that the their them then there these they this those to us was we were what when
where which who whom whose why will with would you your show tell give list explain about also any all some more most
""".split())
MIN_COVERAGE = 0.6        # share of the question's key words one passage must contain to answer without a model
TOP_K = 8


# ---------------------------------------------------------------- text helpers

def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())]


STOP_STEMS = STOP | {_stem(s) for s in STOP}


def key_terms(question: str) -> list[str]:
    return [t for t in dict.fromkeys(tokens(question)) if t not in STOP_STEMS and not (len(t) == 1 and t.isalpha())]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _flat(x: Any) -> str:
    if isinstance(x, dict):
        return "; ".join(f"{k}: {_flat(v)}" for k, v in x.items() if v not in ("", None))
    if isinstance(x, list):
        return ", ".join(_flat(i) for i in x)
    return str(x)


# ---------------------------------------------------------------- corpus

def _md_chunks(file: str, text: str) -> list[dict]:
    out, heading, buf = [], "", []

    def flush():
        para = " ".join(buf).strip()
        if para:
            clause = re.match(r"\*\*([\w.\-]+)\*\*", para)
            src = f"{file} › {heading}" if heading else file
            out.append({"source": src + (f" cl. {clause.group(1)}" if clause else ""),
                        "text": f"{heading}: {para}" if heading else para})
        buf.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip()
        elif not line.strip():
            flush()
        else:
            buf.append(line.strip())
    flush()
    return out


def _json_chunks(file: str, obj: Any) -> list[dict]:
    if not isinstance(obj, dict):
        return [{"source": file, "text": _flat(obj)}]
    out, scalars = [], {k: v for k, v in obj.items() if not isinstance(v, (dict, list))}
    if scalars:
        out.append({"source": file, "text": _flat(scalars)})
    for k, v in obj.items():
        if isinstance(v, list):
            for i, item in enumerate(v):
                label = item.get("id", i) if isinstance(item, dict) else i
                out.append({"source": f"{file}#{k}/{label}", "text": f"{k} {label}: {_flat(item)}"})
        elif isinstance(v, dict):
            out.append({"source": f"{file}#{k}", "text": f"{k}: {_flat(v)}"})
    return out


def build_corpus(engine) -> list[dict]:
    """Every passage the tool is allowed to answer from. Reads the live dataset, so applied events show up."""
    chunks: list[dict] = []
    ds = getattr(engine, "dataset", None)
    if ds is not None:
        for f, text in ds.texts.items():
            chunks += _md_chunks(f, text)
        for f, rows in ds.tables.items():
            stem = f.split("/")[-1].rsplit(".", 1)[0].replace("_", " ")
            for r in rows:
                key = next(iter(r.values()), "")
                chunks.append({"source": f"{f}#{key}", "text": _flat(r), "extra": f"{stem} {f}"})
        for f, doc in ds.docs.items():
            chunks += _json_chunks(f, doc)
        for f, up in ds.uploads.items():          # files a person added through the UI
            if up["kind"] == "document":
                chunks += _md_chunks(f, up["text"])
            elif up["kind"] == "table":
                stem = f.split("/")[-1].rsplit(".", 1)[0].replace("_", " ")
                for r in up["rows"]:
                    chunks.append({"source": f"{f}#{next(iter(r.values()), '')}", "text": _flat(r), "extra": f"{stem} {f}"})
            else:
                chunks += _json_chunks(f, up["json"])
        for ev in ds.events:
            chunks.append({"source": f"events/event_stream.json#{ev.get('event_id')}",
                           "text": f"event {ev.get('event_id')} on {ev.get('date')}: {ev.get('description')}"})
    p = engine.passport()
    chunks.append({"source": "audit result: overall", "text":
                   f"Overall launch status for {p['product']['name']} v{p['product']['version']} (launch "
                   f"{p['product']['launch_date']}, as of {p['as_of']}): {p['overall']}. " +
                   "; ".join(f"{n} {d['status']}" for n, d in p["departments"].items())})
    for s in p["seams"]:
        facts = {k: v for k, v in s["facts"].items() if k not in ("score_reasons", "explained_by")}
        chunks.append({"source": f"audit result: {s['id']}", "text":
                       f"{s['title']}. {s['explanation']} Severity {s['severity']}, status {s['status']}. "
                       f"Departments: {', '.join(s['departments'])}. Fix options: {'; '.join(s['fix_options'])}. "
                       f"Facts: {_flat(facts)}", "extra": "seam finding gap issue"})
    for name, d in p["departments"].items():
        for f in d.get("findings", []):
            chunks.append({"source": f"audit result: {name} {f['record']}", "text":
                           f"{name} check {f['record']} {f.get('result', '')}: {f['finding']}. "
                           f"{'; '.join(f.get('items', []))}", "extra": "finding check result"})
    return chunks


# ---------------------------------------------------------------- retrieval (BM25)

def retrieve(question: str, chunks: list[dict], k: int = TOP_K) -> dict[str, Any]:
    terms = key_terms(question)
    docs = [Counter(tokens(c["text"] + " " + c.get("extra", ""))) for c in chunks]
    n = len(docs) or 1
    df = Counter(t for d in docs for t in d)
    known = [t for t in terms if df[t]]
    avg = sum(sum(d.values()) for d in docs) / n or 1
    scored = []
    for c, d in zip(chunks, docs):
        length, s = sum(d.values()), 0.0
        for t in known:
            if d[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * 2.5 / (d[t] + 1.5 * (0.25 + 0.75 * length / avg))
        if s > 0:
            scored.append((s, c, sum(1 for t in terms if d[t]) / (len(terms) or 1)))
    scored.sort(key=lambda x: -x[0])
    top = scored[:k]
    return {"terms": terms, "known": known, "hits": [c for _, c, _ in top],
            "best_coverage": max((cov for _, _, cov in top), default=0.0)}


# ---------------------------------------------------------------- answering

PROMPT = """You answer an auditor's question using ONLY the numbered passages below. They come from a company's HR,
Finance and Legal files and its current audit results. Use no outside knowledge and never guess.
If the passages do not directly contain the answer, say so.
Return ONLY JSON: {{"answerable": true | false, "answer": "<short plain-English answer>",
"citations": [{{"passage": <number>, "quote": "<words copied exactly from that passage>"}}]}}
Rules: every claim in the answer needs a citation; quotes must be copied word for word; when the passages
do not answer the question set "answerable" to false and "answer" to "".
Question: {question}
Passages:
{passages}"""


def _declined() -> dict[str, Any]:
    return {"answerable": False, "answer": "", "message": NOT_ANSWERABLE, "citations": [], "via": "none"}


def _extract(hits: list[dict]) -> dict[str, Any]:
    return {"answerable": True, "via": "extract", "message": None,
            "answer": "No language model is available to write an answer, so here are the closest passages "
                      "from the documents and data:",
            "citations": [{"source": h["source"], "quote": h["text"][:400]} for h in hits[:3]]}


def _verified(raw: Any, hits: list[dict]) -> dict[str, Any] | None:
    """Accept the model's answer only if at least one quote really appears in the passage it cites."""
    try:
        out = parse_json(raw)
        if not out.get("answerable") or not str(out.get("answer", "")).strip():
            return {"answerable": False}
        cites = []
        for c in out.get("citations", []):
            i = int(c["passage"]) - 1
            quote = str(c["quote"]).strip()
            if 0 <= i < len(hits) and quote and _norm(quote) in _norm(hits[i]["text"]):
                cites.append({"source": hits[i]["source"], "quote": quote})
        if not cites:
            return None
        return {"answerable": True, "answer": str(out["answer"]).strip(), "citations": cites, "via": "llm", "message": None}
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def answer(engine, question: str, llm: Callable[[str], str] | None = None) -> dict[str, Any]:
    llm = llm if llm is not None else getattr(engine, "llm", None)
    r = retrieve(question, build_corpus(engine))
    if not r["known"] or not r["hits"]:
        return _declined()                                  # no key word of the question appears in the documents
    if llm is not None:
        passages = "\n".join(f"[{i}] ({h['source']}) {h['text']}" for i, h in enumerate(r["hits"], 1))
        try:
            res = _verified(llm(PROMPT.format(question=question.strip(), passages=passages)), r["hits"])
        except Exception:                                   # offline cache miss, provider error, ...
            res = None
        if res is not None:
            return res if res["answerable"] else _declined()
    if r["best_coverage"] >= MIN_COVERAGE:
        return _extract(r["hits"])
    return _declined()
