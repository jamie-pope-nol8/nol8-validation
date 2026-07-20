# Themis Issue Register

Engineering-facing defect and limitation reports for the Themis product,
surfaced while building a validation capability against the evaluation
environment.

**Each `ISSUE-NNN-*.md` here is self-contained and safe to send on its own** -
no repository, no tooling, and no internal references. Reproductions are literal
curl against your own endpoints. You can attach any single file to an email and
an engineer can read, understand, and reproduce it without anything installed.

Send them individually. In particular, keep the data-corruption defect
(ISSUE-004) separate from the lifecycle and environment items, so it is triaged
as the defect it is rather than as product feedback.

| ID | Title | Type | Severity | Status |
|---|---|---|---|---|
| [ISSUE-001](ISSUE-001-deployed-policy-has-no-identity.md) | A deployed policy has no identity | Limitation | High | Open |
| [ISSUE-002](ISSUE-002-deployment-replaces-entire-ruleset.md) | Deployment replaces the entire ruleset | Limitation | High | Open |
| [ISSUE-003](ISSUE-003-deployment-is-fire-and-forget.md) | Deployment is fire-and-forget | Limitation | Medium | Open |
| [ISSUE-004](ISSUE-004-overlapping-matches-corrupt-output.md) | Overlapping matches corrupt output | **Defect** | **High** | Open |
| [ISSUE-005](ISSUE-005-replacements-truncate-at-15-characters.md) | Replacements truncate at 15 characters | Behavior | Medium | Open |
| [ISSUE-006](ISSUE-006-evaluation-environment-unreachable-externally.md) | Evaluation environment is unreachable externally | Environment | High | Open |
| [ISSUE-007](ISSUE-007-no-runtime-health-signal.md) | No way to check whether the runtime is healthy | Limitation | Medium | Open |

**Shared root causes worth naming when reading as a set:**

- ISSUE-001, 002, 003, and 007 are facets of one gap: **the runtime cannot be
  asked about its own state** - not what policy is loaded, not whether it has
  converged, not whether the engine is serving.
- ISSUE-004 is the only outright data-correctness defect. It is the priority.
- ISSUE-006 is an environment-configuration choice, not a defect; it is here
  because it currently blocks demonstrating the product to its most relevant
  buyers.

---

*Internal notes, investigations, and framework-specific material live in
`internal/` and are not for external distribution.*
