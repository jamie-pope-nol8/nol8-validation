"""Aggregate validation evidence and render a portable HTML report."""

from __future__ import annotations

from collections import Counter
from html import escape
from typing import Any, Mapping, Sequence


def _text(value: Any, default: str = "unavailable") -> str:
    if value is None:
        return default
    return str(value)


def _percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _table(rows: Sequence[tuple[str, Any]]) -> str:
    body = "".join(
        "<tr><th>" + escape(label) + "</th><td>" + escape(_text(value)) + "</td></tr>"
        for label, value in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


def _distribution_table(title: str, values: Mapping[str, Any]) -> str:
    if not values:
        return f"<h3>{escape(title)}</h3><p>Unavailable</p>"
    rows = "".join(
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
        for key, value in sorted(values.items())
    )
    return (
        f"<h3>{escape(title)}</h3>"
        "<table><thead><tr><th>Name</th><th>Count</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _inconclusive_note(
    evidence: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> str:
    """Explain inconclusive records, and name the tokens responsible."""

    if not evidence.get("inconclusive"):
        return ""

    collisions = comparison.get("replacement_collisions")
    limit = comparison.get("replacement_max_length")

    detail = ""
    if isinstance(collisions, Mapping):
        examples = collisions.get("examples")
        if isinstance(examples, Mapping) and examples:
            rows = "".join(
                "<tr>"
                f"<td><code>{escape(str(prefix))}</code></td>"
                f"<td>{escape(', '.join(str(value) for value in replacements))}</td>"
                "</tr>"
                for prefix, replacements in examples.items()
                if isinstance(replacements, Sequence)
                and not isinstance(replacements, (str, bytes))
            )
            truncated = (
                f"<p class=\"muted\">Showing {len(examples)} of "
                f"{collisions.get('count')} colliding tokens.</p>"
                if collisions.get("truncated")
                else ""
            )
            detail = (
                "<table><thead><tr><th>Truncated to</th>"
                "<th>Produced by these replacements</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>{truncated}"
            )

    return (
        '<div class="status-warning" '
        'style="padding:10px 16px;border:1px solid var(--warning);'
        'border-radius:4px;margin:16px 0;">'
        f"<p><strong>{evidence['inconclusive']} record(s) could not be "
        "confirmed as passes.</strong> Their output matched what was expected, "
        f"but two or more replacement tokens become identical once truncated "
        f"to {escape(_text(limit))} characters. Where that happens, a record "
        "in which the wrong rule fired is indistinguishable from one in which "
        "the right rule fired, so a pass cannot be established.</p>"
        "<p>This is a limit of the comparison, not an observed product "
        "failure. Give the affected rules replacements that differ within the "
        "first "
        f"{escape(_text(limit))} characters and re-run to resolve it.</p>"
        f"{detail}"
        "</div>"
    )


# Failure-detail rendering (FW-6). Failing reports used to be one full-document
# <article> per failing row - at scale, megabytes of undifferentiated blocks
# with no way to see the shape of what failed. Instead we classify each failure
# by an explainable signature, group by signature, and show a few compact diffs
# per group. Signatures describe the observed SHAPE of the divergence; they do
# not assert a root cause, which the reader infers.

# Representatives shown in full per signature group. The rest are named by
# record_id (cheap, complete traceability) but not dumped.
_MAX_REPRESENTATIVES = 3
# Characters of shared context kept before the first divergence, and of each
# side's tail kept after it, in a compact diff window.
_DIFF_CONTEXT = 48
_DIFF_TAIL = 96


def _mismatch_shape(expected: Any, actual: Any) -> str:
    """Label the factual shape of a content mismatch, not its cause."""

    if not isinstance(expected, str) or not isinstance(actual, str):
        return "Content mismatch (message unavailable)"
    if expected == actual:
        # Defensive: a mismatch row should differ, but never mislabel it.
        return "Content mismatch (messages reported identical)"
    length_expected, length_actual = len(expected), len(actual)
    if length_actual < length_expected and expected.startswith(actual):
        return "Actual is a prefix of expected (consistent with truncation)"
    if length_expected < length_actual and actual.startswith(expected):
        return "Actual extends expected (extra trailing content)"
    if length_actual < length_expected:
        return "Actual shorter than expected (content lost)"
    if length_actual > length_expected:
        return "Actual longer than expected"
    return "Same length, content differs"


def classify_failure(row: Mapping[str, Any]) -> str:
    """Return an explainable signature grouping like failures together."""

    status = str(row.get("status") or "unknown")
    if status == "EXECUTION_FAILURE":
        http_status = row.get("http_status")
        if isinstance(http_status, int):
            return f"Execution failure (HTTP {http_status})"
        return "Execution failure (no response)"
    if status == "CONTENT_MISMATCH":
        return _mismatch_shape(row.get("expected_message"), row.get("actual_message"))
    # Any other non-pass, non-inconclusive status we did not anticipate is kept
    # as its own group rather than being silently folded in.
    return status


def group_failures(
    failures: Sequence[Mapping[str, Any]],
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """Group failures by signature, ordered by size then name (deterministic)."""

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in failures:
        groups.setdefault(classify_failure(row), []).append(row)
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def _first_divergence(expected: str, actual: str) -> int:
    """Index of the first byte at which two strings differ."""

    limit = min(len(expected), len(actual))
    index = 0
    while index < limit and expected[index] == actual[index]:
        index += 1
    return index


def _compact_diff(expected: str, actual: str) -> str:
    """A windowed diff around the first divergence, each side capped."""

    offset = _first_divergence(expected, actual)
    start = max(0, offset - _DIFF_CONTEXT)
    common = expected[start:offset]
    expected_tail = expected[offset : offset + _DIFF_TAIL]
    actual_tail = actual[offset : offset + _DIFF_TAIL]
    lead = "…" if start > 0 else ""
    expected_more = "…" if len(expected) > offset + _DIFF_TAIL else ""
    actual_more = "…" if len(actual) > offset + _DIFF_TAIL else ""
    return (
        "<div class='diff'>"
        f"<p class='muted'>First difference at byte {offset} "
        f"(expected {len(expected)} bytes, actual {len(actual)} bytes).</p>"
        f"<pre class='diff-common'>{escape(lead + common)}</pre>"
        "<pre class='diff-expected'><span class='diff-label'>expected</span>"
        f"{escape(expected_tail + expected_more)}</pre>"
        "<pre class='diff-actual'><span class='diff-label'>actual</span>"
        f"{escape(actual_tail + actual_more)}</pre>"
        "</div>"
    )


def _match_evidence_table(row: Mapping[str, Any]) -> str:
    match_rows = []
    matches = row.get("expected_matches")
    if isinstance(matches, list):
        for match in matches:
            if not isinstance(match, Mapping):
                continue
            match_rows.append(
                "<tr>"
                f"<td>{escape(_text(match.get('category_id')))}</td>"
                f"<td>{escape(_text(match.get('case_id')))}</td>"
                f"<td><code>{escape(_text(match.get('variant')))}</code></td>"
                f"<td><code>{escape(_text(match.get('replacement')))}</code></td>"
                "</tr>"
            )
    if not match_rows:
        return "<p>No expected matches.</p>"
    return (
        "<table><thead><tr><th>Category</th><th>Case</th><th>Variant</th>"
        "<th>Replacement</th></tr></thead><tbody>"
        + "".join(match_rows)
        + "</tbody></table>"
    )


def _failure_representative(row: Mapping[str, Any]) -> str:
    """Render one representative: compact diff where possible, then full detail."""

    expected = row.get("expected_message")
    actual = row.get("actual_message")
    if isinstance(expected, str) and isinstance(actual, str) and expected != actual:
        anchor = _compact_diff(expected, actual)
    else:
        # Execution failures (and any row without both messages) have no diff
        # to anchor on; the facts table below carries the evidence.
        anchor = ""
    facts = _table(
        (
            ("Request index", row.get("request_index")),
            ("Record kind", row.get("kind")),
            ("HTTP status", row.get("http_status")),
            ("Latency (ms)", row.get("latency_ms")),
            ("Error", row.get("error")),
        )
    )
    return (
        "<article class='failure'>"
        f"<h4>{escape(_text(row.get('record_id')))}</h4>"
        + anchor
        + facts
        + "<details><summary>Full expected and actual messages</summary>"
        f"<h5>Expected</h5><pre>{escape(_text(expected))}</pre>"
        f"<h5>Actual</h5><pre>{escape(_text(actual))}</pre>"
        "</details>"
        "<details><summary>Expected match evidence</summary>"
        + _match_evidence_table(row)
        + "</details>"
        "</article>"
    )


def render_failure_section(failures: Sequence[Mapping[str, Any]]) -> str:
    """Grouped, compact failure details: a summary table then a few examples."""

    if not failures:
        return "<p>No comparison failures.</p>"

    groups = group_failures(failures)
    summary_rows = "".join(
        "<tr>"
        f"<td>{escape(signature)}</td>"
        f"<td>{len(rows)}</td>"
        f"<td>{escape(_text(rows[0].get('record_id')))}</td>"
        "</tr>"
        for signature, rows in groups
    )
    summary = (
        f"<p>{len(failures)} failing record(s) across {len(groups)} signature(s). "
        "Each signature describes the observed shape of the divergence, not a "
        "diagnosed cause.</p>"
        "<table><thead><tr><th>Signature</th><th>Count</th>"
        "<th>First example</th></tr></thead>"
        f"<tbody>{summary_rows}</tbody></table>"
    )

    sections = []
    for signature, rows in groups:
        representatives = "".join(
            _failure_representative(row) for row in rows[:_MAX_REPRESENTATIVES]
        )
        if len(rows) > _MAX_REPRESENTATIVES:
            remaining = rows[_MAX_REPRESENTATIVES:]
            dropped = (
                f"<p class='muted'>Showing {_MAX_REPRESENTATIVES} of {len(rows)} "
                "in this group. Remaining record IDs are listed below; their full "
                "detail is omitted to keep the report readable.</p>"
                "<details><summary>"
                f"{len(remaining)} further record ID(s)</summary><p><code>"
                + escape(
                    ", ".join(_text(row.get("record_id")) for row in remaining)
                )
                + "</code></p></details>"
            )
        else:
            dropped = ""
        sections.append(
            "<section class='signature'>"
            f"<h3>{escape(signature)} <span class='muted'>× {len(rows)}</span></h3>"
            + representatives
            + dropped
            + "</section>"
        )

    return summary + "".join(sections)


def aggregate_evidence(
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    comparison_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Produce report metrics without changing validation outcomes."""

    outcomes = Counter(str(row.get("status", "unknown")) for row in comparison_rows)
    kinds = Counter(str(row.get("kind", "unknown")) for row in comparison_rows)
    categories: Counter[str] = Counter()
    cases: Counter[str] = Counter()
    expected_replacements = 0
    latencies: list[float] = []
    failures: list[Mapping[str, Any]] = []

    for row in comparison_rows:
        if row.get("status") not in ("PASS", "INCONCLUSIVE"):
            failures.append(row)
        latency = row.get("latency_ms")
        if isinstance(latency, (int, float)):
            latencies.append(float(latency))
        count = row.get("expected_match_count")
        if isinstance(count, int):
            expected_replacements += count
        matches = row.get("expected_matches")
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, Mapping):
                continue
            category = match.get("category_id")
            case = match.get("case_id")
            if isinstance(category, str):
                categories[category] += 1
            if isinstance(case, str):
                cases[case] += 1

    total = len(comparison_rows)
    passed = outcomes["PASS"]
    # An inconclusive record is neither a pass nor a product failure: the
    # output matched, but truncation made the comparison unable to tell which
    # rule produced it. Counting it as failed would blame the product for a
    # limit of the comparison; counting it as passed would certify what was
    # never established.
    inconclusive = outcomes["INCONCLUSIVE"]
    return {
        "total": total,
        "passed": passed,
        "inconclusive": inconclusive,
        "failed": total - passed - inconclusive,
        "pass_rate": passed / total * 100 if total else 0.0,
        "outcomes": outcomes,
        "kinds": kinds,
        "categories": categories,
        "cases": cases,
        "expected_replacements": expected_replacements,
        "failures": failures,
        "latency": {
            "minimum": min(latencies) if latencies else 0.0,
            "average": sum(latencies) / len(latencies) if latencies else 0.0,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "maximum": max(latencies) if latencies else 0.0,
        },
        "generation": generation,
        "manifest": manifest,
    }


def render_report_html(evidence: Mapping[str, Any]) -> str:
    """Render self-contained, escaped HTML from aggregated evidence."""

    manifest = evidence["manifest"]
    generation = evidence["generation"]
    stages = manifest.get("stages", {}) if isinstance(manifest, Mapping) else {}
    policy = stages.get("policy", {}) if isinstance(stages, Mapping) else {}
    run = stages.get("run", {}) if isinstance(stages, Mapping) else {}
    comparison = stages.get("comparison", {}) if isinstance(stages, Mapping) else {}
    configuration = manifest.get("configuration", {})

    workload_name = generation.get("workload_name", generation.get("test_name"))
    requested_records = generation.get(
        "requested_records", generation.get("record_count")
    )
    realized_records = generation.get(
        "realized_records", generation.get("record_count")
    )
    requested_rules = generation.get(
        "requested_rules", generation.get("policy_rule_count")
    )
    realized_rules = generation.get(
        "realized_rules", generation.get("policy_rule_count")
    )

    policy_response = policy.get("response", {})
    if not isinstance(policy_response, Mapping):
        policy_response = {}
    requests_completed = run.get("requests_completed")
    harness_runtime = run.get("total_runtime_seconds")
    completed_count = (
        float(requests_completed)
        if isinstance(requests_completed, (int, float))
        else 0.0
    )
    runtime_seconds = (
        float(harness_runtime)
        if isinstance(harness_runtime, (int, float))
        else 0.0
    )
    harness_throughput = (
        completed_count / runtime_seconds if runtime_seconds > 0 else 0.0
    )
    rules_deployed = policy_response.get("rules", realized_rules)
    input_payload_bytes = generation.get("payload_bytes_total")
    input_payload_size = (
        f"{input_payload_bytes} bytes"
        if isinstance(input_payload_bytes, (int, float))
        else "unavailable"
    )

    artifacts = manifest.get("artifacts", {})
    artifact_rows = []
    if isinstance(artifacts, Mapping):
        for name, metadata in sorted(artifacts.items()):
            if not isinstance(metadata, Mapping):
                continue
            artifact_rows.append(
                "<tr>"
                f"<td>{escape(str(name))}</td>"
                f"<td>{escape(_text(metadata.get('path')))}</td>"
                f"<td><code>{escape(_text(metadata.get('sha256')))}</code></td>"
                f"<td>{escape(_text(metadata.get('size_bytes')))}</td>"
                "</tr>"
            )

    # An empty comparison means nothing was validated. Deriving PASS from
    # "zero failures" would certify a product that was never exercised, so it
    # is reported as INCONCLUSIVE rather than as a pass.
    if evidence["total"] == 0:
        overall = "INCONCLUSIVE"
    elif evidence["failed"] > 0:
        overall = "FAIL"
    elif evidence["inconclusive"] > 0:
        # Zero failures, but not every record could be confirmed. Reporting
        # PASS here would overstate what the evidence supports.
        overall = "INCONCLUSIVE"
    else:
        overall = "PASS"

    pass_rate = float(evidence["pass_rate"])
    # Never let a rounded rate read as 100% while failures exist, and never
    # style a run containing failures as passing.
    pass_rate_display = f"{pass_rate:.2f}%"
    if evidence["failed"] > 0 and pass_rate_display == "100.00%":
        pass_rate_display = "&lt;100.00%"
    if evidence["total"] == 0:
        pass_rate_class = "status-fail"
    elif evidence["inconclusive"] > 0:
        # Green is reserved for a run where every record was confirmed.
        pass_rate_class = "status-warning"
    elif evidence["failed"] == 0:
        pass_rate_class = "status-pass"
    elif pass_rate >= 95.0:
        pass_rate_class = "status-warning"
    else:
        pass_rate_class = "status-fail"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nol8 Validation Report — {escape(_text(manifest.get('run_id')))}</title>
<style>
:root {{ color-scheme: light; --ink:#17202a; --muted:#59636e; --line:#d8dee4; --ok:#176b3a; --ok-bg:#e7f5ec; --bad:#a12622; --bad-bg:#fbe9e7; --warning:#8a5a00; --warning-bg:#fff4ce; --panel:#f6f8fa; }}
body {{ font: 15px/1.5 system-ui, sans-serif; color:var(--ink); max-width:1100px; margin:0 auto; padding:32px; }}
h1,h2,h3 {{ line-height:1.2; }} h2 {{ margin-top:36px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
.status {{ display:inline-block; padding:5px 10px; border-radius:4px; color:white; background:{'var(--ok)' if overall == 'PASS' else 'var(--warning)' if overall == 'INCONCLUSIVE' else 'var(--bad)'}; font-weight:700; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
.metric {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:14px; }} .metric strong {{ display:block; font-size:24px; }}
.metric-passed, .status-pass {{ color:var(--ok); background:var(--ok-bg); border-color:var(--ok); }}
.metric-failed, .status-fail {{ color:var(--bad); background:var(--bad-bg); border-color:var(--bad); }}
.status-warning {{ color:var(--warning); background:var(--warning-bg); border-color:var(--warning); }}
table {{ border-collapse:collapse; width:100%; margin:10px 0 20px; }} th,td {{ border:1px solid var(--line); padding:7px 9px; text-align:left; vertical-align:top; }} th {{ background:var(--panel); }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:var(--panel); padding:12px; border:1px solid var(--line); }} code {{ overflow-wrap:anywhere; }}
.signature {{ margin:24px 0; }} .signature > h3 {{ margin-bottom:4px; }}
.failure {{ border-left:4px solid var(--bad); padding:1px 16px; margin:16px 0; }} .muted {{ color:var(--muted); }}
.diff {{ margin:8px 0; }} .diff pre {{ margin:0; border-radius:0; }}
.diff-common {{ border-bottom:none; color:var(--muted); }}
.diff-expected {{ background:var(--ok-bg); border-color:var(--ok); border-bottom:none; }}
.diff-actual {{ background:var(--bad-bg); border-color:var(--bad); }}
.diff-label {{ display:inline-block; min-width:72px; font-weight:700; text-transform:uppercase; font-size:11px; letter-spacing:.04em; color:var(--muted); user-select:none; }}
@media print {{ body {{ max-width:none; padding:0; }} details {{ display:block; }} }}
</style>
</head>
<body>
<header><h1>Nol8 Validation Report</h1><p><span class="status">{overall}</span></p></header>
<h2>Run identity</h2>
{_table((("Run ID", manifest.get("run_id")), ("Run type", manifest.get("run_type")), ("Workload", workload_name), ("Configuration snapshot", configuration.get("snapshot") if isinstance(configuration, Mapping) else None), ("Created at", manifest.get("created_at")), ("Updated at", manifest.get("updated_at")), ("Deployment target", policy.get("target")), ("Replacement maximum length", comparison.get("replacement_max_length"))))}
<h2>Validation outcome</h2>
<div class="grid"><div class="metric"><strong>{evidence['total']}</strong>Evaluated</div><div class="metric metric-passed"><strong>{evidence['passed']}</strong>Passed</div><div class="metric metric-failed"><strong>{evidence['failed']}</strong>Failed</div>{f'<div class="metric status-warning"><strong>{evidence["inconclusive"]}</strong>Inconclusive</div>' if evidence['inconclusive'] else ''}<div class="metric {pass_rate_class}"><strong>{pass_rate_display}</strong>Pass rate</div></div>
{'<p class="status-warning" style="padding:10px;border:1px solid var(--warning);border-radius:4px;">No records were evaluated. This report does not establish that the product was validated.</p>' if evidence['total'] == 0 else ''}
{_inconclusive_note(evidence, comparison)}
{_distribution_table("Outcome breakdown", evidence["outcomes"])}
{_distribution_table("Record kinds", evidence["kinds"])}
<h2>Workload composition</h2>
{_table((("Seed", generation.get("seed")), ("Requested records", requested_records), ("Realized records", realized_records), ("Requested rules", requested_rules), ("Realized rules", realized_rules), ("Clean records", generation.get("clean_record_count")), ("Dirty records", generation.get("dirty_record_count")), ("Expected replacements", evidence["expected_replacements"]), ("Payload bytes average", generation.get("payload_bytes_average")), ("Padding bytes", generation.get("padding_bytes_total"))))}
{_distribution_table("Scenarios", generation.get("scenario_distribution", {}))}
{_distribution_table("Formats", generation.get("format_distribution", {}))}
{_distribution_table("Match profiles", generation.get("match_profile_distribution", {}))}
{_distribution_table("Size profiles", generation.get("size_profile_distribution", {}))}
<h2>Policy deployment</h2>
{_table((("Status", policy.get("status")), ("Policy path", policy.get("policy_path")), ("Policy SHA-256", policy.get("policy_sha256")), ("HTTP status", policy.get("http_status")), ("Command ID", policy_response.get("command_id")), ("Stage", policy_response.get("stage")), ("Message", policy_response.get("message")), ("Rules", policy_response.get("rules"))))}
<h2>Execution</h2>
{_table((("Status", run.get("status")), ("Requests total", run.get("requests_total")), ("Requests completed", run.get("requests_completed")), ("Requests failed", run.get("requests_failed")), ("Harness runtime", f"{runtime_seconds:.3f} seconds"), ("Harness throughput", f"{harness_throughput:.2f} req/sec")))}
<h3>Service latency from request evidence</h3>
{_table(tuple((name, f"{value:.3f} ms") for name, value in evidence["latency"].items()))}
<p class="muted">End-to-end throughput includes validation harness overhead. Latency reflects observed request processing time.</p>
<h2>Data Path Profile</h2>
<h3>Architecture</h3>
{_table((("Processing path", "Nol8 FPGA-accelerated data path"),))}
<h3>Workload</h3>
{_table((("Records evaluated", evidence["total"]), ("Rules deployed", rules_deployed), ("Expected transformations", evidence["expected_replacements"]), ("Input payload size", input_payload_size)))}
<h3>Observed</h3>
{_table((("Harness throughput", f"{harness_throughput:.2f} req/sec"), ("Service latency p50", f"{evidence['latency']['p50']:.3f} ms"), ("Service latency p95", f"{evidence['latency']['p95']:.3f} ms"), ("Service latency p99", f"{evidence['latency']['p99']:.3f} ms")))}
<p class="muted">Measured latency reflects observed request processing. Architecture context describes the execution path and does not represent a benchmark comparison.</p>
<h2>Transformation evidence</h2>
{_distribution_table("Expected matches by category", evidence["categories"])}
{_distribution_table("Expected matches by case", evidence["cases"])}
<h2>Failure details</h2>
{render_failure_section(evidence["failures"])}
<h2>Artifact provenance</h2>
<table><thead><tr><th>Artifact</th><th>Path</th><th>SHA-256</th><th>Bytes</th></tr></thead><tbody>{''.join(artifact_rows)}</tbody></table>
<p class="muted">Generated from durable Run artifacts. Validation stages were not rerun.</p>
</body></html>
"""
    return html
