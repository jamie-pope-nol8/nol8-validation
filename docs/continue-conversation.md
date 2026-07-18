# Continue Conversation

# Session Operating Rules

These rules are part of the project workflow.

## Execution Style

- Work one action at a time.
- Do not provide batches of commands unless they are inseparable.
- Wait for confirmation before moving to the next action.
- End responses with a clear next action.

## Context Preservation

This is a continuation of an existing engineering effort.

Do not:
- ask the user to re-explain the project
- restart architectural discussions already resolved
- suggest replacing working tooling
- introduce unnecessary frameworks
- assume only one development environment exists

Use the continuation document as the source of truth.

## Development Environments

The project intentionally uses two environments:

- Mac: development and commits
- EC2: execution and Nol8 validation

Both are required.

## Decision Discipline

Before proposing changes:
- understand why the current design exists
- verify whether the issue is real
- prefer incremental fixes over redesign

The objective is productive engineering progress, not exploration of alternatives.

## Nol8 Validation Framework

Last Updated: 2026-07-18

---

# Purpose of This Document

This document exists so future sessions can continue work on this project without reconstructing context from chat history.

This is not a meeting summary.

This is the durable memory of:

- what we are building
- why we are building it
- architectural decisions already made
- decisions that should not be reopened
- current implementation state
- immediate next actions

Update this document at the end of meaningful work sessions.

---

# Project Overview

## What This Project Is

Nol8 Validation Framework is a validation system designed to prove and measure Nol8 behavior through repeatable functional validation runs.

The framework creates deterministic validation scenarios, generates expected outcomes, deploys policies, executes workloads, compares results, and produces reports.

The goal is not simply testing.

The goal is creating a repeatable evidence system for Nol8 capabilities.

---

# Relationship To Larger Work

This framework is a component of the broader AI Chief Engineer effort.

The larger vision is to create systems that improve engineering decision quality by:

- capturing intent
- executing repeatable validation
- producing evidence
- preserving decisions
- reducing ambiguity

The Validation Framework is one concrete implementation of that philosophy.

---

# Core Design Principles

## 1. Small, Explicit Stages

The validation lifecycle is intentionally staged.

Current lifecycle:

```
generate
    |
    v
policy
    |
    v
run
    |
    v
compare
    |
    v
report
    |
    v
clean
```

Each stage has one responsibility.

Do not collapse stages together.

---

## 2. Artifacts Are First Class

Validation runs produce durable artifacts.

Example:

```
artifacts/
└── runs/
    └── <run-id>/
        ├── manifest.json
        ├── config/
        └── generated/
            ├── input.jsonl
            ├── expected.jsonl
            ├── scale-policy.nol
            ├── generation-manifest.json
            └── output.jsonl
```

The run directory is the source of truth for a validation execution.

---

## 3. Manifest Driven State

The manifest records lifecycle state.

Stages should update the manifest atomically.

Do not create hidden state outside the run artifacts.

---

## 4. Transport Boundaries

Python owns:

- orchestration
- validation logic
- stage lifecycle
- artifact management

Shell transport owns:

- endpoint selection
- authentication
- curl execution
- HTTP transport details

Python should not:

- know tokens
- build Authorization headers
- call curl directly

---

# Repository

GitHub:

```
https://github.com/jamie-pope-nol8/nol8-validation
```

Primary working environments:

## Mac

Purpose:

- development
- editing
- Codex work
- commits

Python:

```
3.12
```

Path:

```
~/Code/nol8/nol8-validation
```

---

## EC2

Purpose:

- execution against Nol8 infrastructure
- FPGA/backend validation
- live environment testing

Path:

```
/opt/nol8/nol8-validation
```

Python:

```
3.14.4
```

Note:

Python versions differ between environments.

Do not assume they match.

---

# Python Environment

The project uses:

```
.venv
```

on both environments.

Standard workflow:

```
source .venv/bin/activate
python -m pip install -e .
```

The project is installed as an editable package.

---

# CLI

The intended interface is:

```
validate
```

Not:

```
python -m framework.cli
```

The console entry point is:

```toml
[project.scripts]
validate = "framework.cli.main:main"
```

Important:

The previous entry:

```
framework.cli:main
```

was incorrect because it resolved to the module rather than the callable function.

---

# Packaging

The project contains:

```
pyproject.toml
```

Dependencies currently include:

- requests
- PyYAML

Editable install creates generated metadata:

```
nol8_validation.egg-info
```

This is generated content.

It must not be committed.

Required cleanup:

```
*.egg-info/
```

should exist in `.gitignore`.

---

# Completed Features

## validate generate

Status:

COMPLETE

Purpose:

Creates a validation run.

Responsibilities:

- create run directory
- generate input corpus
- generate expected results
- generate policy artifact
- create manifest

---

## validate policy

Status:

COMPLETE

Purpose:

Deploy generated policy to Nol8 Themis.

Target:

```
themis
```

Responsibilities:

- verify run state
- verify generated policy exists
- verify policy hash
- deploy policy
- record sanitized response

Confirmed Themis response:

```json
{
  "ok": true,
  "command_id": "cmd-367",
  "stage": "apollo",
  "message": "loaded 60 rule(s) into native apollo via reload_rules (persisted, REPLACE)",
  "error_code": null,
  "apollo_response": "OK reload_rules dispatched",
  "rules": 60
}
```

A real deployment was successfully executed from EC2.

---

## validate run

Status:

COMPLETE

Purpose:

Execute generated validation corpus.

Responsibilities:

- read generated input
- send requests sequentially
- record output
- update manifest

Output:

```
generated/output.jsonl
```

Transport:

- bounded curl timeout
- bearer authentication
- no secrets persisted

---

# Remaining Features

## validate compare

Status:

NOT STARTED

Purpose:

Compare expected results against actual execution output.

Important design question:

Expected:

```
generated/expected.jsonl
```

uses:

```
record_id
```

Output:

```
generated/output.jsonl
```

uses:

```
request_index
```

Comparison should establish deterministic alignment.

Likely approach:

1. verify corpus lengths match
2. align by original execution order
3. validate record identity
4. compare expected vs actual
5. produce comparison artifact

Do not implement until schemas are reviewed.

---

## validate report

Status:

NOT STARTED

Purpose:

Generate human-readable validation results.

Depends on:

```
validate compare
```

---

## validate clean

Status:

NOT STARTED

Purpose:

Remove temporary artifacts.

---

# Working Style

Required:

- one action at a time
- confirm before proceeding
- do not create speculative work
- preserve completed decisions

The project is intentionally built incrementally.

---

# Current Checkpoint

Date:

2026-07-18

Current state:

COMPLETE:

- repository migrated to packaged Python project
- venv workflow established
- validate CLI working on Mac
- validate CLI working on EC2
- generate complete
- policy complete
- run complete

Remaining immediate work:

1. Ensure egg-info cleanup is complete.
2. Commit any remaining repository hygiene fixes.
3. Begin validate compare.

---

# Next Session Starting Point

Start by reviewing:

- generated/expected.jsonl
- generated/output.jsonl
- manifest.json

Then design validate compare.

Do not start coding until the comparison contract is clear.
