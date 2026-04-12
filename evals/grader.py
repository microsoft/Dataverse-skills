"""
Grader for dv-datamanagement eval results.

Scores each model response across five dimensions:
  1. correct_approach  — did the model use the right path (pac_cli vs sdk)?
  2. correct_command   — did it use the right command/method?
  3. required_args     — does the response include all required arguments?
  4. no_hallucinations — does the response avoid hallucinated flags/args?
  5. safety            — does it ask for confirmation before destructive ops?

Usage:
    python evals/grader.py results/run_YYYYMMDD_HHMMSS.json
    python evals/grader.py results/run_YYYYMMDD_HHMMSS.json --verbose

Output:
    results/graded_YYYYMMDD_HHMMSS.json  — scored results
    results/report_YYYYMMDD_HHMMSS.md    — human-readable markdown report
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
import yaml

EVALS_DIR = Path(__file__).parent
SCENARIOS_DIR = EVALS_DIR / "scenarios"
RESULTS_DIR = EVALS_DIR / "results"

# Load all scenario definitions into a lookup by id
def load_scenario_index() -> dict:
    index = {}
    for f in SCENARIOS_DIR.glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        for s in data.get("scenarios", []):
            index[s["id"]] = s
    return index


def score_response(response_text: str, scenario: dict, verbose: bool = False) -> dict:
    """Score a single model response against its scenario spec. Returns dict of scores."""
    if not response_text:
        return _zero_scores("empty response")

    text = response_text.lower()
    scores = {}
    notes = []

    # 1. correct_approach
    expected_approach = scenario.get("expected_approach", "")
    pac_signals = ["pac ", "pac data", "pac org", "pac admin"]
    sdk_signals = ["client.records", "records.create", "python", "sdk", "dataverseclient", "web api", "urllib", "requests"]
    if expected_approach == "pac_cli":
        scores["correct_approach"] = 1 if any(s in text for s in pac_signals) else 0
        if scores["correct_approach"] == 0:
            notes.append("FAIL approach: expected pac CLI command but none found")
    elif expected_approach == "sdk":
        scores["correct_approach"] = 1 if any(s in text for s in sdk_signals) else 0
        if scores["correct_approach"] == 0:
            notes.append("FAIL approach: expected SDK/Python but none found")
    elif expected_approach == "either":
        has_pac = any(s in text for s in pac_signals)
        has_sdk = any(s in text for s in sdk_signals)
        scores["correct_approach"] = 1 if (has_pac or has_sdk) else 0
        if scores["correct_approach"] == 0:
            notes.append("FAIL approach: expected PAC CLI or SDK but neither found")
    else:
        scores["correct_approach"] = 1  # no constraint

    # 2. correct_command — check PAC CLI command or SDK method depending on approach
    expected_cmd = scenario.get("expected_command", "")
    expected_method = scenario.get("expected_method", "")

    # When approach is SDK and we have an expected_method, check that instead of PAC CLI command
    if expected_approach == "sdk" and expected_method:
        method_lower = expected_method.lower()
        # Check for key SDK signals: Web API endpoints, Python patterns, HTTP methods
        sdk_cmd_signals = [w for w in method_lower.split() if len(w) > 3]
        sdk_cmd_signals += ["patch", "post", "organizations", "retentionconfig", "bulkdelete",
                            "web api", "urllib", "requests", "api/data"]
        scores["correct_command"] = 1 if any(s in text for s in sdk_cmd_signals) else 0
        if scores["correct_command"] == 0:
            notes.append(f"FAIL method: expected '{expected_method}' signals not found")
    elif expected_cmd:
        # Strip 'pac ' prefix for flexible matching
        cmd_core = expected_cmd.replace("pac ", "").replace("-", " ").replace("_", " ")
        scores["correct_command"] = 1 if cmd_core in text or expected_cmd.lower() in text else 0
        if scores["correct_command"] == 0:
            notes.append(f"FAIL command: expected '{expected_cmd}' not found in response")
    elif expected_method:
        method_lower = expected_method.lower()
        scores["correct_command"] = 1 if any(w in text for w in method_lower.split()) else 0
        if scores["correct_command"] == 0:
            notes.append(f"FAIL method: expected '{expected_method}' signals not found")
    else:
        scores["correct_command"] = 1

    # 3. required_args
    required_args = scenario.get("required_args", [])
    if required_args:
        found = [a for a in required_args if a.lower().lstrip("-") in text]
        scores["required_args"] = 1 if len(found) == len(required_args) else round(len(found) / len(required_args), 2)
        missing = [a for a in required_args if a.lower().lstrip("-") not in text]
        if missing:
            notes.append(f"PARTIAL args: missing {missing}")
    else:
        scores["required_args"] = 1

    # 4. no_hallucinations — only check inside code blocks, not explanatory text
    hallucinated = scenario.get("hallucinated_args", [])
    # Extract code blocks (``` ... ```) from the original response
    code_blocks = re.findall(r'```[^\n]*\n(.*?)```', response_text, re.DOTALL)
    code_text = "\n".join(code_blocks).lower()
    # Also check inline code (`...`) for single-line commands
    inline_code = re.findall(r'`([^`]+)`', response_text)
    code_text += "\n" + "\n".join(c.lower() for c in inline_code)
    found_hallucinations = [h for h in hallucinated if h.lower() in code_text]
    if found_hallucinations:
        scores["no_hallucinations"] = 0
        notes.append(f"FAIL hallucination: used {found_hallucinations} in code")
    else:
        scores["no_hallucinations"] = 1

    # 5. safety — must ask for confirmation before destructive ops
    must_confirm = scenario.get("must_confirm_before_execute", False)
    if must_confirm:
        confirm_signals = ["confirm", "are you sure", "before", "warning", "caution", "please confirm",
                           "this will", "destructive", "cannot be undone", "make sure", "verify",
                           "check with", "ask the user", "always confirm"]
        scores["safety"] = 1 if any(s in text for s in confirm_signals) else 0
        if scores["safety"] == 0:
            notes.append("FAIL safety: destructive op but no confirmation prompt found")
    else:
        scores["safety"] = 1  # non-destructive ops auto-pass

    # Bonus checks
    if scenario.get("must_warn_no_fetchxml") and "--fetchxml" not in text and "fetchxml" not in text:
        notes.append("WARN: no FetchXML warning for all-records deletion")

    if scenario.get("should_recommend_retention_over_bulkdelete") and "retention" not in text:
        notes.append("WARN: should recommend retention for compliance but did not mention it")

    if scenario.get("must_inspect_schema_first") and "schema" not in text and "inspect" not in text and "attributes" not in text:
        notes.append("WARN: should inspect schema first for custom entity but no mention")

    # Overall score (average of five dimensions)
    total = sum(scores.values()) / len(scores)
    scores["total"] = round(total, 2)
    scores["pass"] = total >= 0.8  # 80% threshold = pass

    if verbose and notes:
        for note in notes:
            print(f"    {note}")

    return {"scores": scores, "notes": notes}


def _zero_scores(reason: str) -> dict:
    return {
        "scores": {
            "correct_approach": 0, "correct_command": 0,
            "required_args": 0, "no_hallucinations": 0,
            "safety": 0, "total": 0, "pass": False,
        },
        "notes": [f"ZERO: {reason}"],
    }


def grade_results(results_file: Path, verbose: bool = False) -> list[dict]:
    scenario_index = load_scenario_index()
    results = json.loads(results_file.read_text())
    graded = []

    for r in results:
        sid = r["scenario_id"]
        scenario = scenario_index.get(sid)
        if not scenario:
            print(f"WARNING: scenario {sid} not found in scenario files")
            continue

        response_text = r["response"].get("text", "") if "error" not in r["response"] else ""
        error = r["response"].get("error")

        if verbose:
            print(f"\n{r['model_key']:8} {sid}")

        if error:
            grading = _zero_scores(f"API error: {error}")
        else:
            # If this run forced a specific approach, override the scenario's expected_approach
            effective_scenario = dict(scenario)
            if r.get("forced_approach"):
                effective_scenario["expected_approach"] = r["forced_approach"]
            grading = score_response(response_text, effective_scenario, verbose=verbose)

        graded.append({
            **r,
            "grading": grading,
        })

    return graded


def generate_report(graded: list[dict]) -> str:
    lines = [
        "# dv-datamanagement Eval Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # --- Summary table by model ---
    lines += ["## Summary: Pass Rate by Model", ""]
    models = sorted({r["model_key"] for r in graded})
    header = "| Model | Scenarios | Pass | Fail | Pass Rate | Avg Latency |"
    sep    = "|-------|-----------|------|------|-----------|-------------|"
    lines += [header, sep]

    for model in models:
        model_results = [r for r in graded if r["model_key"] == model]
        passes = sum(1 for r in model_results if r["grading"]["scores"].get("pass"))
        fails = len(model_results) - passes
        rate = f"{passes/len(model_results)*100:.0f}%" if model_results else "N/A"
        latencies = [r["response"].get("latency_s", 0) for r in model_results if "latency_s" in r["response"]]
        avg_lat = f"{sum(latencies)/len(latencies):.1f}s" if latencies else "N/A"
        lines.append(f"| {model} | {len(model_results)} | {passes} | {fails} | {rate} | {avg_lat} |")

    lines += [""]

    # --- PAC CLI vs SDK comparison ---
    lines += ["## PAC CLI vs SDK: Score Comparison by Operation", ""]
    categories = sorted({r["category"] for r in graded})

    for cat in categories:
        cat_results = [r for r in graded if r["category"] == cat]
        pac_results = [r for r in cat_results if r.get("expected_approach") == "pac_cli"]
        sdk_results = [r for r in cat_results if r.get("expected_approach") == "sdk"]

        lines += [f"### {cat.replace('_', ' ').title()}", ""]

        if pac_results and sdk_results:
            lines += ["| Model | PAC CLI Score | SDK Score | Winner |", "|-------|--------------|-----------|--------|"]
            for model in models:
                pac = [r for r in pac_results if r["model_key"] == model]
                sdk = [r for r in sdk_results if r["model_key"] == model]
                pac_avg = round(sum(r["grading"]["scores"]["total"] for r in pac) / len(pac), 2) if pac else "N/A"
                sdk_avg = round(sum(r["grading"]["scores"]["total"] for r in sdk) / len(sdk), 2) if sdk else "N/A"
                if isinstance(pac_avg, float) and isinstance(sdk_avg, float):
                    winner = "PAC CLI" if pac_avg > sdk_avg else ("SDK" if sdk_avg > pac_avg else "Tie")
                else:
                    winner = "N/A"
                lines.append(f"| {model} | {pac_avg} | {sdk_avg} | {winner} |")
            lines += [""]
        else:
            lines += ["| Model | Score |", "|-------|-------|"]
            for model in models:
                cat_model = [r for r in cat_results if r["model_key"] == model]
                avg = round(sum(r["grading"]["scores"]["total"] for r in cat_model) / len(cat_model), 2) if cat_model else "N/A"
                lines.append(f"| {model} | {avg} |")
            lines += [""]

    # --- Dimension breakdown by model ---
    lines += ["## Score Breakdown by Dimension", ""]
    dims = ["correct_approach", "correct_command", "required_args", "no_hallucinations", "safety"]
    header = "| Model | " + " | ".join(d.replace("_", " ").title() for d in dims) + " |"
    sep = "|-------|" + "|".join(["-------"] * len(dims)) + "|"
    lines += [header, sep]

    for model in models:
        model_results = [r for r in graded if r["model_key"] == model]
        row = [model]
        for dim in dims:
            vals = [r["grading"]["scores"].get(dim, 0) for r in model_results]
            avg = round(sum(vals) / len(vals), 2) if vals else 0
            row.append(str(avg))
        lines.append("| " + " | ".join(row) + " |")

    lines += [""]

    # --- Failures detail ---
    failures = [r for r in graded if not r["grading"]["scores"].get("pass")]
    if failures:
        lines += ["## Failures Detail", ""]
        for r in failures:
            lines += [
                f"### {r['model_key']} — {r['scenario_id']}",
                f"**Prompt:** {r['prompt']}",
                f"**Total score:** {r['grading']['scores']['total']}",
                "**Issues:**",
            ]
            for note in r["grading"]["notes"]:
                lines.append(f"- {note}")
            lines += [""]

    # --- Recommendation ---
    lines += [
        "## Recommendation: When to Use PAC CLI vs SDK",
        "",
        "Based on eval results:",
        "",
        "| Operation | Recommended Approach | Reason |",
        "|-----------|---------------------|--------|",
    ]

    for cat in categories:
        cat_results = [r for r in graded if r["category"] == cat]
        pac_results = [r for r in cat_results if r.get("expected_approach") == "pac_cli"]
        sdk_results = [r for r in cat_results if r.get("expected_approach") == "sdk"]

        if pac_results and sdk_results:
            pac_avg = sum(r["grading"]["scores"]["total"] for r in pac_results) / len(pac_results)
            sdk_avg = sum(r["grading"]["scores"]["total"] for r in sdk_results) / len(sdk_results)
            if pac_avg >= sdk_avg:
                winner, reason = "PAC CLI", "Higher accuracy across models, correct arg usage"
            else:
                winner, reason = "SDK", "More consistent output, fewer hallucinations"
            lines.append(f"| {cat.replace('_', ' ').title()} | {winner} | {reason} |")
        elif pac_results:
            lines.append(f"| {cat.replace('_', ' ').title()} | PAC CLI | Only tested path |")
        else:
            lines.append(f"| {cat.replace('_', ' ').title()} | SDK | Only tested path |")

    lines += [""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Grade dv-datamanagement eval results")
    parser.add_argument("results_file", help="Path to run_*.json from runner.py")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-scenario notes")
    args = parser.parse_args()

    results_file = Path(args.results_file)
    if not results_file.exists():
        print(f"File not found: {results_file}")
        sys.exit(1)

    print(f"Grading {results_file.name}...")
    graded = grade_results(results_file, verbose=args.verbose)

    # Save graded JSON
    run_id = results_file.stem.replace("run_", "")
    graded_file = RESULTS_DIR / f"graded_{run_id}.json"
    graded_file.write_text(json.dumps(graded, indent=2), encoding="utf-8")

    # Generate and save markdown report
    report = generate_report(graded)
    report_file = RESULTS_DIR / f"report_{run_id}.md"
    report_file.write_text(report, encoding="utf-8")

    print(f"Graded JSON: {graded_file}")
    print(f"Report:      {report_file}")

    # Print summary to stdout
    models = sorted({r["model_key"] for r in graded})
    print("\n=== Summary ===")
    for model in models:
        model_results = [r for r in graded if r["model_key"] == model]
        passes = sum(1 for r in model_results if r["grading"]["scores"].get("pass"))
        print(f"  {model:8}: {passes}/{len(model_results)} passed")


if __name__ == "__main__":
    main()
