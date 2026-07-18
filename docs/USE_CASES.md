# Nol8 Validation Framework Use Cases

## Purpose

This document defines the real-world workloads that the Nol8 Validation Framework must represent.

The goal is to ensure validation reflects realistic customer deployments rather than synthetic benchmark data.

Each use case describes:

- What the workload represents
- Typical payload formats
- Typical policy content
- Success criteria
- Validation scenarios
- Future performance objectives

---

# Use Case 1: AI Data Plane / Pre-Inference Inspection

## Description

Inspect prompts, retrieved documents, tool output, and agent context before data is sent to an LLM.

## Typical Payloads

- Plain text
- Markdown
- JSON
- HTML
- XML

## Typical Policies

- Customer identifiers
- Internal project names
- API keys
- Secrets
- Regulated data
- Customer-specific deny lists

## Example Scenarios

- Prompt sanitization
- RAG document inspection
- Agent tool output filtering
- Context window protection

---

# Use Case 2: Enterprise Data Loss Prevention

## Description

Inspect outbound enterprise content before it leaves organizational boundaries.

## Typical Payloads

- Email
- Support tickets
- Chat messages
- Reports
- HTML pages
- JSON API responses

## Typical Policies

- PII
- Financial identifiers
- Healthcare identifiers
- Intellectual property
- Internal code names

## Example Scenarios

- Email redaction
- Customer export validation
- Document sanitization

---

# Use Case 3: Log and Telemetry Sanitization

## Description

Remove sensitive information before logs are stored or exported.

## Typical Payloads

- Application logs
- Access logs
- JSON events
- Stack traces

## Typical Policies

- Authorization headers
- JWTs
- API keys
- Session IDs
- Customer identifiers

## Example Scenarios

- SIEM ingestion
- Cloud logging
- Debug log export

---

# Use Case 4: Document and Record Sanitization

...

---

# Use Case 5: Agent-to-Agent / Agent-to-Tool Policy Enforcement

...

---

# Candidate Future Use Cases

- Healthcare pipelines
- Financial transaction inspection
- Source code scanning
- CI/CD artifact validation
- Streaming Kafka topics
- Multi-part message validation
- Multi-tenant policy isolation