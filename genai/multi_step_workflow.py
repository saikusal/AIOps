from typing import Any, Dict, List, Optional


def _stage(name: str, status: str, summary: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "stage": name,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def _confidence_score(confidence: str) -> float:
    normalized = str(confidence or "").strip().lower()
    if normalized == "high":
        return 0.9
    if normalized == "low":
        return 0.3
    return 0.6


def _score_to_confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score <= 0.4:
        return "low"
    return "medium"


def _normalize_assessment_shapes(evidence: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(evidence or {})
    hard = [item for item in (normalized.get("hard_evidence") or []) if item]
    contradicting = [item for item in (normalized.get("contradicting_evidence") or []) if item]
    missing = [item for item in (normalized.get("missing_evidence") or []) if item]

    if not isinstance(normalized.get("confidence_assessment"), dict) or not normalized.get("confidence_assessment"):
        score = max(0.05, min(0.95, (len(hard) * 0.18) - (len(contradicting) * 0.08) - (len(missing) * 0.06) + 0.12))
        normalized["confidence_assessment"] = {
            "level": _score_to_confidence_label(score),
            "score": round(score, 2),
            "posture": "well_supported" if score >= 0.8 else "tentative" if score <= 0.4 else "developing",
            "summary": normalized.get("confidence_reason") or "",
        }
    if not isinstance(normalized.get("contradiction_assessment"), dict) or not normalized.get("contradiction_assessment"):
        count = len(contradicting)
        severity = "none" if count <= 0 else "low" if count == 1 else "moderate" if count == 2 else "high"
        normalized["contradiction_assessment"] = {
            "severity": severity,
            "count": count,
            "blocks_dependency_claim": count > 0 and len(hard) <= count,
            "summary": "No contradicting evidence currently weakens the working hypothesis." if count <= 0 else "Contradicting signals exist and should be considered before stronger claims are made.",
        }
    if not isinstance(normalized.get("evidence_gap_assessment"), dict) or not normalized.get("evidence_gap_assessment"):
        count = len(missing)
        status = "none" if count <= 0 else "low" if count == 1 else "moderate" if count <= 3 else "high"
        normalized["evidence_gap_assessment"] = {
            "status": status,
            "count": count,
            "summary": "No unresolved evidence gaps are currently tracked." if count <= 0 else "Additional evidence is still needed before the RCA can be treated as complete.",
        }
    return normalized


def build_investigation_plan(*, question: str, scope: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    evidence = (context or {}).get("evidence_assessment") or {}
    target = (
        evidence.get("best_dependency_target")
        or (context or {}).get("service_name")
        or (context or {}).get("target_host")
        or ""
    )
    candidate_hypotheses: List[Dict[str, Any]] = []
    if evidence.get("hard_evidence"):
        candidate_hypotheses.append(
            {
                "name": "scoped_component_failure",
                "confidence": "medium",
                "reason": evidence.get("confidence_reason") or "Scoped service evidence exists.",
            }
        )
    if evidence.get("dependency_hard_evidence"):
        candidate_hypotheses.append(
            {
                "name": "downstream_dependency_impact",
                "confidence": "medium",
                "reason": "Dependency-specific hard evidence was collected.",
            }
        )
    return {
        "goal": "Determine the most likely root cause and safest next verification step.",
        "question": question,
        "scope": scope or {},
        "selected_target": target,
        "candidate_hypotheses": candidate_hypotheses,
        "missing_evidence": evidence.get("missing_evidence") or [],
        "next_planned_tool_calls": [
            "metrics.query_service_overview",
            "logs.search",
            "traces.search",
        ],
    }


def build_iteration_plan(
    *,
    question: str,
    scope: Dict[str, Any],
    context: Dict[str, Any],
    planner: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    max_iterations: int = 3,
) -> Dict[str, Any]:
    evidence = (context or {}).get("evidence_assessment") or {}
    logs = evidence_bundle.get("logs") or {}
    traces = evidence_bundle.get("traces") or {}
    metrics = evidence_bundle.get("metrics") or {}
    code_context = evidence_bundle.get("code_context") or {}
    runbooks = evidence_bundle.get("runbooks") or {}

    candidate_steps: List[Dict[str, Any]] = []
    seen_tools = set()

    def _add_step(tool_name: str, reason: str, stop_if_successful: bool = False) -> None:
        if tool_name in seen_tools:
            return
        seen_tools.add(tool_name)
        candidate_steps.append(
            {
                "tool_name": tool_name,
                "reason": reason,
                "stop_if_successful": stop_if_successful,
            }
        )

    missing_evidence = [str(item) for item in (planner.get("missing_evidence") or []) if item]
    contradicted = [str(item) for item in (evidence.get("contradicting_evidence") or []) if item]

    if not metrics.get("ok"):
        _add_step("metrics.query_service_overview", "Metrics evidence is missing for the scoped service.")
    if not logs.get("ok") or int(logs.get("hit_count") or 0) <= 0:
        _add_step("logs.search", "Relevant log evidence is missing or empty for the current scope.")
    if not traces.get("ok") or int(traces.get("trace_count") or 0) <= 0:
        _add_step("traces.search", "Trace evidence is missing for the current scope.")
    if not code_context.get("ok"):
        _add_step("code.search_context", "Code ownership or recent change context is still missing.")
    if not runbooks.get("ok"):
        _add_step("runbooks.search", "No runbook guidance was collected yet.")

    for item in missing_evidence:
        lowered = item.lower()
        if "log" in lowered:
            _add_step("logs.search", f"Missing evidence mentions logs: {item}")
        elif "trace" in lowered or "span" in lowered:
            _add_step("traces.search", f"Missing evidence mentions traces or spans: {item}")
        elif "metric" in lowered or "latency" in lowered or "error" in lowered:
            _add_step("metrics.query_service_overview", f"Missing evidence mentions metrics: {item}")
        elif "deploy" in lowered or "change" in lowered or "code" in lowered:
            _add_step("code.recent_changes_for_component", f"Missing evidence mentions change analysis: {item}")
        elif "runbook" in lowered:
            _add_step("runbooks.search", f"Missing evidence mentions runbook guidance: {item}")

    if contradicted:
        _add_step(
            "topology.get_dependency_context",
            "Contradicting evidence exists, so dependency context should be re-checked before a stronger claim is made.",
            stop_if_successful=True,
        )

    if not candidate_steps:
        candidate_steps.append(
            {
                "tool_name": "none",
                "reason": "Existing evidence is sufficient for a bounded RCA response.",
                "stop_if_successful": True,
            }
        )

    iterations: List[Dict[str, Any]] = []
    should_continue = False
    stop_reason = "evidence_sufficient"
    for index in range(1, max_iterations + 1):
        if index <= len(candidate_steps):
            step = candidate_steps[index - 1]
            iterations.append(
                {
                    "iteration": index,
                    "selected_tool": step["tool_name"],
                    "reason": step["reason"],
                    "status": "planned" if step["tool_name"] != "none" else "skipped",
                }
            )
        else:
            iterations.append(
                {
                    "iteration": index,
                    "selected_tool": "none",
                    "reason": "Iteration budget reserved but not currently needed.",
                    "status": "unused",
                }
            )

    if candidate_steps and candidate_steps[0]["tool_name"] != "none":
        should_continue = True
        stop_reason = "iteration_budget_not_exhausted"

    return {
        "question": question,
        "scope": scope or {},
        "selected_target": planner.get("selected_target") or "",
        "max_iterations": max_iterations,
        "should_continue": should_continue,
        "stop_reason": stop_reason,
        "candidate_steps": candidate_steps,
        "iterations": iterations,
    }


def normalize_investigation_evidence(context: Dict[str, Any]) -> Dict[str, Any]:
    incident = (context or {}).get("incident") or {}
    metrics = (context or {}).get("metrics") or {}
    logs = (context or {}).get("elasticsearch") or {}
    traces = (context or {}).get("jaeger") or {}
    dependency_graph = (context or {}).get("dependency_graph") or {}
    code_context = (context or {}).get("code_context") or {}
    source_context = (context or {}).get("source_context") or {}
    runbooks = (context or {}).get("runbooks") or {}
    evidence = _normalize_assessment_shapes((context or {}).get("evidence_assessment") or {})
    linked = (context or {}).get("linked_recommendation") or {}
    return {
        "scope": (context or {}).get("scope") or {},
        "incident": {
            "incident_key": incident.get("incident_key") or "",
            "status": incident.get("status") or "",
            "title": incident.get("title") or "",
        },
        "metrics": {
            "ok": bool(metrics),
            "keys": sorted(list(metrics.keys()))[:10] if isinstance(metrics, dict) else [],
        },
        "logs": {
            "ok": bool(logs),
            "hit_count": int(logs.get("count") or 0) if isinstance(logs, dict) else 0,
        },
        "traces": {
            "ok": bool(traces),
            "trace_count": len((traces.get("data") or [])) if isinstance(traces, dict) else 0,
        },
        "dependency_graph": {
            "ok": bool(dependency_graph),
            "depends_on_count": len((dependency_graph.get("depends_on") or [])) if isinstance(dependency_graph, dict) else 0,
            "blast_radius_count": len((dependency_graph.get("blast_radius") or [])) if isinstance(dependency_graph, dict) else 0,
        },
        "code_context": {
            "ok": bool(code_context),
            "owner_repository": ((code_context.get("owner") or {}).get("repository")) if isinstance(code_context, dict) else "",
            "recent_change_count": len((((code_context.get("recent_changes") or {}).get("recent_changes")) or [])) if isinstance(code_context, dict) else 0,
            "quality": (((code_context.get("quality_assessment") or {}).get("quality")) if isinstance(code_context, dict) else "") or "",
            "safe_to_claim_code_root_cause": bool(((code_context.get("quality_assessment") or {}).get("safe_to_claim_code_root_cause"))) if isinstance(code_context, dict) else False,
            "stale_index": bool(((code_context.get("quality_assessment") or {}).get("stale_index"))) if isinstance(code_context, dict) else False,
        },
        "source_context": {
            "ok": bool(source_context),
            "traceback_count": int(source_context.get("traceback_count") or 0) if isinstance(source_context, dict) else 0,
        },
        "runbooks": {
            "ok": bool(runbooks),
            "count": int(runbooks.get("count") or 0) if isinstance(runbooks, dict) else 0,
        },
        "linked_recommendation": {
            "present": bool(linked),
            "diagnostic_command": linked.get("diagnostic_command") if isinstance(linked, dict) else "",
        },
        "evidence_assessment": {
            "hard_evidence": evidence.get("hard_evidence") or [],
            "contradicting_evidence": evidence.get("contradicting_evidence") or [],
            "missing_evidence": evidence.get("missing_evidence") or [],
            "safe_action": evidence.get("safe_action") or "",
            "confidence_reason": evidence.get("confidence_reason") or "",
            "confidence_assessment": evidence.get("confidence_assessment") or {},
            "contradiction_assessment": evidence.get("contradiction_assessment") or {},
            "evidence_gap_assessment": evidence.get("evidence_gap_assessment") or {},
        },
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
            "collecting_evidence",
            "completed",
            "Collected metrics, logs, traces, topology, runbooks, and code-context evidence.",
            {
                "metrics_present": bool((context or {}).get("metrics")),
                "logs_present": bool((context or {}).get("elasticsearch")),
                "traces_present": bool((context or {}).get("jaeger")),
                "code_context_present": bool((context or {}).get("code_context")),
            },
        ),
        _stage(
            "assessing_evidence",
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
            "planning_next_step",
            "completed",
            "Selected the most relevant investigation target and next evidence direction.",
            {
                "selected_target": target,
                "target_host": (context or {}).get("target_host") or "",
                "service_name": (context or {}).get("service_name") or "",
                "safe_action": evidence.get("safe_action") or "",
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


def annotate_investigation_workflow_with_iterations(
    workflow: List[Dict[str, Any]],
    iteration_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    annotated = [dict(item) for item in (workflow or [])]
    for item in annotated:
        if item.get("stage") != "planning_next_step":
            continue
        details = dict(item.get("details") or {})
        details["iteration_plan"] = {
            "max_iterations": iteration_plan.get("max_iterations"),
            "should_continue": iteration_plan.get("should_continue"),
            "stop_reason": iteration_plan.get("stop_reason"),
            "candidate_steps": iteration_plan.get("candidate_steps") or [],
            "iterations": iteration_plan.get("iterations") or [],
        }
        if iteration_plan.get("candidate_steps"):
            details["selected_next_tool"] = (iteration_plan["candidate_steps"][0] or {}).get("tool_name") or ""
        item["details"] = details
        break
    return annotated


def finalize_investigation_workflow(workflow: List[Dict[str, Any]], response: Dict[str, Any]) -> List[Dict[str, Any]]:
    finalized = list(workflow or [])
    finalized.append(
        _stage(
            "verifying",
            "completed",
            "Prepared the follow-up verification step from the completed investigation response.",
            {
                "next_verification_step": response.get("next_verification_step") or "",
                "suggested_command": response.get("suggested_command") or "",
            },
        )
    )
    finalized.append(
        _stage(
            "post_check_validator",
            "completed",
            "Validated the RCA response shape and attached the next verification step.",
            {
                "confidence": response.get("confidence") or "",
                "next_verification_step": response.get("next_verification_step") or "",
                "follow_up_question_count": len(response.get("follow_up_questions") or []),
                "confidence_score": _confidence_score(response.get("confidence") or ""),
                "confidence_assessment": response.get("confidence_assessment") or {},
                "contradiction_assessment": response.get("contradiction_assessment") or {},
                "evidence_gap_assessment": response.get("evidence_gap_assessment") or {},
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
                    "verification_loop_state": verification.get("verification_loop_state") or "",
                    "requires_follow_up": verification.get("requires_follow_up"),
                    "issue_score_delta": verification.get("issue_score_delta"),
                    "recommended_next_step": verification.get("recommended_next_step") or "",
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
