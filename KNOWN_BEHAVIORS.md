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
