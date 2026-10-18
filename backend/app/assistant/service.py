"""
"Ask ClairSec" assistant (FEATURES.md F11).

Grounded, read-only and honest:
  * Facts come only from platform records (app.assistant.tools), each with an id.
  * With an offline provider (mock / no key) a deterministic answerer handles the
    common questions from templates — labelled "Offline assistant".
  * With a real provider, the model writes the prose under a versioned prompt; the
    answer is QUARANTINED-trust, target-derived text is wrapped in the untrusted
    envelope, and any cited id that is not among the provided facts is dropped.
  * Nothing here can change a status, severity, score or verdict. Suggested
    actions are links the USER may click; the assistant executes nothing.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.assistant import tools
from app.llm.factory import build_provider, is_offline_provider
from app.llm.models import AgentName, CallBudget, LLMRequest, Message, TrustLevel, Untrusted
from app.llm.prompts.registry import PromptRegistry
from app.llm.quarantine import wrap_quarantined

logger = logging.getLogger(__name__)

CONVERSATIONS = "assistant_conversations"

# A verdict that the application is safe — never allowed in an answer (SECURITY.md section 11).
_SECURE_VERDICT = re.compile(
    r"\b(app|application|project|api|system|it|this|code)\s+(is|looks|seems)\s+(now\s+|completely\s+|fully\s+)?(secure|safe from attack)\b",
    re.IGNORECASE,
)
MAX_STORED_MESSAGES = 50


class AssistantContext(BaseModel):
    screen: str = "dashboard"
    project_id: str | None = None
    scan_id: str | None = None
    finding_id: str | None = None


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: AssistantContext = Field(default_factory=AssistantContext)
    explain_simply: bool = False
    conversation_id: str | None = None


class Citation(BaseModel):
    type: str
    id: str
    label: str


class SuggestedAction(BaseModel):
    label: str
    route: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    mode: str  # "offline" | "llm"
    conversation_id: str


class _ModelAnswer(BaseModel):
    """Structured output the model must return (LLM.md section 3)."""

    answer: str
    cited_ids: list[str] = Field(default_factory=list)


# ── Fact gathering ───────────────────────────────────────────────────────────


class Facts(BaseModel):
    lines: dict[str, str] = Field(default_factory=dict)        # fact id -> platform fact (trusted)
    untrusted: list[Untrusted] = Field(default_factory=list)   # target-derived text
    citations: dict[str, Citation] = Field(default_factory=dict)
    scan: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    finding: dict[str, Any] | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


async def gather_facts(db: AsyncIOMotorDatabase, ctx: AssistantContext) -> Facts:
    f = Facts()
    finding = await tools.get_finding(db, ctx.finding_id) if ctx.finding_id else None
    scan_id = ctx.scan_id or (finding or {}).get("scan_id")
    scan = await tools.get_scan(db, scan_id) if scan_id else None
    project_id = ctx.project_id or (scan or {}).get("project_id") or (finding or {}).get("project_id")
    project = await tools.get_project(db, project_id) if project_id else None
    if scan is None and project_id:
        scan = await tools.get_latest_scan_for_project(db, project_id)
    if scan is None and not ctx.finding_id and not project_id:
        scan = await tools.get_latest_scan(db)
    f.scan, f.project, f.finding = scan, project, finding

    if project:
        pid = f"project:{project['id'][:8]}"
        f.lines[pid] = (
            f"Project '{project.get('name')}': validation={tools._v(project.get('validation_status'))}, "
            f"isolation={tools._v(project.get('isolation_status'))}, origin={project.get('origin', 'user_project')}"
            + (f", isolation error: {tools.redact(project.get('isolation_error'))[:400]}"
               if project.get("isolation_error") else "")
        )
        f.citations[pid] = Citation(type="project", id=project["id"], label=project.get("name") or "Project")

    if scan:
        sid = f"scan:{scan['id'][:8]}"
        c = scan.get("counters") or {}
        p = scan.get("posture") or {}
        f.lines[sid] = (
            f"Scan state={scan.get('state')}, stage={scan.get('stage')}, mode={scan.get('mode')}; "
            f"endpoints={c.get('endpoints_discovered', 0)}, tests executed={c.get('tests_executed', 0)}, "
            f"candidates={c.get('candidates', 0)}, confirmed={c.get('confirmed', 0)}, "
            f"fixes applied={c.get('fixes_applied', 0)}, fixes verified={c.get('fixes_verified', 0)}"
            + (f"; score before={p.get('before')} ({p.get('grade_before')}), after={p.get('after')} "
               f"({p.get('grade_after')}), coverage={p.get('coverage')}" if p.get("before") is not None else "")
            + (f"; error: {tools.redact(scan.get('error'))[:400]}" if scan.get("error") else "")
        )
        f.citations[sid] = Citation(type="scan", id=scan["id"], label=f"Scan {scan['id'][:8]}")
        f.events = await tools.get_recent_events(db, scan["id"])
        for e in f.events[-8:]:
            eid = f"event:{scan['id'][:8]}-{e.get('seq')}"
            f.lines[eid] = f"{e.get('agent')}: {e.get('title')}"
        f.findings = await tools.list_findings(db, scan["id"])
        for fd in f.findings[:12]:
            fid = f"finding:{fd['id'][:8]}"
            sev = (fd.get("cvss") or {}).get("severity")
            f.lines.setdefault(fid, (
                f"Finding '{fd.get('title')}' {fd.get('method')} {fd.get('route_template')}: "
                f"status={tools._v(fd.get('status'))}, severity={tools._v(sev)}"
            ))
            f.citations.setdefault(fid, Citation(type="finding", id=fd["id"], label=fd.get("title") or "Finding"))

    if finding:
        fid = f"finding:{finding['id'][:8]}"
        prov = await tools.get_provenance(db, finding["id"])
        ver = await tools.get_verification(db, finding["id"])
        f.verification = ver
        cvss = finding.get("cvss") or {}
        f.lines[fid] = (
            f"Finding '{finding.get('title')}' ({finding.get('category')}) at {finding.get('method')} "
            f"{finding.get('route_template')}: status={tools._v(finding.get('status'))}, "
            f"CVSS {cvss.get('base_score')} {tools._v(cvss.get('severity'))}; "
            f"evidence lane={(prov or {}).get('lane')}; "
            f"plain meaning: {tools.explain_category(finding.get('category')) or 'n/a'}"
        )
        f.citations[fid] = Citation(type="finding", id=finding["id"], label=finding.get("title") or "Finding")
        if prov:
            f.lines[f"{fid}-chain"] = "; ".join(f"{s['who']}: {s['title']}" for s in prov.get("steps", []))
        if ver:
            vid = f"verification:{finding['id'][:8]}"
            suite = ver.get("functional_suite") or {}
            ep = ver.get("endpoint_preserved") or {}
            f.lines[vid] = (
                f"Verification outcome={tools._v(ver.get('outcome'))}; exploit re-run exploited="
                f"{(ver.get('original_exploit') or {}).get('exploited')}; app checks {suite.get('passed')}/"
                f"{suite.get('total')} passed ({suite.get('source', 'fixture_suite')}); endpoint preserved="
                f"{ep.get('preserved') if ep.get('ran') else 'unknown'}; reason: {ver.get('outcome_reason')}"
            )
            f.citations[vid] = Citation(type="verification", id=ver.get("id", ""), label="Fix verification")
        # The response the target sent is target-derived: it may contain injected instructions.
        evidence_ids = finding.get("evidence_ids") or []
        if evidence_ids:
            tc = await db["test_cases"].find_one({"id": evidence_ids[0]})
            body = ((tc or {}).get("response") or {}).get("body")
            if body:
                f.untrusted.append(Untrusted(content=tools.redact(body)[:1500],
                                             origin=f"http:{finding.get('method')} {finding.get('route_template')}"))
    return f


# ── Offline (deterministic) answerer ─────────────────────────────────────────


def _intent(message: str) -> str:
    m = message.lower()
    rules = [
        ("failure", ("fail", "error", "broke", "not work", "didn't", "didnt", "stuck", "why can't", "cannot")),
        ("fix", ("fix", "patch", "safe", "verified", "regress")),
        ("score", ("score", "grade", "posture")),
        ("next", ("next", "should i", "what now", "do now", "recommend")),
        ("explain", ("explain", "what is", "what's", "mean", "manager", "simple")),
        ("status", ("happening", "status", "progress", "doing", "running", "summary")),
    ]
    for name, words in rules:
        if any(w in m for w in words):
            return name
    return "status"


def _suggestions(f: Facts) -> list[SuggestedAction]:
    out: list[SuggestedAction] = []
    if f.finding:
        out.append(SuggestedAction(label="Open this finding", route=f"/vulnerabilities/{f.finding['id']}"))
        out.append(SuggestedAction(label="Review the fix", route=f"/fixes/{f.finding['id']}"))
    if f.scan:
        out.append(SuggestedAction(label="Open the scan", route=f"/scans/{f.scan['id']}"))
        if f.scan.get("state") == "completed":
            out.append(SuggestedAction(label="Generate a report", route="/reports"))
    return out[:3]


def offline_answer(message: str, f: Facts, simple: bool) -> tuple[str, list[str]]:
    """Return (answer, fact ids used). Templates only — never invents data."""
    intent = _intent(message)
    scan, fd, ver = f.scan, f.finding, f.verification
    sid = f"scan:{scan['id'][:8]}" if scan else None

    if intent == "failure":
        err = (scan or {}).get("error") or (f.project or {}).get("isolation_error")
        if not err:
            return ("Nothing has failed in the recorded data for this context. If something looks stuck, "
                    "check the readiness banner on the Dashboard: it shows whether Docker, the database "
                    "and the AI provider are reachable.", [k for k in (sid,) if k])
        hint = tools.diagnose_failure(err)
        ids = [k for k in (sid, f"project:{f.project['id'][:8]}" if f.project else None) if k]
        return (f"The last error recorded was: {tools.redact(err)[:300]}"
                + (f"\n\nLikely cause: {hint}" if hint else "\n\nI can't match it to a known cause; the full "
                   "message above is what the platform recorded."), ids)

    if intent == "fix" and fd:
        vid = f"verification:{fd['id'][:8]}"
        if not ver:
            return ("This finding has no verified fix yet, so I can't say the fix works. "
                    "A fix only counts once the same attack is re-run and blocked AND the app still works.",
                    [f"finding:{fd['id'][:8]}"])
        outcome = str(tools._v(ver.get("outcome")))
        suite = ver.get("functional_suite") or {}
        if simple:
            text = {"fixed": "Yes. We tried the same break-in again and it failed, and the app still does "
                             "everything it did before.",
                    "regressed": "Not quite. The fix stopped the attack but broke something else, so it "
                                 "doesn't count as fixed.",
                    "unresolved": "No. The same attack still works after the change."}.get(
                outcome, "We couldn't check it fully, so we don't count it as fixed yet.")
        else:
            text = (f"Verification outcome: {outcome}. Exploit re-run blocked: "
                    f"{not (ver.get('original_exploit') or {}).get('exploited')}. Functional checks: "
                    f"{suite.get('passed')}/{suite.get('total')} passed ({suite.get('source', 'fixture_suite')}). "
                    f"Reason recorded: {ver.get('outcome_reason')}")
        return text, [vid]

    if intent == "score" and scan and (scan.get("posture") or {}).get("before") is not None:
        p = scan["posture"]
        return (f"The security score went from {p['before']} ({p['grade_before']}) before fixes to "
                f"{p['after']} ({p['grade_after']}) after verified fixes. It is computed by platform code from "
                "confirmed findings only, and a high score means the tests that ran found nothing, not that "
                "nothing exists" + (" (coverage was limited)." if p.get("limited_coverage") else "."), [sid])

    if intent == "explain" and fd:
        plain = tools.explain_category(fd.get("category"))
        fid = f"finding:{fd['id'][:8]}"
        if simple and plain:
            return (f"In plain words: {plain} ClairSec proved this by actually trying it against a sealed "
                    "copy of the app, not by guessing.", [fid])
        cvss = fd.get("cvss") or {}
        return (f"{fd.get('title')}: {fd.get('description') or ''} Severity is CVSS {cvss.get('base_score')} "
                f"({tools._v(cvss.get('severity'))}), computed by platform code."
                + (f" In plain words: {plain}" if plain else ""), [fid])

    if intent == "next":
        if not scan:
            return ("Start by importing a project (Projects → Local folder or GitHub URL) or run the Demo app "
                    "to see the whole pipeline in about a minute.", [])
        state = scan.get("state")
        if state in ("running", "queued"):
            return ("The scan is still running. Watch the attack timeline; findings appear the moment an "
                    "oracle confirms them.", [sid])
        if state == "failed":
            return ("The scan failed. Ask me \"why did it fail?\" to see the recorded error and likely cause, "
                    "then retry from the Scans screen.", [sid])
        unfixed = [x for x in f.findings if str(tools._v(x.get("status"))) == "confirmed"]
        return ((f"Review the {len(unfixed)} confirmed finding(s), replay an attack to see the proof, then "
                 "generate a report for your team.") if unfixed else
                "No confirmed findings. Generate a report to record the coverage, and consider scanning again "
                "after code changes.", [sid])

    # status / fallback
    if not scan:
        return ("There is no scan for this context yet. Import a project or run the Demo app to start.", [])
    c = scan.get("counters") or {}
    if simple:
        text = (f"Right now the scan is {scan.get('state')} ({scan.get('stage')}). It has tried "
                f"{c.get('tests_executed', 0)} attacks and proved {c.get('confirmed', 0)} real problem(s); "
                f"{c.get('fixes_verified', 0)} fix(es) were checked and work.")
    else:
        text = (f"Scan {scan['id'][:8]} is {scan.get('state')} at stage '{scan.get('stage')}': "
                f"{c.get('endpoints_discovered', 0)} endpoints, {c.get('tests_executed', 0)} tests executed, "
                f"{c.get('candidates', 0)} candidates, {c.get('confirmed', 0)} confirmed, "
                f"{c.get('fixes_verified', 0)} fixes verified.")
    if f.events:
        text += f" Latest event: {f.events[-1].get('title')}."
    if intent == "status" and not any(w in message.lower() for w in ("happening", "status", "progress", "doing",
                                                                   "running", "summary")):
        text += (" (I'm the offline assistant: I answer common questions from recorded data. Connect an AI "
                 "provider in Settings for open-ended questions.)")
    return text, [sid]


# ── LLM path ─────────────────────────────────────────────────────────────────


async def llm_answer(message: str, f: Facts, simple: bool, scan_id: str | None) -> tuple[str, list[str]] | None:
    provider = build_provider()
    if is_offline_provider(provider):
        return None
    system = PromptRegistry().get_prompt("assistant.answer", "v1")
    facts_text = "\n".join(f"[{k}] {v}" for k, v in f.lines.items()) or "(no recorded facts)"
    parts = [f"Recorded platform facts:\n{facts_text}"]
    for u in f.untrusted:
        wrapped, _nonce, _detected = wrap_quarantined(u)
        parts.append(f"Target response captured at {u.origin}:\n{wrapped}")
    parts.append(("Explain simply, for a non-technical reader.\n" if simple else "") + f"Question: {message}")
    request = LLMRequest(
        prompt_id="assistant.answer",
        prompt_version="v1",
        system=system,
        messages=[Message(role="user", content="\n\n".join(parts))],
        response_schema=_ModelAnswer,
        trust=TrustLevel.QUARANTINED,
        scan_id=scan_id or "assistant",
        agent=AgentName.ASSISTANT,
        budget=CallBudget(max_attempts=2, timeout_s=60, max_output_tokens=800),
    )
    try:
        resp = await provider.complete(request=request)
    except Exception as exc:  # noqa: BLE001 — fall back to the offline answer
        logger.warning("Assistant LLM call failed: %s", exc)
        return None
    if resp.malformed_output or resp.parsed is None:
        return None
    parsed: _ModelAnswer = resp.parsed  # type: ignore[assignment]
    valid = [i.strip("[]") for i in parsed.cited_ids if i.strip("[]") in f.lines]
    answer = parsed.answer.strip()
    # Platform code checks the model's prose before anyone sees it (RULES.md section 3).
    # An answer that cites no recorded fact is ungrounded; an answer that declares the app
    # "secure" breaks SECURITY.md section 11 and is the classic result of a prompt injection
    # in the target's own responses. Either way the model's text is withheld.
    if not valid or _SECURE_VERDICT.search(answer):
        logger.warning("Assistant LLM answer withheld (citations=%d, secure_verdict=%s)",
                       len(valid), bool(_SECURE_VERDICT.search(answer)))
        return None
    return answer, valid


# ── Entry point ──────────────────────────────────────────────────────────────


async def ask(db: AsyncIOMotorDatabase, req: AskRequest) -> AskResponse:
    facts = await gather_facts(db, req.context)
    result = await llm_answer(req.message, facts, req.explain_simply,
                              (facts.scan or {}).get("id"))
    mode = "llm"
    if result is None:
        result = offline_answer(req.message, facts, req.explain_simply)
        mode = "offline"
    answer, used_ids = result
    citations = [facts.citations[i.split("-chain")[0]] for i in used_ids
                 if i.split("-chain")[0] in facts.citations]
    seen: set[str] = set()
    citations = [c for c in citations if not (c.id in seen or seen.add(c.id))]

    conv_id = req.conversation_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    turn = [
        {"role": "user", "text": tools.redact(req.message), "ts": now},
        {"role": "assistant", "text": tools.redact(answer), "mode": mode,
         "citations": [c.model_dump() for c in citations], "ts": now},
    ]
    existing = await db[CONVERSATIONS].find_one({"id": conv_id})
    messages = ((existing or {}).get("messages") or []) + turn
    await db[CONVERSATIONS].update_one(
        {"id": conv_id},
        {"$set": {"id": conv_id, "context": req.context.model_dump(), "updated_at": now,
                  "messages": messages[-MAX_STORED_MESSAGES:], "schema_version": 1}},
        upsert=True,
    )
    return AskResponse(answer=answer, citations=citations, suggested_actions=_suggestions(facts),
                       mode=mode, conversation_id=conv_id)
