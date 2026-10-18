"""METHODOLOGY.md section 3 matching function and F13 scan diff."""
from app.research.matching import diff_scans, match_findings, normalize

TABLE = ["/users/{user_id}", "/documents/{doc_id}", "/health"]


def f(id, cat, route, method="GET", conf=0.5, **kw):
    return {"id": id, "category": cat, "route_template": route, "method": method,
            "confidence": {"score": conf}, **kw}


def test_normalize_uses_route_table_lowercases_and_strips():
    assert normalize("/users/42", TABLE) == "/users/{user_id}"
    assert normalize("/Health/", TABLE) == "/health"
    assert normalize("/documents/{doc_id}/") == "/documents/{doc_id}"


def test_one_to_one_assignment_duplicates_and_metrics():
    ground = [f("g1", "BOLA", "/documents/{doc_id}"), f("g2", "BFLA", "/users/{user_id}", "DELETE")]
    reported = [
        f("r1", "BOLA", "/documents/7", conf=0.9),
        f("r2", "BOLA", "/documents/{doc_id}", conf=0.4),   # same G again -> duplicate, not FP
        f("r3", "INJECTION", "/health", conf=0.8),           # FP
    ]
    m = match_findings(reported, ground, TABLE)
    assert [r["id"] for r, _ in m.pairs] == ["r1"]          # highest confidence wins
    assert [d["id"] for d in m.duplicates] == ["r2"]
    assert [x["id"] for x in m.false_positives] == ["r3"]
    assert [g["id"] for g in m.false_negatives] == ["g2"]
    assert m.detection_rate == 0.5 and m.fdr == 0.5


def test_category_and_method_must_both_match():
    m = match_findings([f("r", "BOLA", "/users/{user_id}", "POST")], [f("g", "BOLA", "/users/{user_id}", "GET")])
    assert m.tp == 0 and m.fp == 1 and m.fn == 1


def test_scan_diff_four_buckets():
    base = [
        f("b1", "BOLA", "/documents/{doc_id}", verification_outcome="fixed"),
        f("b2", "BFLA", "/users/{user_id}", "DELETE"),
        f("b3", "SECURITY_MISCONFIG", "/health"),
    ]
    head = [
        f("h1", "BOLA", "/documents/{doc_id}"),          # was fixed, reproduces -> came back
        f("h2", "BFLA", "/users/{user_id}", "DELETE"),   # still open
        f("h3", "INJECTION", "/users/{user_id}"),        # new
    ]
    d = diff_scans(base, head, TABLE)
    assert [x["id"] for x in d["came_back"]] == ["h1"]
    assert [x["id"] for x in d["still_open"]] == ["h2"]
    assert [x["id"] for x in d["new"]] == ["h3"]
    assert [x["id"] for x in d["fixed_since_last_scan"]] == ["b3"]
