## Open Issues

### Issue #001 - Replacement strings truncated to 15 characters

Status: Reported
Disposition: Confirmed implementation bug
Owner: Engineering
Discovered: 2026-07-16
Discovered by: Functional validation suite

Description

Replacement strings longer than 15 characters are truncated by the FPGA.

Impact

Policy authors must currently keep replacement strings ≤15 characters.

Resolution

Engineering has confirmed this is a defect and is implementing a fix.

Regression Test

After the fix is deployed, rerun the functional validation suite with long replacement strings enabled.

# KB-002: Sandbox service accessibility requires execution host

Date: 2026-07-18
Status: Open
Category: Environment / Developer Experience

## Summary

Developer environments cannot directly access sandbox Nol8 services even when connected through the approved VPN tunnel.

## Observed Behavior

- Local development environment resolves:
  - themis.sales.nol8.cloud
  - 10.10.1.254

- HTTPS connectivity attempts from the developer workstation to:
  - :443
  - :8443

  do not complete.

- Validation execution from the local Codex environment cannot reach Themis because it is not running inside the sandbox network.

## Expected Behavior

A developer connected through the approved VPN should be able to access sandbox services required for:

- agent development
- inference testing
- functional validation
- demonstrations
- performance testing

The sandbox should support development workflows without requiring all interaction to originate from a dedicated EC2 execution host.

## Impact

Current architecture creates friction for:
- demos
- troubleshooting
- iterative development
- customer-facing validation workflows

Developers must move workflows onto infrastructure hosts rather than using their normal development environment.

## Recommendation

Evaluate sandbox network access controls to allow authenticated VPN users appropriate access to non-production sandbox services.

Security controls should remain appropriate for production environments, but sandbox environments should optimize for developer productivity and validation workflows.

## Notes

Data used in this environment is synthetic/non-production.
