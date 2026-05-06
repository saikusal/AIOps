# Code Context Gap Assessment

This note assesses the current code-context implementation in OpsMitra, what it already does well, and where the major gaps are.

This assessment fits primarily under:

- `Track 2`: [AUTONOMOUS_CONTROL_PLANE_DESIGN.md](./AUTONOMOUS_CONTROL_PLANE_DESIGN.md)

It also relates to:

- `Track 1`: [AGENT_POLICY_AND_RUNTIME_DESIGN.md](./AGENT_POLICY_AND_RUNTIME_DESIGN.md)
  because target/runtime knowledge influences service-to-repo matching
- `Track 3`: [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md)
  because indexed code evidence, changes, and investigation snapshots become part of retained operational memory

## Why This Matters

OpsMitra’s product pitch includes:

- code-context-aware investigation
- code-aware RCA
- route-to-handler lookup
- span-to-symbol mapping
- recent code change correlation

That means the quality of the code-context layer directly affects:

- how well the control plane can reason about incidents
- how accurately it can identify likely failure code paths
- how well it can connect runtime evidence to source evidence

## Current Architecture

The current code-context path is based on:

- local repository indexing
- Django models storing code-context bindings
- targeted code lookup services
- MCP-style tool exposure to the investigation orchestrator

Important components:

- [genai/code_context_ingestion.py](./genai/code_context_ingestion.py)
- [genai/code_context_extractors.py](./genai/code_context_extractors.py)
- [genai/code_context_services.py](./genai/code_context_services.py)
- [genai/mcp_services.py](./genai/mcp_services.py)
- [genai/mcp_orchestrator.py](./genai/mcp_orchestrator.py)

Important data models:

- [RepositoryIndex](./genai/models.py)
- [ServiceRepositoryBinding](./genai/models.py)
- [RouteBinding](./genai/models.py)
- [SpanBinding](./genai/models.py)
- [DeploymentBinding](./genai/models.py)
- [CodeChangeRecord](./genai/models.py)
- [SymbolRelation](./genai/models.py)

## What Is Already Working

### 1. Local repository indexing exists

OpsMitra can register local repositories and persist repository metadata through `RepositoryIndex`.

This is a real, persistent model, not just an in-memory prompt trick.

### 2. Service-to-repo binding exists

The platform can bind runtime services to repositories through `ServiceRepositoryBinding`.

This allows the control plane to answer:

- which repository likely owns a service
- which team likely owns it
- what local repo path should be searched

### 3. Route mapping exists

For Python projects, the system can extract route bindings and map:

- HTTP route
- method
- handler function
- file path

This is useful for application-level RCA.

### 4. Span mapping exists

For Python projects, the system can extract likely span-to-symbol relations from tracing calls.

This lets the control plane connect tracing evidence to probable source locations.

### 5. Recent git change correlation exists

The ingestion path can read recent git history and create `CodeChangeRecord` entries.

This supports:

- “what changed recently”
- “did a recent deployment likely affect this path”

### 6. Targeted snippet reading exists

The control plane can read specific code snippets rather than dumping the entire repository into the LLM prompt.

This is important and correct from an architecture standpoint.

### 7. Traceback-based source reading exists

If logs contain Python traceback paths, the source-reading path can map those paths to local files and read relevant code snippets.

This is particularly useful for Python application failures.

## What The Current System Is Actually Doing

There are two different behaviors:

### 1. Indexing-time scanning

During sync/indexing, the platform broadly scans repositories, especially Python files, to build:

- route bindings
- span bindings
- symbol relations
- queue/task hints
- recent commit records

### 2. Investigation-time retrieval

During an investigation, the platform generally retrieves:

- matching repo owner
- matching route handler
- matching span symbol
- recent changes
- related symbols
- targeted code snippets

So the current architecture is not “dump the whole repo into the LLM.” It is:

- broad scan during indexing
- targeted retrieval during investigation

## Current Repo Selection Logic

Repo selection today is driven mostly by:

- builtin repository registration
- target metadata such as `repo_path` or `repo_name`
- discovered-service metadata when present
- local path guessing from `AIOPS_CODE_CONTEXT_AUTO_ROOTS`

This means the system is currently strongest when:

- repos are local or mounted
- repo ownership is explicitly or predictably named
- service names align with repo names or configured metadata

## Main Gaps

### 1. The extractor is basically Python-only

This is the largest current gap.

The extractor in [genai/code_context_extractors.py](./genai/code_context_extractors.py) focuses on Python AST parsing.

That means current support is weak or missing for:

- JavaScript / TypeScript
- Java
- Go
- C#
- YAML-based routing/config
- Helm
- Terraform
- Kubernetes manifests as first-class code-context evidence

This limits how broadly OpsMitra can claim code-aware RCA across customer stacks.

### 2. Service-to-repo matching is heuristic

Current matching relies mostly on:

- service names
- repo names
- path hints
- discovered-service metadata

This works for demos and disciplined environments but will be fragile in more complex customer estates.

Missing:

- explicit multi-repo onboarding flow
- stronger canonical ownership assignment workflow
- more deterministic service-to-repo mapping

### 3. Search is shallow and mostly token-based

`search_code_context(...)` is currently based on token and substring scoring over:

- route patterns
- symbol names
- span names
- file paths
- relations

This is useful, but it is not a strong semantic retrieval system.

### 4. Symbol graph is shallow

`SymbolRelation` is currently built from relatively simple call extraction.

This means:

- call graph depth is limited
- inter-module understanding is limited
- class/method relation quality is limited
- cross-file dependency reasoning is still shallow

### 5. Deployment-to-code linkage is weak

`DeploymentBinding` exists, but its quality depends heavily on supplied metadata.

The system does not yet robustly know:

- which exact commit is running on which target
- which deployment version maps to which incident without extra metadata
- which runtime artifact corresponds to which repo revision with high confidence

### 6. No strong remote repository integration model

The current model expects:

- local repo clones
- mounted source directories
- locally indexable repositories

Missing:

- GitHub/GitLab/Bitbucket integration flow
- authenticated repo sync model
- branch or revision aware remote fetching
- multi-tenant repo access governance

### 7. Freshness management is limited

There is a sync path, but there is not yet a mature freshness model around:

- scheduled sync policy
- stale index detection
- sync drift warning
- investigation-time warning when code index is old

### 8. Operational config context is weak

For real RCA, source code alone is not enough.

The platform should also understand:

- deployment manifests
- Helm values
- Docker Compose files
- ingress and service definitions
- environment config references
- queue/topic definitions
- migration/config relations

Today the implementation is much stronger on Python code than on adjacent operational config context.

## Honest Current Verdict

The code-context layer is:

- a real implementation
- a good differentiator
- useful for Python-heavy or demo-friendly environments

But it is not yet mature enough to claim:

- universal multi-language source intelligence
- deep deployment-to-code fidelity
- highly reliable service-to-repo mapping across arbitrary estates

The correct current product framing is closer to:

- “code-context aware for indexed local repositories”

than:

- “deep universal source intelligence across all stacks”

## What This Means For The Tracks

### Track 1 Impact

Track 1 needs stronger runtime and service metadata because better service-to-repo binding depends on better target knowledge.

### Track 2 Impact

Track 2 depends directly on this layer.

If code-context quality is weak, the autonomous control plane should:

- lower confidence
- avoid overclaiming code root cause
- ask for more runtime evidence
- treat code suggestions as supportive rather than decisive

So this gap assessment belongs mainly to Track 2.

### Track 3 Impact

Track 3 matters because:

- code evidence snapshots
- change records
- matched snippets
- investigation-time code decisions

become part of retained investigation memory and replay data.

## Recommended Improvement Roadmap

### Phase 1: Strengthen metadata and freshness

- make service-to-repo ownership more explicit
- add stale-index visibility
- improve sync discipline

### Phase 2: Expand language and config coverage

- add TypeScript/JavaScript extraction
- add config/manifests extraction
- improve deployment/config evidence

### Phase 3: Improve retrieval quality

- stronger semantic search
- better snippet ranking
- better symbol relation quality

### Phase 4: Improve deployment fidelity

- stronger runtime-to-version mapping
- stronger deployment binding population
- stronger correlation between incidents and recent changes

## Bottom Line

The current code-context engine is a solid foundation and a credible differentiator.

Its main strengths are:

- local repo indexing
- service ownership
- route and span mapping
- recent change tracking
- targeted snippet retrieval

Its main gaps are:

- language coverage
- matching robustness
- semantic depth
- config/manifests awareness
- deployment fidelity

This should be treated as an active capability track inside the broader autonomous control-plane roadmap, not as a finished subsystem.
