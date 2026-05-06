# Track 1: Agent Policy And Runtime Design

This is Track 1 of the OpsMitra autonomy and operations architecture plan.

Related tracks:

- `Track 2`: [AUTONOMOUS_CONTROL_PLANE_DESIGN.md](./AUTONOMOUS_CONTROL_PLANE_DESIGN.md)
- `Track 3`: [DATA_MEMORY_LIFECYCLE_DESIGN.md](./DATA_MEMORY_LIFECYCLE_DESIGN.md)
- `Track 4`: [INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md](./INTEGRATIONS_AND_TELEMETRY_ADAPTERS_DESIGN.md)

This document defines how OpsMitra should handle target-side agent permissions, runtime knowledge, log-source awareness, and post-onboarding policy refresh.

The goal is to avoid a brittle model where:

- every server gets the same permissions,
- the agent assumes all logs live in `/var/log`,
- role changes require agent reinstallation,
- command execution is broader than necessary.

Instead, OpsMitra should install the base agent once and manage behavior through target-specific configuration.

## Design Goals

For every onboarded target, OpsMitra should know:

- what kind of server it is
- what runtime it uses
- which workloads matter
- where logs come from
- how restart/diagnostic actions should work
- what commands are allowed
- what actions need approval
- what actions are completely blocked

The base agent should remain installed, while policy and runtime knowledge can be updated later without reinstalling the agent.

## Core Principles

1. Install the agent once.
2. Keep permissions target-specific.
3. Separate telemetry collection from command execution.
4. Treat runtime knowledge as first-class data.
5. Use discovery to suggest configuration, not to replace operator confirmation.
6. Use defense in depth:
   backend authorization, policy evaluation, and agent-side enforcement.

## Problem Statement

Linux and Docker-based targets do not follow a single standard layout:

- logs may come from `journald`
- logs may live in `/var/log/...`
- logs may live in app-specific paths such as `/opt/app/logs`
- logs may come from `docker logs`
- a server may change roles over time
- a server may start as app-only and later host a database

Because of this:

- permissions should not be global
- log retrieval should not assume one filesystem path
- restart behavior should not assume one service name
- onboarding must capture operator-confirmed runtime knowledge

## Architecture Overview

OpsMitra should manage two connected layers per target:

1. `Execution policy`
   What the agent is allowed to do on that target.
2. `Runtime knowledge`
   How that target is actually set up.

These layers should be stored in the control plane, surfaced in the UI, and rendered into a generated agent config.

Track 1 also owns `target-side centralized log ingestion configuration`.

That includes:

- identifying the correct log sources on each target
- attaching normalized target metadata to shipped log records
- generating target-specific shipper configuration
- deciding which central log stream family a target writes into

So Track 1 is not only about execution policy. It is also about source-aware log collection setup.

## Target-Specific Permission Model

Permissions should be target-specific, or at minimum profile-based with per-target overrides.

Examples:

- App server:
  - allow `systemctl status`
  - allow `journalctl`
  - allow `docker logs`
  - maybe allow `docker restart` for approved containers
- Database server:
  - allow read-only DB diagnostics
  - deny generic app restart commands
  - deny Docker commands if Docker is not part of the runtime
- Critical production server:
  - allow read-only diagnostics
  - require approval for restart
  - block broad write actions

OpsMitra should never assume one global permission set for all Linux targets.

## Permission Layers

OpsMitra should enforce permissions at three layers:

1. `User permissions`
   What the operator is allowed to request in the product.
2. `Policy permissions`
   What the target configuration allows or requires approval for.
3. `Execution permissions`
   What the local agent or cluster agent can actually execute.

All three layers must align before a command is executed.

## Linux Agent Privilege Model

The Linux host agent may need elevated privileges, but it should not have unrestricted root shell behavior.

Recommended approach:

- run the agent as a dedicated service user
- grant `sudo` only for specific commands through `sudoers`
- use command templates and allowlists
- log every executed action
- block arbitrary shell execution

Avoid by default:

- arbitrary `bash -c`
- arbitrary `sh -c`
- arbitrary `python -c`
- arbitrary `psql` write access
- arbitrary file deletion
- package installation

Examples of commands that may be allowed:

- `systemctl status <approved-service>`
- `systemctl restart <approved-service>`
- `journalctl -u <approved-service>`
- `ss -tulpn`
- `docker ps`
- `docker logs <approved-container>`
- `docker inspect <approved-container>`
- `docker restart <approved-container>`

## Runtime Knowledge Model

OpsMitra needs a per-target knowledge model because infrastructure layouts vary.

For each target, the control plane should know:

- target role: `app`, `db`, `cache`, `gateway`, `custom`
- environment: `prod`, `staging`, `dev`
- runtime type: `systemd`, `docker`, `standalone`, `kubernetes`
- approved services
- approved containers
- primary log source
- centralized log stream family
- restart method
- DB type if relevant

Examples:

- `orders-prod-01`
  - role: `app`
  - runtime: `docker`
  - logs: `docker logs orders-api`
  - restart: `docker restart orders-api`

- `billing-vm-02`
  - role: `app`
  - runtime: `systemd`
  - logs: `journald` unit `billing-api`
  - restart: `systemctl restart billing-api`

- `db-prod-01`
  - role: `db`
  - runtime: `systemd`
  - logs: custom file path or journald
  - DB diagnostics: read-only only

## Proposed Data Model

Add first-class target configuration models to the control plane.

### 1. `TargetPolicyProfile`

Reusable policy templates, such as:

- `linux-readonly`
- `linux-app-systemd`
- `linux-app-docker`
- `linux-db-readonly`
- `prod-restricted`

Suggested fields:

- `name`
- `target_type`
- `runtime_type`
- `description`
- `allow_service_status`
- `allow_service_restart`
- `allow_docker_logs`
- `allow_docker_restart`
- `allow_journal_logs`
- `allow_file_logs`
- `allow_db_diagnostics`
- `allow_db_changes`
- `allow_process_kill`
- `requires_approval_for_restart`
- `requires_approval_for_write_actions`
- `sudo_mode`
- `allowed_command_patterns`

### 2. `TargetPolicyAssignment`

Binds a specific target to a base policy profile plus overrides.

Suggested fields:

- `target`
- `policy_profile`
- `override_json`
- `config_version`
- `last_applied_at`
- `last_apply_status`

### 3. `TargetRuntimeProfile`

Stores runtime metadata for the target.

Suggested fields:

- `target`
- `role`
- `environment`
- `runtime_type`
- `hostname`
- `os_family`
- `docker_available`
- `systemd_available`
- `primary_restart_mode`
- `notes`

### 4. `TargetServiceBinding`

Maps business services to local runtime objects.

Suggested fields:

- `target`
- `service_name`
- `service_kind`
- `systemd_unit`
- `container_name`
- `process_name`
- `port`
- `is_primary`
- `restart_command_template`
- `status_command_template`

Where `service_kind` may be:

- `systemd`
- `docker_container`
- `process`
- `database`

### 5. `TargetLogSource`

Stores one or more log sources for the target.

Suggested fields:

- `target`
- `source_type`
- `service_binding`
- `journal_unit`
- `file_path`
- `container_name`
- `parser_type`
- `is_primary`

Where `source_type` may be:

- `journald`
- `file`
- `docker`
- `database`

Suggested additional fields:

- `stream_family`
- `parser_name`
- `include_patterns`
- `exclude_patterns`
- `shipper_type`

### 6. `TargetLogIngestionProfile`

Stores generated centralized log-ingestion intent for a target.

Suggested fields:

- `target`
- `shipper_type`
- `stream_family`
- `opensearch_pipeline`
- `record_metadata_json`
- `config_version`
- `last_applied_at`
- `last_apply_status`

## Agent Config Design

The agent should not rely on hardcoded permissions. It should receive a generated config from the control plane.

Example shape:

```json
{
  "target_id": "target_123",
  "profile": "linux-app-docker",
  "config_version": 3,
  "runtime": {
    "role": "app",
    "runtime_type": "docker"
  },
  "allowed_actions": {
    "service_status": true,
    "service_restart": false,
    "docker_logs": true,
    "docker_restart": true,
    "db_diagnostics": false
  },
  "bindings": {
    "services": [
      {
        "name": "orders-api",
        "kind": "docker_container",
        "container_name": "orders-api"
      }
    ],
    "logs": [
      {
        "source_type": "docker",
        "container_name": "orders-api",
        "primary": true
      }
    ]
  }
}
```

This config should be:

- generated by the control plane
- fetched during enrollment and refresh
- versioned
- auditable

Track 1 should treat target-side log shipper config the same way:

- generated by the control plane
- tied to runtime knowledge and onboarding choices
- versioned
- refreshable without reinstalling the agent bundle

## Centralized Log Ingestion In Track 1

Centralized log ingestion belongs primarily to Track 1.

Why:

- it depends on target runtime knowledge
- it depends on target-specific log source selection
- it depends on onboarding/operator confirmation
- it depends on generated target-side shipper configuration

Track 1 should therefore define:

- which shipper runs on a target
- how `journald`, file, Docker, and later Kubernetes log sources are modeled
- how target metadata is attached to emitted records
- which OpenSearch stream family a target writes into

### Recommended Direction

For the current product direction:

- centralized logs are required
- target-side agent-only log retrieval is fallback, not primary
- Fluent Bit is a suitable shipper choice for Linux targets

### Important Constraint

Track 1 should explicitly reject `per-host` or `per-app` index creation patterns such as:

- `servername-appname-date`
- `ip-dbname-date`

These patterns would create too many small indices or streams and do not scale well operationally.

Instead, Track 1 should define:

- a small number of OpenSearch stream families
- normalized metadata fields on each log event
- field-based querying by the control plane

### Suggested Stream Families

Examples:

- `logs-linux-default`
- `logs-docker-default`
- `logs-kubernetes-default`
- `logs-database-default`

### Suggested Log Metadata Fields

At minimum, Track 1 should ensure centralized logs carry:

- `@timestamp`
- `target_id`
- `hostname`
- `ip_address`
- `environment`
- `target_type`
- `runtime_type`
- `service_name`
- `application`
- `component_role`
- `container_name`
- `k8s_namespace`
- `k8s_workload`
- `log_source_type`
- `message`
- `severity`
- `trace_id` when available

### Fluent Bit Role

Fields should be attached primarily in generated Fluent Bit config, based on target-specific onboarding and runtime knowledge.

OpenSearch ingest pipelines can then do:

- normalization
- cleanup
- light enrichment

## Discovery Versus Configuration

OpsMitra should use both discovery and operator confirmation.

Discovery should suggest:

- whether `systemd` is available
- whether Docker is available
- running services
- containers
- listening ports
- likely journald units
- likely DB daemons

The operator should confirm:

- which services/containers are important
- which log source is primary
- which actions are allowed
- which role the target should be treated as

Do not rely on discovery alone for policy decisions.

## Onboarding UX Requirements

Yes, this must be captured in the UI during onboarding.

Recommended Linux onboarding flow:

### Step 1: Connection

- host or IP
- SSH user
- auth method

### Step 2: Detected Runtime

Show discovery results such as:

- systemd available or not
- Docker available or not
- common services found
- listening ports found

### Step 3: Target Classification

Operator selects:

- role: `app`, `db`, `cache`, `gateway`, `custom`
- environment: `prod`, `staging`, `dev`
- runtime type, with a discovery-based suggestion

### Step 4: Service Mapping

Operator confirms:

- primary app service or container
- optional secondary services
- DB service if present

### Step 5: Log Source

Operator selects:

- `journald`
- `file path`
- `docker logs`
- `custom`

If file:

- capture the file path

If journald:

- capture the unit name

If Docker:

- capture the container name

Also capture centralized ingestion details when relevant:

- whether the source ships centrally
- stream family selection when applicable
- parser choice when known
- include and exclude patterns for file sources

### Step 6: Execution Policy

Operator selects a policy profile, such as:

- `Readonly`
- `App Standard`
- `App Docker`
- `DB Readonly`
- `Restricted Prod`

Optional toggles:

- allow restart
- require approval for restart
- allow DB diagnostics
- allow file-log reads

### Step 7: Review And Install

Show:

- what will be installed
- what permissions will be granted
- what commands will be allowed

## Post-Onboarding Configuration UI

This is required in addition to onboarding.

OpsMitra should provide a `Target Configuration` page where operators can edit:

- target role
- runtime type
- service bindings
- log sources
- log ingestion profile
- policy profile
- approval rules

Actions on that page:

- `Save`
- `Push agent config`

This is what allows a server to change from app to DB without reinstalling the agent.

## Policy Refresh Flow

The agent should usually be reconfigured, not reinstalled.

Recommended flow:

1. operator updates the target config in the UI
2. control plane stores a new config version
3. agent fetches the updated config on heartbeat or via refresh
4. agent applies the new local config
5. Fleet shows the applied config version and status

Suggested status fields:

- `config_version`
- `last_config_applied_at`
- `last_config_status`

## Linux Sudoers Strategy

Policy profiles should drive both:

- backend authorization rules
- generated `sudoers` snippets

That means onboarding or config refresh should be able to update a target-specific `sudoers` file matching the selected policy profile.

The design target is:

- one installed agent
- updateable local command scope
- no requirement to reinstall when the server role changes

## Track 1 Deliverables

Track 1 should explicitly include:

- target policy models
- target runtime knowledge models
- target service binding models
- target log source models
- target log-ingestion profile models
- onboarding UI for runtime and log source selection
- generated Fluent Bit config from target metadata
- config refresh without reinstall

## Kubernetes Alignment

The same design idea applies to Kubernetes:

- one installed cluster agent
- target-specific or cluster-specific policy profile
- read-only and operations-enabled modes
- RBAC aligned with allowed actions

For Kubernetes, permissions are enforced through:

- control-plane policy
- cluster-agent checks
- Kubernetes RBAC

## Rollout Plan

### Phase 1: Data Model And Defaults

- add the target policy/runtime models
- seed default policy profiles
- store target runtime and policy separately from telemetry-only onboarding

### Phase 2: Onboarding UI

- extend Linux onboarding UI with role/runtime/log-source/policy steps
- persist configuration choices during onboarding
- show a review screen before install

### Phase 3: Agent Config Generation

- add a generated target config JSON endpoint
- render config from target policy + runtime knowledge
- add config versioning

### Phase 4: Agent Refresh

- update the Linux agent to fetch/apply refreshed config
- expose `last_config_applied_at` and `last_config_status`
- avoid reinstall for role changes

### Phase 5: Sudoers And Enforcement Hardening

- generate target-specific `sudoers` snippets
- tighten command templates
- align agent-side enforcement with target config

### Phase 6: Drift Detection

- detect runtime changes
- warn when a target no longer matches its configured role
- prompt the operator to review policy

## Recommended Build Order

Implement in this order:

1. backend models
2. seeded policy profiles
3. onboarding UI fields and workflow
4. target configuration page
5. generated agent config endpoint
6. agent config refresh support
7. `sudoers` generation and enforcement hardening

## Expected Outcome

With this design:

- agents are installed once
- target permissions are server-specific
- role changes do not require reinstall in the normal case
- log sources are explicit rather than guessed blindly
- restarts and diagnostics are approval-aware
- the system is safer than a broad “agent can run anything” model

## Summary

OpsMitra should treat target-side agents as long-lived executors whose behavior is controlled by:

- target-specific policy profiles
- target runtime knowledge
- operator-confirmed onboarding data
- updateable generated config
- narrow local privilege scope

This is the correct foundation for Linux, Linux with Docker, and later more mature policy handling across Kubernetes as well.
