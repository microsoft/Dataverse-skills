"""
Static eval suite for Dataverse plugin skill files.

Checks every SKILL.md for code correctness, auth pattern compliance,
cross-skill completeness, and PAC CLI accuracy. Runs with no external
dependencies (stdlib only).

Usage:
    python .github/evals/static_checks.py
    python .github/evals/static_checks.py --skills-dir path/to/skills

Exit code 0 = all checks passed. Exit code 1 = one or more failures.

--- Eval Categories ---

CAT-1  Python Code Block Validity
       Checks that every python-fenced block is runnable as written.
       EVAL-PY-01  sys.path.insert present and ordered before 'from auth import'
       EVAL-PY-04  No all-comment stub blocks
       EVAL-PY-05  get_token() not used in DataverseClient blocks
       EVAL-PY-06  load_env() called before os.environ access

CAT-2  Auth Pattern Compliance
       Checks that auth imports follow the documented pattern.
       EVAL-AUTH-01  No 'from scripts.auth import' pattern
       EVAL-AUTH-02  Every get_token/urllib block must justify why SDK is not used

CAT-3  PAC CLI Accuracy
       Checks for known-bad PAC CLI invocations.
       EVAL-PAC-02  No 'pac --version' invocations

CAT-4  Skill Structure & Discoverability
       Checks that every skill has the structural elements agents need to
       discover and route to it correctly. Anchored to Anthropic's Skills
       authoring guidance: description is a single descriptive sentence with
       an inline 'Use when ...' clause, third-person, max 1024 chars.
       EVAL-STRUCT-01  Frontmatter has required 'name' and 'description' fields
       EVAL-STRUCT-02  Frontmatter 'name' matches the skill directory name
       EVAL-STRUCT-03  Description contains a 'Use when' routing hint
       EVAL-STRUCT-04  Description is <= 1024 chars (Anthropic spec hard limit)
       EVAL-STRUCT-05  Frontmatter parses as valid YAML (catches unquoted colons,
                       malformed mappings, and other syntax errors that break the
                       skill manifest on GitHub and at plugin-load time)

CAT-5  Cross-Skill Completeness
       Checks that skills reference each other correctly and that the
       overview index stays in sync with the actual skill set.
       EVAL-COMPLETE-01  Skill Boundaries section present in every non-exempt skill
       EVAL-COMPLETE-02  Skill Boundaries cross-references point to real skill names
       EVAL-COMPLETE-03  dv-overview Available Skills table lists every skill directory
       EVAL-COMPLETE-04  No skill references the removed 'dv-python-sdk' skill
       EVAL-COMPLETE-05  README.md skill count matches actual number of skill directories

CAT-6  dv-admin Allowlist Enforcement
       Checks that the settings allowlist in dv-admin keeps its refusal semantics
       and covers every backend key it claims to cover. Regression guard against
       silent allowlist drift (keys disappearing, denylist becoming vague, or
       the refusal directive being softened).
       EVAL-ALLOW-01  dv-admin has an 'Allowed settings' heading
       EVAL-ALLOW-02  Allowlist text contains the refusal directive ('must be refused')
       EVAL-ALLOW-03  Known out-of-scope settings are named as explicit denylist examples
       EVAL-ALLOW-04  Every expected allowlisted backend key is present in dv-admin
       
CAT-7  Manifest Version Consistency
       Checks that the plugin version matches across all marketplace and plugin
       manifest files, preventing drift when version bumps miss a file.
       EVAL-VERSION-01  All four version fields match (3 files, 4 fields total)
       EVAL-VERSION-02  Version format is valid semver (x.y.z)

CAT-8  Skill Token Budget (Anthropic Skills spec)
       Anthropic's published skills loading model — Level 1 (frontmatter, always
       loaded across every interaction) ~100 tokens; Level 2 (body, loaded on
       trigger) <5k tokens; Level 3 (`references/`, loaded on demand) unlimited.
       EVAL-BUDGET-01  Frontmatter <= 200 tokens (Level 1, with headroom)
       EVAL-BUDGET-02  Body       <= 5,000 tokens (Level 2 cap)
       EVAL-BUDGET-03  Skills with body > 4,000 tokens must have a `references/`
                       subfolder (forces Level 3 split before Level 2 fills up)
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tiktoken
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _ENCODER = None

try:
    import yaml
    _YAML = yaml
except ImportError:
    _YAML = None


def count_tokens(text):
    """Token count using the cl100k_base encoder (matches Claude's input units).
    Falls back to a 4-chars-per-token approximation if tiktoken is unavailable."""
    if _ENCODER is not None:
        return len(_ENCODER.encode(text))
    return max(1, len(text) // 4)

# Skills that intentionally have no Skill Boundaries table.
NO_BOUNDARIES_EXEMPT = {"dv-overview", "dv-connect"}

# Skills exempt from CAT-8.3 (the references/ split nudge): orchestration / index
# skills are loaded as one routing surface and don't have a natural "long workflow"
# to extract. Hard cap (CAT-8.2) still applies.
NO_REFERENCES_NUDGE_EXEMPT = {"dv-overview"}

# Anthropic's Skills spec hard limit on the description field (per docs.claude.com).
DESCRIPTION_CHAR_LIMIT = 1024


def extract_fenced_blocks(text, lang="python"):
    """Return list of (index, content) for fenced blocks of the given language."""
    pattern = rf"```{re.escape(lang)}[^\n]*\n(.*?)```" if lang else r"```\w*[^\n]*\n(.*?)```"
    return list(enumerate(re.findall(pattern, text, re.DOTALL), start=1))


def parse_frontmatter(text):
    """Return the YAML frontmatter block as a raw string, or None if absent."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# CAT-1  Python Code Block Validity
# ---------------------------------------------------------------------------

def check_python_blocks(name, text):
    failures = []
    python_blocks = extract_fenced_blocks(text, "python")

    for i, block in python_blocks:
        label = f"{name} python-block-{i}"

        # EVAL-PY-01: sys.path.insert must precede 'from auth import'
        if "from auth import" in block:
            lines = block.splitlines()
            auth_idx = next((j for j, l in enumerate(lines) if "from auth import" in l), None)
            path_idx = next((j for j, l in enumerate(lines) if "sys.path.insert" in l), None)
            if path_idx is None:
                failures.append(
                    f"EVAL-PY-01 [{label}] 'from auth import' present but no sys.path.insert"
                )
            elif path_idx > auth_idx:
                failures.append(
                    f"EVAL-PY-01 [{label}] sys.path.insert appears after 'from auth import'"
                )

        # EVAL-PY-04: no all-comment stub blocks
        non_blank = [l for l in block.splitlines() if l.strip()]
        if non_blank and all(l.strip().startswith("#") for l in non_blank):
            failures.append(
                f"EVAL-PY-04 [{label}] block is all comments -- "
                f"replace stub with runnable code or remove the python fence"
            )

        # EVAL-PY-05: get_token() must not appear in SDK blocks
        if "DataverseClient(" in block and "get_token" in block:
            failures.append(
                f"EVAL-PY-05 [{label}] get_token() used in block containing DataverseClient() -- "
                f"use get_credential() for SDK operations"
            )

        # EVAL-PY-06: load_env() must precede os.environ access (except notebook blocks)
        if "os.environ[" in block and "load_env" not in block:
            if "InteractiveBrowserCredential" not in block:
                failures.append(
                    f"EVAL-PY-06 [{label}] os.environ accessed without calling load_env() first"
                )

    return failures


# ---------------------------------------------------------------------------
# CAT-2  Auth Pattern Compliance
# ---------------------------------------------------------------------------

def check_auth_patterns(name, text):
    failures = []
    python_blocks = extract_fenced_blocks(text, "python")

    for i, block in python_blocks:
        label = f"{name} python-block-{i}"

        # EVAL-AUTH-01: no 'from scripts.auth import'
        if "from scripts.auth import" in block:
            failures.append(
                f"EVAL-AUTH-01 [{label}] 'from scripts.auth import' is wrong -- "
                f"use sys.path.insert + 'from auth import'"
            )

        # EVAL-AUTH-02: get_token/urllib blocks must justify why SDK cannot be used
        uses_raw_http = ("get_token" in block or "urllib.request" in block)
        if uses_raw_http:
            has_justification = any(
                marker in block
                for marker in [
                    "SDK cannot",
                    "SDK can't",
                    "SDK does not support",
                    "WRONG",
                ]
            )
            if not has_justification:
                failures.append(
                    f"EVAL-AUTH-02 [{label}] uses get_token/urllib without justification "
                    f"comment -- add '# SDK cannot/does not support <reason>' to the import line"
                )

    return failures


# ---------------------------------------------------------------------------
# CAT-3  PAC CLI Accuracy
# ---------------------------------------------------------------------------

def check_pac_cli(name, text):
    failures = []
    bash_blocks = (
        extract_fenced_blocks(text, "bash")
        + extract_fenced_blocks(text, "sh")
        + extract_fenced_blocks(text, "")
    )

    # EVAL-PAC-02: pac --version must not appear anywhere
    for _i, block in bash_blocks:
        if "pac --version" in block:
            failures.append(
                f"EVAL-PAC-02 [{name}] 'pac --version' found -- "
                f"use 'pac' (banner) to check installation, not 'pac --version'"
            )
            break  # one report per file is enough

    return failures


# ---------------------------------------------------------------------------
# CAT-4  Skill Structure & Discoverability
# ---------------------------------------------------------------------------

def check_structure(name, text):
    failures = []
    frontmatter = parse_frontmatter(text)

    if frontmatter is None:
        failures.append(
            f"EVAL-STRUCT-01 [{name}] no YAML frontmatter found (expected --- block at top of file)"
        )
        return failures  # remaining checks depend on frontmatter existing

    # EVAL-STRUCT-01: required frontmatter fields
    if not re.search(r"^name\s*:", frontmatter, re.MULTILINE):
        failures.append(f"EVAL-STRUCT-01 [{name}] frontmatter missing 'name' field")
    if not re.search(r"^description\s*:", frontmatter, re.MULTILINE):
        failures.append(f"EVAL-STRUCT-01 [{name}] frontmatter missing 'description' field")

    # EVAL-STRUCT-02: frontmatter 'name' matches directory name
    name_match = re.search(r"^name\s*:\s*(\S+)", frontmatter, re.MULTILINE)
    if name_match:
        declared_name = name_match.group(1).strip()
        if declared_name != name:
            failures.append(
                f"EVAL-STRUCT-02 [{name}] frontmatter name '{declared_name}' "
                f"does not match directory name '{name}'"
            )

    # EVAL-STRUCT-03: 'Use when' routing hint present in description
    desc_match = re.search(r"^description\s*:\s*(.+?)(?=^\w|\Z)", frontmatter, re.MULTILINE | re.DOTALL)
    desc = desc_match.group(1).strip() if desc_match else ""
    if "Use when" not in desc:
        failures.append(
            f"EVAL-STRUCT-03 [{name}] description missing 'Use when' routing hint "
            f"(per Anthropic's skill-authoring guidance, the description should "
            f"include both what the skill does and when to use it)"
        )

    # EVAL-STRUCT-04: description <= 1024 chars (Anthropic spec hard limit)
    if len(desc) > DESCRIPTION_CHAR_LIMIT:
        failures.append(
            f"EVAL-STRUCT-04 [{name}] description is {len(desc)} chars, "
            f"exceeds Anthropic's {DESCRIPTION_CHAR_LIMIT}-char limit"
        )

    # EVAL-STRUCT-05: frontmatter must parse as valid YAML.
    # Without this, descriptions with unquoted colons (e.g., "data model: add a
    # column") render fine to a regex-extractor but break GitHub's YAML parser
    # and any agent that loads the skill via a real YAML library.
    if _YAML is not None:
        try:
            _YAML.safe_load(frontmatter)
        except _YAML.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            loc = f" (line {mark.line + 1} col {mark.column + 1})" if mark else ""
            failures.append(
                f"EVAL-STRUCT-05 [{name}] frontmatter is not valid YAML{loc}: "
                f"{getattr(e, 'problem', str(e))} -- "
                f"common cause: an unquoted colon in the description value"
            )

    return failures


# ---------------------------------------------------------------------------
# CAT-5  Cross-Skill Completeness
# ---------------------------------------------------------------------------

def check_completeness(name, text, all_skill_names):
    failures = []

    # EVAL-COMPLETE-01: Skill Boundaries section required
    if name not in NO_BOUNDARIES_EXEMPT:
        if not re.search(r"^##\s+skill boundaries", text, re.IGNORECASE | re.MULTILINE):
            failures.append(
                f"EVAL-COMPLETE-01 [{name}] missing '## Skill boundaries' section"
            )
        else:
            # EVAL-COMPLETE-02: cross-references in Skill Boundaries point to real skill names
            boundaries_match = re.search(
                r"##\s+skill boundaries(.*?)(?=^##|\Z)", text,
                re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            if boundaries_match:
                boundaries_text = boundaries_match.group(1)
                # Find all bold references like **dv-something**
                refs = re.findall(r"\*\*(dv-[\w-]+)\*\*", boundaries_text)
                for ref in refs:
                    if ref not in all_skill_names:
                        failures.append(
                            f"EVAL-COMPLETE-02 [{name}] Skill Boundaries references "
                            f"'{ref}' which is not a known skill"
                        )

    # EVAL-COMPLETE-04: no references to removed dv-python-sdk
    if "dv-python-sdk" in text:
        failures.append(
            f"EVAL-COMPLETE-04 [{name}] references removed skill 'dv-python-sdk' -- "
            f"update to 'dv-data' or 'dv-query'"
        )

    return failures


# ---------------------------------------------------------------------------
# CAT-6  dv-admin Allowlist Enforcement
# ---------------------------------------------------------------------------

# Representative sample of allowlisted backend keys — one per mechanism.
# If any of these disappears from dv-admin, the allowlist is broken.
# Not exhaustive (would make minor formatting edits painful); picked to cover
# all 4 mechanisms (PAC CLI org column / OrgDB XML / recyclebinconfigs / settingdefinition).
_ALLOWLIST_REQUIRED_KEYS = [
    # PAC CLI org columns (existing + new from 1.4.0)
    "plugintracelogsetting",
    "auditretentionperiodv2",
    "enablecanvasappsinsolutionsbydefault",
    "lookupresolvedelayms",
    # OrgDB XML keys (existing + new)
    "IsMCPEnabled",
    "SearchAndCopilotIndexMode",
    "EnableWorkIQ",
    "EnableTDSEndpoint",
    "EnableOwnershipAcrossBusinessUnits",
    # recyclebinconfigs
    "cleanupintervalindays",
    # settingdefinition
    "PowerAppsAppLevelSecurityRolesEnabled",
    "PlanShareSecurityRolesEnabled",
]

# Known out-of-scope settings — the skill should name these explicitly as
# denylist examples so the agent has concrete "do not toggle" signal.
_ALLOWLIST_REQUIRED_DENYLIST_EXAMPLES = [
    "sessiontimeoutinmins",   # was allowlisted pre-1.2.0, removed
    "IsArchivalEnabled",      # OrgDB key close to recycle bin but out of scope
    "IsShadowLakeEnabled",    # OrgDB key, out of scope
]


def check_allowlist(name, text):
    failures = []
    if name != "dv-admin":
        return failures

    # EVAL-ALLOW-01: 'Allowed settings' heading must exist
    if not re.search(r"^##+\s+Allowed settings", text, re.MULTILINE | re.IGNORECASE):
        failures.append(
            f"EVAL-ALLOW-01 [{name}] missing 'Allowed settings' heading"
        )
        return failures  # the rest of the rules assume the section exists

    # EVAL-ALLOW-02: the section must contain the refusal directive
    # Match a reasonably-wide refusal phrase so cosmetic edits don't trip it.
    section_match = re.search(
        r"##+\s+Allowed settings.*?(?=^##+\s|\Z)",
        text, re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    section_text = section_match.group(0) if section_match else ""
    if "must be refused" not in section_text:
        failures.append(
            f"EVAL-ALLOW-02 [{name}] Allowed settings section missing 'must be refused' directive"
        )

    # EVAL-ALLOW-03: known out-of-scope settings must be named somewhere in dv-admin.
    # Use \b word boundaries so 'IsArchivalEnabled' does not spuriously match
    # 'IsArchivalEnabledExtra' or similar near-miss renames.
    for denied in _ALLOWLIST_REQUIRED_DENYLIST_EXAMPLES:
        if not re.search(rf"\b{re.escape(denied)}\b", text):
            failures.append(
                f"EVAL-ALLOW-03 [{name}] denylist example '{denied}' no longer appears — "
                f"agent loses the explicit out-of-scope signal"
            )

    # EVAL-ALLOW-04: every expected allowlisted key must be present as a whole word
    # (so a rename like 'IsMCPEnabled' -> 'IsMCPEnabledXX' is caught, not silently passed).
    for key in _ALLOWLIST_REQUIRED_KEYS:
        if not re.search(rf"\b{re.escape(key)}\b", text):
            failures.append(
                f"EVAL-ALLOW-04 [{name}] allowlisted key '{key}' no longer appears — "
                f"allowlist has drifted from the documented 37-toggle coverage"
            )

    return failures


def check_overview_index(overview_path, all_skill_names):
    """EVAL-COMPLETE-03: dv-overview Available Skills table lists every skill directory."""
    failures = []
    if not overview_path.exists():
        failures.append("EVAL-COMPLETE-03 [dv-overview] SKILL.md not found")
        return failures

    text = overview_path.read_text(encoding="utf-8")
    for skill_name in all_skill_names:
        if skill_name == "dv-overview":
            continue  # overview doesn't list itself
        if skill_name not in text:
            failures.append(
                f"EVAL-COMPLETE-03 [dv-overview] Available Skills table missing entry "
                f"for '{skill_name}'"
            )

    return failures


def check_readme_skill_count(skills_dir, all_skill_names):
    """EVAL-COMPLETE-05: README.md skill count matches actual skill directories."""
    failures = []
    readme_path = skills_dir.parent.parent.parent.parent / "README.md"
    if not readme_path.exists():
        # README is optional — skip silently if not found
        return failures

    text = readme_path.read_text(encoding="utf-8")
    actual_count = len(all_skill_names)

    # Look for "N skills" pattern in README (e.g., "**5 skills**" or "6 skills")
    matches = re.findall(r"\*{0,2}(\d+)\s+skills\*{0,2}", text)
    for m in matches:
        claimed = int(m)
        if claimed != actual_count:
            failures.append(
                f"EVAL-COMPLETE-05 [README.md] claims '{claimed} skills' but "
                f"found {actual_count} skill directories"
            )

    return failures


# ---------------------------------------------------------------------------
# CAT-6  Manifest Version Consistency
# ---------------------------------------------------------------------------

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def check_version_consistency(repo_root):
    """
    EVAL-VERSION-01: All four version fields match across manifest files.
    EVAL-VERSION-02: Version format is valid semver (x.y.z).

    The four version fields live in three files:
      1. .github/plugin/marketplace.json -- metadata.version
      2. .github/plugin/marketplace.json -- plugins[0].version
      3. .github/plugins/dataverse/.claude-plugin/plugin.json -- version
      4. .github/plugins/dataverse/.github/plugin/plugin.json -- version
    """
    failures = []

    manifests = [
        (
            ".github/plugin/marketplace.json",
            lambda d: d.get("metadata", {}).get("version"),
            "metadata.version",
        ),
        (
            ".github/plugin/marketplace.json",
            lambda d: (d.get("plugins") or [{}])[0].get("version"),
            "plugins[0].version",
        ),
        (
            ".github/plugins/dataverse/.claude-plugin/plugin.json",
            lambda d: d.get("version"),
            "version",
        ),
        (
            ".github/plugins/dataverse/.github/plugin/plugin.json",
            lambda d: d.get("version"),
            "version",
        ),
    ]

    found = []
    for rel_path, extractor, field in manifests:
        full_path = repo_root / rel_path
        if not full_path.exists():
            failures.append(
                f"EVAL-VERSION-01 [{rel_path}] manifest file not found"
            )
            continue
        try:
            data = json.loads(full_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(
                f"EVAL-VERSION-01 [{rel_path}] invalid JSON: {e}"
            )
            continue

        version = extractor(data)
        if version is None:
            failures.append(
                f"EVAL-VERSION-01 [{rel_path}] missing '{field}' field"
            )
            continue

        found.append((rel_path, field, version))

        # EVAL-VERSION-02: semver format check
        if not SEMVER_PATTERN.match(version):
            failures.append(
                f"EVAL-VERSION-02 [{rel_path}] '{field}' = '{version}' "
                f"does not match semver format x.y.z"
            )

    # EVAL-VERSION-01: all collected versions must match
    unique_versions = {v for _, _, v in found}
    if len(unique_versions) > 1:
        detail = ", ".join(
            f"{rp}:{f}={v}" for rp, f, v in found
        )
        failures.append(
            f"EVAL-VERSION-01 version mismatch across manifests -- {detail}"
        )

    return failures


# ---------------------------------------------------------------------------
# CAT-8  Skill Token Budget (Anthropic Skills spec)
# ---------------------------------------------------------------------------

FRONTMATTER_TOKEN_CAP = 200
BODY_TOKEN_CAP = 5000
BODY_TOKEN_REFERENCES_TRIGGER = 4000


def check_token_budget(name, text, skill_dir):
    """
    EVAL-BUDGET-01: frontmatter <= FRONTMATTER_TOKEN_CAP tokens (Level 1)
    EVAL-BUDGET-02: body <= BODY_TOKEN_CAP tokens (Level 2 — Anthropic spec)
    EVAL-BUDGET-03: when body > BODY_TOKEN_REFERENCES_TRIGGER tokens, a
                    `references/` subfolder must exist (forces Level 3 split)

    Anchor: Anthropic's Skills loading model — Level 1 ~100 tok / Level 2 <5k tok / Level 3 unlimited.
    """
    failures = []
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return failures  # CAT-4 already flags missing frontmatter
    frontmatter, body = m.group(1), m.group(2)

    fm_tokens = count_tokens(frontmatter)
    if fm_tokens > FRONTMATTER_TOKEN_CAP:
        failures.append(
            f"EVAL-BUDGET-01 [{name}] frontmatter is {fm_tokens} tokens, "
            f"exceeds cap of {FRONTMATTER_TOKEN_CAP} (Anthropic Level 1 — frontmatter "
            f"is loaded into context for every interaction across all skills). "
            f"Trim trigger phrases and over-long enumerations."
        )

    body_tokens = count_tokens(body)
    if body_tokens > BODY_TOKEN_CAP:
        failures.append(
            f"EVAL-BUDGET-02 [{name}] body is {body_tokens} tokens, "
            f"exceeds cap of {BODY_TOKEN_CAP} (Anthropic Level 2). "
            f"Split long content into `references/<topic>.md` files."
        )

    if body_tokens > BODY_TOKEN_REFERENCES_TRIGGER and name not in NO_REFERENCES_NUDGE_EXEMPT:
        if not (skill_dir / "references").is_dir():
            failures.append(
                f"EVAL-BUDGET-03 [{name}] body is {body_tokens} tokens "
                f"(> {BODY_TOKEN_REFERENCES_TRIGGER} tokens) but no `references/` "
                f"subfolder exists. Create `{skill_dir.name}/references/` and "
                f"move long content there before the body hits the {BODY_TOKEN_CAP}-token cap."
            )

    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Static evals for Dataverse skill files")
    parser.add_argument(
        "--skills-dir",
        default=".github/plugins/dataverse/skills",
        help="Path to the skills directory (default: .github/plugins/dataverse/skills)",
    )
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.exists():
        print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
        sys.exit(2)

    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"ERROR: no SKILL.md files found under {skills_dir}", file=sys.stderr)
        sys.exit(2)

    all_skill_names = {f.parent.name for f in skill_files}
    all_failures = []
    python_block_count = 0

    for f in skill_files:
        text = f.read_text(encoding="utf-8")
        name = f.parent.name
        python_block_count += len(re.findall(r"```python\n", text))

        all_failures.extend(check_python_blocks(name, text))
        all_failures.extend(check_auth_patterns(name, text))
        all_failures.extend(check_pac_cli(name, text))
        all_failures.extend(check_structure(name, text))
        all_failures.extend(check_completeness(name, text, all_skill_names))
        all_failures.extend(check_allowlist(name, text))
        all_failures.extend(check_token_budget(name, text, f.parent))

    # Cross-skill checks — need all files loaded
    overview_path = skills_dir / "dv-overview" / "SKILL.md"
    all_failures.extend(check_overview_index(overview_path, all_skill_names))
    all_failures.extend(check_readme_skill_count(skills_dir, all_skill_names))

    # Manifest version consistency — check across repo root
    repo_root = skills_dir.parent.parent.parent.parent
    all_failures.extend(check_version_consistency(repo_root))

    if all_failures:
        # Group output by category prefix for readability
        categories = {}
        for f in all_failures:
            cat = f.split("-")[0] + "-" + f.split("-")[1]  # e.g. EVAL-PY
            categories.setdefault(cat, []).append(f)

        print(f"FAILED -- {len(all_failures)} issue(s) across {len(skill_files)} skill files:\n")
        for cat in sorted(categories):
            print(f"  [{cat}]")
            for issue in categories[cat]:
                print(f"    FAIL  {issue}")
            print()
        sys.exit(1)
    else:
        print(
            f"PASSED -- {len(skill_files)} skill files, "
            f"{python_block_count} Python blocks, "
            f"8 categories checked"
        )


if __name__ == "__main__":
    main()
