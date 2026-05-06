# Track 2: Autonomous Control Plane Design

This is Track 2 of the OpsMitra autonomy and operations architecture plan.

Related tracks:

- `Track 1`: [AGENT_POLICY_AND_RUNTIME_DESIGN.md](./AGENT_POLICY_AND_RUNTIME_DESIGN.md)
- `Track 3`: [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md)
- `Track 4`: [INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md](./INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md)

Supporting assessment:

- [CODE_CONTEXT_GAP_ASSESSMENT.md](./CODE_CONTEXT_GAP_ASSESSMENT.md)

This document defines how the OpsMitra control plane should evolve from a structured investigation orchestrator into a more autonomous, multi-step investigation and remediation system.

The goal is not to give the LLM unrestricted power. The goal is to let the control plane:

- plan an investigation in stages,
- gather evidence iteratively,
- decide what information is missing,
- call the right tools in the right order,
- stop safely when confidence is insufficient,
- escalate to approved execution only when policy allows.

## Design Goals

The autonomous control plane should be able to:

- accept an alert, incident, or operator question
- identify the most relevant target and service
- gather evidence from telemetry, runtime inventory, code context, topology, and history
- reason about gaps and contradictions in the evidence
- choose the next best evidence-gathering step
- continue for multiple iterations until confidence is sufficient or a stop condition is reached
- produce a grounded RCA, next-step guidance, or an execution plan
- route approved actions through the policy layer and target-side agents
- verify results after diagnostics or remediation
- persist the entire reasoning and execution lifecycle

## Why This Track Is Needed

Today, OpsMitra already does significant orchestration:

- route classification
- metrics, logs, and trace retrieval
- code-context lookup
- workflow staging
- typed-action generation
- policy checks
- agent dispatch
- post-command analysis

However, the current control plane is still mostly a structured single-pass or two-pass orchestrator.

It does not yet fully operate as a long-running internal loop that:

- explicitly tracks investigation state,
- detects missing evidence as first-class planning outputs,
- repeatedly selects the next best tool,
- stops only when enough evidence has been gathered or the safety boundary has been reached.

That is the gap this track addresses.

## Core Principles

1. The control plane does the reasoning and orchestration.
2. Agents do evidence retrieval and execution, not decision-making.
3. LLMs should reason over structured evidence, not raw infrastructure guessing.
4. Every step should be bounded, explainable, and auditable.
5. The autonomy loop must have explicit stop conditions.
6. Remediation must remain policy-aware and approval-aware.

## Current State

The current codebase already contains important pieces of this track:

- investigation routing in `genai/views.py`
- MCP-style tool orchestration in `genai/mcp_orchestrator.py`
- tool adapters in `genai/mcp_services.py`
- workflow staging in `genai/multi_step_workflow.py`
- typed actions in `genai/typed_actions.py`
- execution intents, rankings, and replay data in `genai/models.py`

This means Track 2 is not starting from zero. It is an evolution of the current orchestrator into a deeper investigation loop.

One important dependency for Track 2 is the quality of the code-context engine. The current maturity and gaps are captured in [CODE_CONTEXT_GAP_ASSESSMENT.md](./CODE_CONTEXT_GAP_ASSESSMENT.md).

Another important dependency is Track 4, because the autonomy loop must be able to consume normalized telemetry from either native or external platforms.

## Target Architecture

The autonomous control plane should be modeled as an internal state machine with cooperating stages:

1. `Incident Intake`
2. `Scope Resolver`
3. `Planner`
4. `Evidence Collector`
5. `Evidence Assessor`
6. `Hypothesis Generator`
7. `Decision Gate`
8. `Executor`
9. `Verifier`
10. `Outcome Recorder`

These stages should be explicit in both backend state and UI workflow rendering.

## Investigation State Machine

Each investigation run should move through states such as:

- `queued`
- `scoping`
- `collecting_evidence`
- `assessing_evidence`
- `planning_next_step`
- `awaiting_approval`
- `executing`
- `verifying`
- `resolved`
- `needs_operator_input`
- `failed`

This state machine should be persisted so the system can:

- resume interrupted investigations
- show progress in the UI
- support replay and evaluation

## Multi-Iteration Investigation Loop

The target loop is:

1. ingest alert or operator question
2. resolve target and service scope
3. build an initial evidence plan
4. fetch evidence using tools and target-side agents
5. assess evidence quality, gaps, and contradictions
6. decide whether enough evidence exists
7. if not, choose the next best tool call and continue
8. if yes, generate RCA and next-step recommendation
9. if an action is appropriate and policy allows, prepare an execution plan
10. dispatch diagnostics or remediation
11. verify outcome using fresh telemetry
12. record final result and learning signals

The loop should stop when:

- confidence is sufficient
- a hard contradiction cannot be resolved automatically
- required runtime knowledge is missing
- policy blocks further action
- operator approval is required
- iteration budget is exhausted

## What The LLM Should And Should Not Do

The LLM should:

- interpret evidence
- summarize findings
- propose likely causes
- identify missing evidence
- select the next tool category
- propose typed actions

The LLM should not:

- guess infrastructure details when target config is absent
- issue unrestricted shell commands
- bypass policy or approval
- directly decide irreversible actions without the policy layer

The control plane should convert LLM intent into:

- structured next-step decisions
- tool invocations
- typed actions

## Evidence Model

The control plane should reason over a normalized evidence bundle, not ad hoc strings.

Suggested evidence categories:

- alert payload
- incident history
- metrics snapshot
- log excerpt
- trace excerpt
- dependency graph
- inventory/runtime profile
- centralized log query results
- code-context evidence
- recent deployments
- recent commits
- runbook matches
- prior similar incidents
- policy constraints

Each evidence item should carry metadata such as:

- source
- freshness
- confidence
- target scope
- relevance score
- contradiction flags

## Planning Model

The planner should produce a structured plan rather than a free-form paragraph.

Example output shape:

```json
{
  "goal": "Explain 503 errors on orders-api",
  "current_scope": {
    "target": "orders-prod-01",
    "service": "orders-api"
  },
  "hypotheses": [
    "database connectivity failure",
    "upstream dependency timeout",
    "bad deployment regression"
  ],
  "missing_evidence": [
    "application log excerpt",
    "recent trace sample",
    "recent code changes"
  ],
  "next_actions": [
    "fetch_logs",
    "fetch_traces",
    "fetch_recent_code_changes"
  ]
}
```

This plan should be stored on the `InvestigationRun`.

## Tool Selection Strategy

Tool calls should be selected through bounded classes rather than arbitrary generation.

Examples:

- `fetch_metrics`
- `fetch_logs`
- `fetch_traces`
- `fetch_dependency_graph`
- `fetch_runtime_profile`
- `fetch_code_owner`
- `fetch_recent_commits`
- `fetch_runbooks`
- `fetch_similar_incidents`
- `run_diagnostic_command`
- `run_remediation_command`

The control plane should translate these abstract tool choices into concrete backend calls.

For centralized logs, `fetch_logs` should:

- choose the correct stream family based on target runtime knowledge
- apply metadata filters such as `target_id`, `service_name`, `environment`, or `k8s_namespace`
- avoid depending on one index per host or application

## Missing Runtime Knowledge Handling

The autonomy loop must explicitly handle cases where runtime knowledge is incomplete.

Examples:

- log source is unknown
- target role is ambiguous
- service-to-container mapping is missing
- target policy profile is absent

In those cases, the planner should:

- fall back to safe discovery
- reduce confidence
- request operator confirmation when needed
- avoid broad or destructive execution

This is where Track 1 and Track 2 meet.

Track 2 assumes that centralized logs are already available through Track 1’s source-aware ingestion model. The autonomy loop should query logs by stream family plus metadata filters, not by inventing per-host index names.

## Contradiction And Confidence Handling

The control plane should treat contradictions as first-class objects.

Examples:

- logs suggest DB timeout but traces suggest ingress failure
- metrics show app healthy but alerts show 503s
- recent deployment evidence conflicts with stable error history

The control plane should:

- explicitly record contradictions
- reduce confidence when contradictions persist
- prefer additional diagnostics over premature remediation
- ask for operator review when contradictions remain unresolved

Confidence should be derived from:

- evidence freshness
- number of confirming signals
- number of contradicting signals
- historical similarity
- runtime knowledge completeness

## Execution Escalation Model

The autonomous control plane should escalate through levels:

1. `Observe`
   Read-only evidence gathering
2. `Diagnose`
   Read-only diagnostic commands
3. `Recommend`
   Propose remediation without executing
4. `Approve`
   Wait for approval if required
5. `Execute`
   Dispatch typed action through the agent
6. `Verify`
   Check telemetry and incident state after execution

This layered model prevents uncontrolled action jumps.

## Verification Loop

After every executed diagnostic or remediation action, the control plane should:

- gather fresh metrics
- gather fresh logs if relevant
- compare alert state before and after
- assess whether symptoms improved, worsened, or stayed unchanged
- decide whether the incident is resolved, still active, or requires the next iteration

Verification should not be optional. It is part of the autonomy loop.

## Operator Interaction Model

Even in autonomous mode, the operator remains part of the system.

The control plane should support:

- `autonomous observe-only`
- `autonomous diagnose-only`
- `autonomous with approval-required remediation`
- `manual review required`

The UI should clearly show:

- what the system observed
- what it inferred
- why it chose the next step
- which steps were blocked by policy

## Persistence Model

The control plane should persist:

- investigation run state
- iteration count
- plan snapshots
- evidence bundle snapshots
- tool invocations
- contradiction records
- typed actions
- policy decisions
- verification results
- outcome summaries

This enables:

- debugging
- replay
- learning
- evaluation
- auditability

## Proposed Model Extensions

The current `InvestigationRun` and `ToolInvocation` models should be extended or complemented with:

- `InvestigationPlanSnapshot`
- `EvidenceBundleSnapshot`
- `EvidenceGap`
- `HypothesisRecord`
- `VerificationRecord`
- `AutonomyDecisionRecord`

Suggested purposes:

- `InvestigationPlanSnapshot`
  stores planner outputs per iteration
- `EvidenceBundleSnapshot`
  stores normalized evidence at each loop stage
- `EvidenceGap`
  stores explicit missing evidence items
- `HypothesisRecord`
  stores candidate causes and confidence
- `VerificationRecord`
  stores pre/post execution validation
- `AutonomyDecisionRecord`
  stores stop/continue/escalate decisions

## API And Service Layer Changes

Track 2 likely requires:

- investigation-run detail endpoint with stage snapshots
- evidence-bundle serialization helpers
- planner result schema
- next-tool selection logic
- verification result schema
- iteration budget and stop-condition logic

It should also push more orchestration logic out of large view functions into dedicated services.

Suggested service modules:

- `genai/autonomy/planner.py`
- `genai/autonomy/evidence.py`
- `genai/autonomy/hypotheses.py`
- `genai/autonomy/decision_gate.py`
- `genai/autonomy/verifier.py`
- `genai/autonomy/runtime_resolution.py`

## UI Requirements

The frontend should show the autonomy loop as a structured investigation timeline.

Useful UI elements:

- current investigation stage
- evidence fetched so far
- contradictions
- confidence trend
- next planned step
- approval requirements
- executed actions
- verification status

The operator should be able to inspect:

- why the control plane chose a step
- what evidence supported the recommendation
- which evidence is missing

## Safety Boundaries

Safety is mandatory.

Required boundaries:

- iteration limits per investigation
- read-only mode by default
- approval-required mode for risky actions
- policy gate before any execution
- target runtime knowledge gate before diagnostics needing local access
- contradiction gate before destructive remediation
- environment-aware restrictions for production

## Learning And Replay

OpsMitra already has ranking and replay primitives. Track 2 should use them more directly.

The autonomy loop should produce learning signals such as:

- which evidence sources were most useful
- which hypotheses were wrong
- whether verification succeeded
- whether the proposed action improved the incident

These should feed:

- remediation ranking
- replay evaluation
- future planner heuristics

## Rollout Plan

### Phase 1: Explicit Investigation State

- add investigation state machine fields
- persist current stage and iteration count
- expose run details in the backend

### Phase 2: Structured Planner Output

- define planner schema
- store missing evidence and hypotheses explicitly
- stop relying on free-form plan text alone

### Phase 3: Evidence Bundle Normalization

- unify metrics/logs/traces/code/topology into one evidence bundle structure
- attach relevance/freshness/confidence metadata

### Phase 4: Next-Step Selection

- add bounded next-tool selection
- support multiple internal evidence-gathering iterations
- add iteration limits and stop conditions

### Phase 5: Verification And Outcome Loop

- formalize post-command verification
- store verification records
- loop back if the incident is not actually resolved

### Phase 6: Learning Integration

- link autonomy decisions to ranking and replay data
- surface loop quality metrics on the operations dashboard

## Recommended Build Order

Implement in this order:

1. investigation state machine
2. planner and evidence-gap schema
3. normalized evidence bundle
4. iterative next-step selection
5. verification records
6. autonomy UI rendering
7. replay and learning integration

## Expected Outcome

With Track 2 implemented, OpsMitra should evolve from:

- a structured single-pass investigation assistant

to:

- a bounded, explainable, multi-step autonomous investigation and remediation orchestrator

It will still remain policy-aware and approval-aware, but it will handle far more of the reasoning loop itself.
