"""
Report renderers (FEATURES.md F12): HTML, Markdown, JSON, SARIF 2.1.0.

Every renderer consumes the already-redacted dict from collect.collect_report_data.
None of them can reach the database or an LLM.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.reporting.collect import TAXONOMY

FORMATS = ("html", "md", "json", "sarif")
_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note",
                "informational": "note", "unscored": "warning"}


def render_html(d: dict[str, Any], audience: str = "both") -> str:
    return _env.get_template("report.html.j2").render(d=d, audience=audience)


def render_json(d: dict[str, Any], audience: str = "both") -> str:
    return json.dumps(d, indent=2, default=str)


def render_markdown(d: dict[str, Any], audience: str = "both") -> str:
    p = d.get("posture") or {}
    out = [f"# ClairSec security report: {d['project']['name']}", "",
           f"Scan `{d['scan']['id']}` · mode `{d['method']['experience_mode']}` · generated {d['generated_at']}", ""]
    if audience in ("both", "exec"):
        out += ["## Executive summary", ""]
        if p.get("before") is not None:
            out += [f"**Security score:** {p['before']} ({p['grade_before']}) → {p['after']} ({p['grade_after']})", ""]
        out += [*d["summary"], ""]
        if p.get("basis"):
            out += [f"_{p['basis']}_", ""]
    if audience in ("both", "technical"):
        out += [f"## Confirmed findings ({len(d['confirmed'])})", ""]
        if not d["confirmed"]:
            out += ["No vulnerability was proved by the attacks that ran. This does not mean none exist.", ""]
        for f in d["confirmed"]:
            ver = (f.get("verification") or {}).get("outcome") or "not verified"
            out += [f"### [{f['severity'].upper()}] {f['title']}", "",
                    f"- Endpoint: `{f['method']} {f['route']}`",
                    f"- Category: {f['category_name']} · {f['owasp']} · {f['cwe']}",
                    f"- CVSS: {f.get('cvss_score')} `{f.get('cvss_vector') or ''}`",
                    f"- Fix: {ver}", ""]
            if f.get("plain"):
                out += [f"> In plain words: {f['plain']}", ""]
            if f.get("patch") and f["patch"].get("diff"):
                out += ["```diff", f["patch"]["diff"], "```", ""]
        out += ["## Coverage and method", "",
                f"- Tested: {', '.join(d['coverage']['tested']) or 'none'}",
                f"- Not tested: {', '.join(u['category'] for u in d['coverage']['untested']) or 'none'}",
                f"- Platform {d['method']['platform_version']} · {d['method']['llm_provider']} / "
                f"{d['method']['model_id']} · {d['method']['posture_version']} · storage {d['method']['storage_mode']}",
                "", "_AI models only proposed tests and fixes; every verdict here was computed by platform code._", ""]
    return "\n".join(out)


def render_sarif(d: dict[str, Any], audience: str = "both") -> str:
    """SARIF 2.1.0 - stable tool name, CWE in taxa, CVSS in properties (DefectDojo-compatible)."""
    rules: dict[str, dict[str, Any]] = {}
    results = []
    cwe_taxa: dict[str, dict[str, Any]] = {}
    for f in d["confirmed"]:
        rule_id = f"CLAIRSEC/{f['category']}"
        name, owasp, cwe = TAXONOMY.get(f["category"], (f["category_name"], "-", f.get("cwe") or ""))
        cwe_ids = [c.strip() for c in str(f.get("cwe") or cwe).split(",") if c.strip()]
        for c in cwe_ids:
            cwe_taxa.setdefault(c, {"id": c.replace("CWE-", ""), "name": c})
        rules.setdefault(rule_id, {
            "id": rule_id,
            "name": f["category"].title().replace("_", ""),
            "shortDescription": {"text": name},
            "fullDescription": {"text": f.get("plain") or name},
            "helpUri": "https://owasp.org/API-Security/editions/2023/en/0x11-t10/",
            "properties": {"tags": ["security", owasp, *cwe_ids]},
            "relationships": [
                {"target": {"id": c.replace("CWE-", ""), "toolComponent": {"name": "CWE"}}, "kinds": ["superset"]}
                for c in cwe_ids
            ],
        })
        locations = []
        for loc in f.get("source_locations") or []:
            uri = loc.get("file") or loc.get("path")
            if uri:
                region = {"startLine": int(loc.get("line") or loc.get("start_line") or 1)}
                locations.append({"physicalLocation": {"artifactLocation": {"uri": str(uri).replace("\\", "/")},
                                                       "region": region}})
        ver = (f.get("verification") or {}).get("outcome")
        results.append({
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(f["severity"], "warning"),
            "message": {"text": f"{f['title']} at {f['method']} {f['route']}"},
            "locations": locations,
            "properties": {
                "endpoint": f"{f['method']} {f['route']}",
                "cvss": {"score": f.get("cvss_score"), "vector": f.get("cvss_vector")},
                "severity": f["severity"],
                "runtimeConfirmed": True,
                "fixVerification": ver or "not_verified",
            },
        })
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "ClairSec",
                    "version": d["method"]["platform_version"],
                    "informationUri": "https://github.com/chiragk31/ClairSec",
                    "rules": list(rules.values()),
                },
                "extensions": [{"name": "CWE", "taxa": list(cwe_taxa.values())}] if cwe_taxa else [],
            },
            "results": results,
            "properties": {
                "scanId": d["scan"]["id"],
                "experienceMode": d["method"]["experience_mode"],
                "postureVersion": d["method"]["posture_version"],
                "model": f"{d['method']['llm_provider']}/{d['method']['model_id']}",
            },
        }],
    }
    return json.dumps(sarif, indent=2, default=str)


RENDERERS = {"html": render_html, "md": render_markdown, "json": render_json, "sarif": render_sarif}
EXTENSIONS = {"html": "html", "md": "md", "json": "json", "sarif": "sarif.json"}
MEDIA_TYPES = {"html": "text/html", "md": "text/markdown", "json": "application/json",
               "sarif": "application/sarif+json", "pdf": "application/pdf"}
