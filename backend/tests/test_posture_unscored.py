"""D6: a missing/unknown CVSS band is explicit ('unscored'), never silently 'medium'."""
from app.scoring.posture import UNSCORED_BAND, UNSCORED_PENALTY, compute_posture


def _confirmed(**extra):
    return {"id": "f1", "status": "confirmed", "category": "BOLA", **extra}


def test_missing_band_goes_to_unscored_bucket():
    p = compute_posture([_confirmed()], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p["inputs"]["confirmed_counts"][UNSCORED_BAND] == 1
    assert p["inputs"]["confirmed_counts"]["medium"] == 0
    assert p["inputs"]["unscored_count"] == 1
    assert p["inputs"]["unscored_penalty_each"] == UNSCORED_PENALTY
    assert p["before"] == 100 - UNSCORED_PENALTY
    assert p["what_moved"][0]["severity"] == UNSCORED_BAND


def test_unknown_band_string_is_unscored():
    p = compute_posture([_confirmed(severity="spicy")], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p["inputs"]["confirmed_counts"][UNSCORED_BAND] == 1


def test_known_band_unchanged():
    p = compute_posture([_confirmed(severity="high")], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p["inputs"]["confirmed_counts"]["high"] == 1
    assert p["inputs"]["unscored_count"] == 0
    assert p["before"] == 82


def test_stored_evaluated_finding_shape_is_scored():
    """The pipeline passes EvaluatedFinding.model_dump(): severity lives under cvss."""
    stored = _confirmed(cvss={"severity": "critical", "base_score": 9.8, "vector_string": "x"})
    p = compute_posture([stored], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p["inputs"]["confirmed_counts"]["critical"] == 1
    assert p["before"] == 70


def test_surface_marks_worst_severity_from_stored_shape():
    from app.services.attack_surface import build_surface_from_inventory

    routes = [{"path": "/documents/{doc_id}", "method": "GET"}]
    finding = {"id": "f", "status": "confirmed", "route_template": "/documents/{doc_id}",
               "cvss": {"severity": "high", "base_score": 8.1}}
    import inspect
    sig = inspect.signature(build_surface_from_inventory)
    kwargs = {}
    for name in sig.parameters:
        if "route" in name or "inventory" in name or "endpoint" in name:
            kwargs[name] = routes
        elif "finding" in name:
            kwargs[name] = [finding]
        elif "test" in name:
            kwargs[name] = []
    surface = build_surface_from_inventory(**kwargs)
    node = next(n for n in surface["nodes"] if n["path"] == "/documents/{doc_id}")
    assert node["worst_severity"] == "high"


def test_enum_status_from_model_dump_is_counted():
    """scan_service passes EvaluatedFinding.model_dump(), whose status is an enum member."""
    from app.agents.evaluator.schemas import EvaluationStatus

    f = {"id": "f", "status": EvaluationStatus.CONFIRMED, "category": "BOLA",
         "cvss": {"severity": "high", "base_score": 8.1}}
    p = compute_posture([f], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p["before"] == 82
    f["verification_outcome"] = "fixed"
    p2 = compute_posture([f], test_cases=[{"category": "BOLA", "status": "executed"}])
    assert p2["after"] == 100 and p2["before"] == 82
