"""
Eval runner for dv-datamanagement skill.

Sends each scenario prompt to Claude Opus 4.6, Claude Sonnet 4.5, and GPT-4o,
then writes raw responses to results/ for the grader to score.

Usage:
    python evals/runner.py                        # run all scenarios, all models
    python evals/runner.py --category bulk_delete # one category only
    python evals/runner.py --models opus sonnet   # skip GPT-4o
    python evals/runner.py --approach pac_cli     # only pac_cli scenarios
    python evals/runner.py --approach sdk         # only sdk scenarios

Environment variables required:
    ANTHROPIC_API_KEY   — for Claude models
    OPENAI_API_KEY      — for GPT-4o (optional, skip if not set)

The SKILL.md is injected as a system prompt so the model has the same context
a user would have when running the plugin.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import yaml

EVALS_DIR = Path(__file__).parent
SCENARIOS_DIR = EVALS_DIR / "scenarios"
RESULTS_DIR = EVALS_DIR / "results"
SKILL_MD = Path(__file__).parent.parent / ".github/plugins/dataverse/skills/dv-datamanagement/SKILL.md"

MODELS = {
    "opus":   "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5-20251001",
    "gpt4o":  "gpt-4o",
}

SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant helping with Microsoft Dataverse administration.
Follow the skill instructions below exactly when responding to user requests.

--- SKILL INSTRUCTIONS ---
{skill_content}
--- END SKILL INSTRUCTIONS ---

When asked to perform a data management operation:
1. Show the exact command(s) or Python code you would run
2. Explain any required arguments
3. Note any safety considerations or confirmations needed
4. If choosing between PAC CLI and Python SDK, explain why you chose that approach
"""


def load_scenarios(category: str = None, approach: str = None, deduplicate: bool = False) -> list[dict]:
    scenarios = []
    for f in sorted(SCENARIOS_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        for s in data.get("scenarios", []):
            if category and s.get("category") != category:
                continue
            if approach and s.get("expected_approach") != approach:
                continue
            scenarios.append(s)
    if deduplicate:
        # Keep one scenario per unique (category, prompt) pair — prefer pac_cli id (shorter)
        seen = {}
        for s in scenarios:
            key = (s["category"], s["prompt"])
            if key not in seen or len(s["id"]) < len(seen[key]["id"]):
                seen[key] = s
        scenarios = sorted(seen.values(), key=lambda s: s["id"])
    return scenarios


def load_skill_md() -> str:
    if SKILL_MD.exists():
        return SKILL_MD.read_text(encoding="utf-8")
    return "(skill.md not found — running without skill context)"


def call_claude(model_id: str, system: str, prompt: str, retries: int = 3) -> dict:
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed. Run: pip install anthropic"}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(retries):
        start = time.time()
        try:
            msg = client.messages.create(
                model=model_id,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed = time.time() - start
            return {
                "text": msg.content[0].text,
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "latency_s": round(elapsed, 2),
            }
        except Exception as e:
            err = str(e)
            if "rate_limit" in err and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"    rate limit hit, waiting {wait}s (attempt {attempt+1}/{retries})...")
                time.sleep(wait)
            else:
                return {"error": err}

    return {"error": f"failed after {retries} attempts"}


def call_gpt4o(system: str, prompt: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package not installed. Run: pip install openai"}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set — skipping GPT-4o"}

    client = OpenAI(api_key=api_key)
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        elapsed = time.time() - start
        return {
            "text": resp.choices[0].message.content,
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
            "latency_s": round(elapsed, 2),
        }
    except Exception as e:
        return {"error": str(e)}


def run_scenario(scenario: dict, model_key: str, system: str, force_approach: str = None) -> dict:
    prompt = scenario["prompt"]
    model_id = MODELS[model_key]

    # When force_approach is set, prepend an instruction to the prompt
    if force_approach == "pac_cli":
        prompt = f"Use PAC CLI commands (not Python SDK or Web API) to accomplish this.\n\n{prompt}"
    elif force_approach == "sdk":
        prompt = f"Use Python SDK with Web API calls (not PAC CLI commands) to accomplish this.\n\n{prompt}"

    effective_approach = force_approach or scenario.get("expected_approach")
    tag = f"[{model_key}:{force_approach or 'auto'}]"
    print(f"  {tag} {scenario['id']}: {scenario['prompt'][:55]}...")

    if model_key in ("opus", "sonnet", "haiku"):
        result = call_claude(model_id, system, prompt)
    else:
        result = call_gpt4o(system, prompt)

    return {
        "scenario_id": scenario["id"],
        "category": scenario["category"],
        "prompt": scenario["prompt"],  # store original prompt
        "forced_approach": force_approach,
        "model_key": model_key,
        "model_id": model_id,
        "expected_approach": effective_approach,
        "response": result,
    }


def main():
    parser = argparse.ArgumentParser(description="Run dv-datamanagement evals")
    parser.add_argument("--category", help="Filter by category (bulk_delete, retention, org_settings, sample_data)")
    parser.add_argument("--models", nargs="+", choices=list(MODELS.keys()), default=list(MODELS.keys()),
                        help="Models to test (default: all)")
    parser.add_argument("--approach", choices=["pac_cli", "sdk"], help="Filter by expected approach")
    parser.add_argument("--force-approach", choices=["pac_cli", "sdk", "both"],
                        help="Force approach in prompt: pac_cli, sdk, or both (runs every scenario twice)")
    parser.add_argument("--dry-run", action="store_true", help="Print scenarios without calling APIs")
    args = parser.parse_args()

    skill_content = load_skill_md()
    system = SYSTEM_PROMPT_TEMPLATE.format(skill_content=skill_content)
    deduplicate = args.force_approach == "both"
    scenarios = load_scenarios(category=args.category, approach=args.approach, deduplicate=deduplicate)

    if not scenarios:
        print("No scenarios matched filters.")
        sys.exit(1)

    # Determine which forced approaches to run
    if args.force_approach == "both":
        force_list = ["pac_cli", "sdk"]
    elif args.force_approach:
        force_list = [args.force_approach]
    else:
        force_list = [None]  # no forcing — use scenario's expected_approach

    total_runs = len(scenarios) * len(args.models) * len(force_list)
    print(f"Running {len(scenarios)} scenarios x {len(args.models)} model(s) x {len(force_list)} approach(es) = {total_runs} total")

    if args.dry_run:
        for s in scenarios:
            for fa in force_list:
                tag = fa or s.get('expected_approach', '?')
                print(f"  {s['id']} ({s['category']}, {tag}): {s['prompt']}")
        return

    RESULTS_DIR.mkdir(exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    all_results = []

    for scenario in scenarios:
        for force_approach in force_list:
            for model_key in args.models:
                result = run_scenario(scenario, model_key, system, force_approach=force_approach)
                all_results.append(result)
                time.sleep(2)  # avoid rate limits

    output_file = RESULTS_DIR / f"run_{run_id}.json"
    output_file.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {output_file}")
    print(f"Next: python evals/grader.py {output_file}")


if __name__ == "__main__":
    main()
