from typing import Any, Dict, List, Optional


def _stage(name: str, status: str, summary: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "stage": name,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def build_investigation_workflow(*, question: str, scope: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence = (context or {}).get("evidence_assessment") or {}
    linked = (context or {}).get("linked_recommendation") or {}
    runbooks = (context or {}).get("runbooks") or {}
    target = evidence.get("best_dependency_target") or (context or {}).get("service_name") or (context or {}).get("target_host") or ""

    workflow = [
        _stage(
            "planner",
            "completed",
            "Planned investigation scope from the operator question.",
            {
                "question": question,
                "scope": scope or {},
                "application": (context or {}).get("application") or "",
                "service_name": (context or {}).get("service_name") or "",
            },
        ),
        _stage(
            "evidence_checker",
            "completed",
            "Reviewed supporting, contradicting, and missing evidence before RCA generation.",
            {
                "hard_evidence": evidence.get("hard_evidence") or [],
                "contradicting_evidence": evidence.get("contradicting_evidence") or [],
                "missing_evidence": evidence.get("missing_evidence") or [],
                "confidence_reason": evidence.get("confidence_reason") or "",
            },
        ),
        _stage(
            "target_selector",
            "completed",
            "Selected the most relevant component for investigation based on current evidence.",
            {
                "selected_target": target,
                "target_host": (context or {}).get("target_host") or "",
                "service_name": (context or {}).get("service_name") or "",
            },
        ),
        _stage(
            "remediation_selector",
            "completed",
            "Gathered existing runbook and recommendation guidance without executing changes.",
            {
                "linked_recommendation_present": bool(linked),
                "diagnostic_command": linked.get("diagnostic_command") or "",
                "runbook_count": runbooks.get("count") if isinstance(runbooks, dict) else 0,
            },
        ),
    ]
    return workflow


def finalize_investigation_workflow(workflow: List[Dict[str, Any]], response: Dict[str, Any]) -> List[Dict[str, Any]]:
    finalized = list(workflow or [])
    finalized.append(
        _stage(
            "post_check_validator",
            "completed",
            "Validated the RCA response shape and attached the next verification step.",
            {
                "confidence": response.get("confidence") or "",
                "next_verification_step": response.get("next_verification_step") or "",
                "follow_up_question_count": len(response.get("follow_up_questions") or []),
            },
        )
    )
    return finalized


def build_execution_workflow(
    *,
    execution_type: str,
    question: str,
    typed_action: Dict[str, Any],
    target_host: str,
    policy_decision: Dict[str, Any],
    ranking: Dict[str, Any],
    baseline_evidence: Dict[str, Any],
    verification: Optional[Dict[str, Any]] = None,
    analysis_sections: Optional[Dict[str, Any]] = None,
    execution_status: str = "planned",
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    evidence = ((baseline_evidence or {}).get("signals") or {})
    workflow = [
        _stage(
            "planner",
            "completed",
            f"Prepared {execution_type} workflow from typed action and operator context.",
            {
                "question": question,
                "execution_type": execution_type,
                "typed_action": typed_action or {},
                "dry_run": dry_run,
            },
        ),
        _stage(
            "evidence_checker",
            "completed",
            "Checked baseline evidence and contradiction signals before acting.",
            {
                "confirming": evidence.get("confirming") or [],
                "contradicting": evidence.get("contradicting") or [],
                "confidence_score": (baseline_evidence or {}).get("confidence_score"),
            },
        ),
        _stage(
            "target_selector",
            "completed",
            "Confirmed the execution target from typed action and current context.",
            {
                "selected_target": typed_action.get("target") or typed_action.get("service") or target_host,
                "target_host": target_host,
            },
        ),
        _stage(
            "remediation_selector",
            "completed",
            "Ranked the selected action against previous outcomes before execution.",
            {
                "ranking_score": ranking.get("score"),
                "ranking_sample_size": ranking.get("sample_size"),
                "action_type": typed_action.get("action") or "",
            },
        ),
    ]

    executor_status = "completed" if execution_status in {"completed", "failed", "dry_run"} else "blocked" if execution_status in {"blocked", "approval_required"} else "in_progress"
    executor_summary = "Prepared a dry run without dispatching to an agent." if dry_run else "Applied policy and execution controls before dispatching to the agent."
    workflow.append(
        _stage(
            "executor",
            executor_status,
            executor_summary,
            {
                "policy_decision": policy_decision.get("decision") or "",
                "requires_approval": policy_decision.get("requires_approval"),
                "execution_status": execution_status,
            },
        )
    )

    if verification is not None:
        workflow.append(
            _stage(
                "verifier",
                "completed",
                "Ran post-action verification against fresh telemetry.",
                {
                    "verification_status": verification.get("status") or "",
                    "reason": verification.get("reason") or "",
                },
            )
        )

    remediation_action = (analysis_sections or {}).get("remediation_typed_action") or {}
    workflow.append(
        _stage(
            "post_check_validator",
            "completed",
            "Recorded follow-up remediation guidance and outcome metadata for future learning.",
            {
                "next_action_type": remediation_action.get("action") or "",
                "has_follow_up_remediation": bool(remediation_action),
            },
        )
    )
    return workflow
