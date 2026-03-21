#!/usr/bin/env python3
"""validate-skill.py — Score a skill against a quality rubric (0-100).

Usage:
    python validate-skill.py <skill-directory> [--json] [--verbose]

Checks:
    - SKILL.md structure and word count
    - Frontmatter completeness and description quality
    - Progressive disclosure (references exist and are referenced)
    - Script quality (shebang, error handling, help text)
    - Reference quality (length, self-containment)
    - Context efficiency (no unnecessary loading)

Exit codes:
    0  Skill scores 70+  (good)
    1  Skill scores <70   (needs work)
    2  Invalid arguments or missing SKILL.md
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    category: str
    severity: str  # "error", "warning", "info"
    message: str
    suggestion: str = ""


@dataclass
class CategoryScore:
    name: str
    score: float  # 0-100
    weight: float  # How much this category matters (0-1)
    findings: list = field(default_factory=list)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from SKILL.md content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Simple YAML parser (avoids requiring PyYAML)
    fm = {}
    current_key = None
    current_value_lines = []

    for line in frontmatter_text.split("\n"):
        # Check for key: value
        match = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', line)
        if match and not line.startswith("  ") and not line.startswith("\t"):
            # Save previous key
            if current_key:
                val = "\n".join(current_value_lines).strip()
                fm[current_key] = val
            current_key = match.group(1)
            current_value_lines = [match.group(2).strip()]
        elif current_key:
            current_value_lines.append(line)

    # Save last key
    if current_key:
        val = "\n".join(current_value_lines).strip()
        fm[current_key] = val

    # Parse allowed-tools as list
    if "allowed-tools" in fm:
        tools_text = fm["allowed-tools"]
        tools = [t.strip().lstrip("- ") for t in tools_text.split("\n") if t.strip().startswith("-")]
        fm["allowed-tools"] = tools if tools else [tools_text]

    return fm, body


def count_words(text: str) -> int:
    """Count words in text, excluding code blocks and frontmatter."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    return len(text.split())


def check_frontmatter(fm: dict, skill_dir: Path) -> CategoryScore:
    """Validate frontmatter completeness and quality."""
    cat = CategoryScore(name="frontmatter", score=100, weight=0.20)

    # Required fields
    required = ["name", "description"]
    for field_name in required:
        if field_name not in fm or not fm[field_name]:
            cat.score -= 30
            cat.findings.append(Finding(
                "frontmatter", "error",
                f"Missing required field: {field_name}",
                f"Add '{field_name}' to the YAML frontmatter"
            ))

    # Name should be kebab-case
    if "name" in fm:
        name = fm["name"]
        if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', name):
            cat.score -= 10
            cat.findings.append(Finding(
                "frontmatter", "warning",
                f"Name '{name}' is not kebab-case",
                "Use lowercase letters, numbers, and hyphens only"
            ))

    # Description quality
    if "description" in fm:
        desc = fm["description"]
        desc_len = len(desc)

        if desc_len > 1024:
            cat.score -= 15
            cat.findings.append(Finding(
                "frontmatter", "warning",
                f"Description is {desc_len} chars (max recommended: 1024)",
                "Trim the description — it should be concise but trigger-rich"
            ))
        elif desc_len < 50:
            cat.score -= 20
            cat.findings.append(Finding(
                "frontmatter", "error",
                f"Description is only {desc_len} chars — too short for reliable triggering",
                "Add trigger phrases, use cases, and keywords to the description"
            ))

        # Check for trigger phrases
        trigger_indicators = ["use when", "use this", "should be used", "trigger", "keyword"]
        has_triggers = any(t in desc.lower() for t in trigger_indicators)
        if not has_triggers:
            cat.score -= 10
            cat.findings.append(Finding(
                "frontmatter", "warning",
                "Description lacks explicit trigger phrases",
                "Add 'Use when...' or 'Keywords:' to help Claude know when to invoke this skill"
            ))

    # allowed-tools
    if "allowed-tools" not in fm:
        cat.score -= 5
        cat.findings.append(Finding(
            "frontmatter", "info",
            "No allowed-tools specified",
            "List the tools this skill needs (Bash, Read, Write, etc.)"
        ))

    cat.score = max(0, cat.score)
    return cat


def check_skill_md(body: str, skill_dir: Path) -> CategoryScore:
    """Validate SKILL.md body content."""
    cat = CategoryScore(name="skill_md_content", score=100, weight=0.25)

    word_count = count_words(body)
    line_count = len(body.split("\n"))

    # Word count scoring
    if word_count > 5000:
        cat.score -= 35
        cat.findings.append(Finding(
            "skill_md_content", "error",
            f"SKILL.md is {word_count} words — way too long (max: 5000, ideal: 1500-2000)",
            "Move detailed content to references/. SKILL.md should orchestrate, not contain everything."
        ))
    elif word_count > 3000:
        cat.score -= 20
        cat.findings.append(Finding(
            "skill_md_content", "warning",
            f"SKILL.md is {word_count} words — getting long (ideal: 1500-2000)",
            "Consider moving domain-specific details to reference files"
        ))
    elif word_count > 2000:
        cat.score -= 5
        cat.findings.append(Finding(
            "skill_md_content", "info",
            f"SKILL.md is {word_count} words — slightly above ideal (1500-2000)",
            "Minor: see if any sections could be references instead"
        ))
    elif word_count < 200:
        cat.score -= 25
        cat.findings.append(Finding(
            "skill_md_content", "warning",
            f"SKILL.md is only {word_count} words — may be too thin to guide effectively",
            "Ensure core workflow steps and decision logic are documented"
        ))

    # Line count check
    if line_count > 500:
        cat.score -= 15
        cat.findings.append(Finding(
            "skill_md_content", "warning",
            f"SKILL.md is {line_count} lines (recommended: <500)",
            "Long SKILL.md means more context consumed on every trigger. Move depth to references/."
        ))

    # Check for headings structure
    headings = re.findall(r'^#{1,3}\s+.+', body, re.MULTILINE)
    if len(headings) < 3:
        cat.score -= 10
        cat.findings.append(Finding(
            "skill_md_content", "warning",
            f"Only {len(headings)} headings found — skill may lack structure",
            "Use headings to organize phases/sections of the workflow"
        ))

    # Check for imperative form (heuristic: look for "you should" which isn't imperative)
    second_person = len(re.findall(r'\byou\s+(should|must|need|can|will)\b', body, re.IGNORECASE))
    if second_person > 5:
        cat.score -= 10
        cat.findings.append(Finding(
            "skill_md_content", "warning",
            f"Found {second_person} instances of second-person instructions ('you should/must/need')",
            "Use imperative form instead: 'Check the file' not 'You should check the file'"
        ))

    return cat


def check_progressive_disclosure(body: str, skill_dir: Path) -> CategoryScore:
    """Validate progressive disclosure patterns."""
    cat = CategoryScore(name="progressive_disclosure", score=100, weight=0.25)

    refs_dir = skill_dir / "references"
    scripts_dir = skill_dir / "scripts"

    has_refs = refs_dir.exists() and any(
        f.suffix in ('.md', '.txt') for f in refs_dir.iterdir() if f.is_file() and f.name != '.gitkeep'
    ) if refs_dir.exists() else False

    has_scripts = scripts_dir.exists() and any(
        f.suffix in ('.sh', '.py', '.js') for f in scripts_dir.iterdir() if f.is_file() and f.name != '.gitkeep'
    ) if scripts_dir.exists() else False

    # Check if references are actually referenced in SKILL.md
    if has_refs:
        ref_files = [f.name for f in refs_dir.iterdir() if f.is_file() and f.name != '.gitkeep']
        unreferenced = []
        for ref_file in ref_files:
            if ref_file not in body and ref_file.replace('.md', '') not in body:
                unreferenced.append(ref_file)

        if unreferenced:
            cat.score -= 15
            cat.findings.append(Finding(
                "progressive_disclosure", "warning",
                f"Orphaned references (not mentioned in SKILL.md): {', '.join(unreferenced)}",
                "Reference each file in SKILL.md with guidance on WHEN to read it"
            ))

        # Check for conditional loading instructions
        conditional_patterns = [
            r'read\s+.*when', r'load\s+.*if', r'consult\s+.*for',
            r'refer\s+to', r'see\s+.*for\s+detail', r'when.*read',
            r'if.*need.*read', r'for\s+(?:more|detailed|in-depth)'
        ]
        has_conditional = any(re.search(p, body, re.IGNORECASE) for p in conditional_patterns)
        if not has_conditional:
            cat.score -= 10
            cat.findings.append(Finding(
                "progressive_disclosure", "warning",
                "No conditional loading instructions found for references",
                "Add 'Read references/X.md when [condition]' so context is loaded only when needed"
            ))
    else:
        # No references at all — might be fine for simple skills, but flag it
        word_count = count_words(body)
        if word_count > 1500:
            cat.score -= 15
            cat.findings.append(Finding(
                "progressive_disclosure", "warning",
                "No reference files but SKILL.md is large — content may benefit from being split out",
                "Move detailed domain knowledge to references/ and keep SKILL.md as the orchestrator"
            ))

    # Check if scripts are referenced
    if has_scripts:
        script_files = [f.name for f in scripts_dir.iterdir() if f.is_file() and f.name != '.gitkeep']
        unreferenced_scripts = []
        for script_file in script_files:
            if script_file not in body:
                unreferenced_scripts.append(script_file)

        if unreferenced_scripts:
            cat.score -= 10
            cat.findings.append(Finding(
                "progressive_disclosure", "warning",
                f"Scripts not referenced in SKILL.md: {', '.join(unreferenced_scripts)}",
                "Document each script in SKILL.md with usage instructions"
            ))

    # Check for nested references (references pointing to other references via links or read instructions)
    if has_refs:
        ref_files = [f for f in refs_dir.iterdir() if f.suffix == '.md' and f.name != '.gitkeep']
        for ref_file in ref_files:
            ref_content = ref_file.read_text(encoding='utf-8', errors='replace')
            other_refs = [f.name for f in ref_files if f != ref_file]
            # Only flag actual reference-style links, not incidental mentions in examples
            # Look for patterns like: "read references/file.md", "see [file.md]", "(file.md)"
            nested = []
            for r in other_refs:
                # Use word boundary or path separator to avoid substring matches
                # e.g., "script-patterns.md" shouldn't match inside "typescript-patterns.md"
                escaped = re.escape(r)
                link_patterns = [
                    rf'(?:read|see|load|consult|refer to)\s+.*(?<![a-zA-Z-]){escaped}',
                    rf'\[{escaped}\]',
                    rf'\({escaped}\)',
                    rf'`references/{escaped}`',
                ]
                if any(re.search(p, ref_content, re.IGNORECASE) for p in link_patterns):
                    nested.append(r)
            if nested:
                cat.score -= 15
                cat.findings.append(Finding(
                    "progressive_disclosure", "warning",
                    f"{ref_file.name} references other ref files: {', '.join(nested)} — nested references cause partial reads",
                    "Keep references one level deep from SKILL.md. Each reference should be self-contained."
                ))

    # Penalize "always read" or "first read all" patterns
    # Exclude lines that are warnings/negations about the pattern (e.g., "Never load all", "No always-loaded")
    always_load_lines = re.findall(r'^.*(?:always|first)\s+(?:read|load|open)\s+(?:all|every).*$', body, re.IGNORECASE | re.MULTILINE)
    # Filter out lines that are warnings against the pattern
    negation_words = ['never', 'don\'t', 'do not', 'avoid', 'no ', 'not ', 'anti-pattern', 'defeats']
    always_load = [line for line in always_load_lines if not any(neg in line.lower() for neg in negation_words)]
    if always_load:
        cat.score -= 20
        cat.findings.append(Finding(
            "progressive_disclosure", "error",
            "Found 'always/first read all' patterns — defeats progressive disclosure",
            "Load references conditionally based on which phase/branch of the workflow is active"
        ))

    cat.score = max(0, cat.score)
    return cat


def check_scripts(skill_dir: Path) -> CategoryScore:
    """Validate script quality."""
    cat = CategoryScore(name="script_quality", score=100, weight=0.15)

    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.exists():
        cat.score = 50
        cat.findings.append(Finding(
            "script_quality", "info",
            "No scripts/ directory — skill has no deterministic helpers",
            "Consider what operations could be scripted for reliability and speed"
        ))
        return cat

    scripts = [f for f in scripts_dir.iterdir() if f.is_file() and f.name != '.gitkeep']
    if not scripts:
        cat.score = 50
        cat.findings.append(Finding(
            "script_quality", "info",
            "scripts/ directory exists but is empty",
            "Add helper scripts for deterministic operations"
        ))
        return cat

    for script in scripts:
        content = script.read_text(encoding='utf-8', errors='replace')
        lines = content.split('\n')

        # Shebang check
        if not lines[0].startswith('#!'):
            cat.score -= 10
            cat.findings.append(Finding(
                "script_quality", "warning",
                f"{script.name}: Missing shebang line",
                "Add #!/usr/bin/env bash (or python3) as the first line"
            ))

        if script.suffix == '.sh':
            # set -euo pipefail for bash
            has_strict = any('set -' in line and ('e' in line or 'pipefail' in line) for line in lines[:10])
            if not has_strict:
                cat.score -= 5
                cat.findings.append(Finding(
                    "script_quality", "info",
                    f"{script.name}: No 'set -euo pipefail' — errors may go unnoticed",
                    "Add 'set -euo pipefail' near the top for safety"
                ))

            # Help/usage function
            has_help = any('usage' in line.lower() or '--help' in line for line in lines)
            if not has_help:
                cat.score -= 5
                cat.findings.append(Finding(
                    "script_quality", "info",
                    f"{script.name}: No help/usage text",
                    "Add a usage() function and --help flag"
                ))

        elif script.suffix == '.py':
            # Docstring check
            has_docstring = '"""' in content[:500] or "'''" in content[:500]
            if not has_docstring:
                cat.score -= 5
                cat.findings.append(Finding(
                    "script_quality", "info",
                    f"{script.name}: No module docstring",
                    "Add a docstring describing what the script does and how to use it"
                ))

        # Check file is not empty
        if len(content.strip()) < 10:
            cat.score -= 15
            cat.findings.append(Finding(
                "script_quality", "error",
                f"{script.name}: Script is essentially empty",
                "Implement the script or remove it"
            ))

    cat.score = max(0, cat.score)
    return cat


def check_references(skill_dir: Path) -> CategoryScore:
    """Validate reference document quality."""
    cat = CategoryScore(name="reference_quality", score=100, weight=0.15)

    refs_dir = skill_dir / "references"
    if not refs_dir.exists():
        cat.findings.append(Finding(
            "reference_quality", "info",
            "No references/ directory",
            "Not all skills need references, but complex domains benefit from them"
        ))
        return cat

    refs = [f for f in refs_dir.iterdir() if f.suffix == '.md' and f.name != '.gitkeep']
    if not refs:
        cat.findings.append(Finding(
            "reference_quality", "info",
            "references/ directory exists but has no .md files",
            "Add reference documents for domain knowledge"
        ))
        return cat

    for ref in refs:
        content = ref.read_text(encoding='utf-8', errors='replace')
        word_count = count_words(content)
        line_count = len(content.split('\n'))

        # Length checks
        if word_count < 500:
            cat.score -= 10
            cat.findings.append(Finding(
                "reference_quality", "warning",
                f"{ref.name}: Only {word_count} words — may be too thin to justify a separate file",
                "Either expand with more depth or fold into SKILL.md if short enough"
            ))
        elif word_count > 8000:
            cat.score -= 10
            cat.findings.append(Finding(
                "reference_quality", "warning",
                f"{ref.name}: {word_count} words — very large reference consumes a lot of context",
                "Consider splitting into more focused sub-documents"
            ))

        # Check for headings
        headings = re.findall(r'^#{1,3}\s+.+', content, re.MULTILINE)
        if word_count > 1000 and len(headings) < 3:
            cat.score -= 5
            cat.findings.append(Finding(
                "reference_quality", "info",
                f"{ref.name}: Large reference ({word_count} words) with few headings",
                "Add headings/table of contents for navigability"
            ))

        # TOC check for large files (official docs recommend TOC at 100+ lines)
        if line_count > 100 and 'table of contents' not in content.lower() and '## contents' not in content.lower():
            cat.score -= 5
            cat.findings.append(Finding(
                "reference_quality", "info",
                f"{ref.name}: {line_count} lines with no table of contents",
                "Add a table of contents for files over 100 lines so Claude can see scope when previewing"
            ))

    cat.score = max(0, cat.score)
    return cat


def validate_skill(skill_dir: Path, verbose: bool = False) -> dict:
    """Run all validation checks and return results."""
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        return {
            "valid": False,
            "error": f"No SKILL.md found in {skill_dir}",
            "score": 0,
            "categories": []
        }

    content = skill_md_path.read_text(encoding='utf-8')
    fm, body = parse_frontmatter(content)

    # Run all checks
    categories = [
        check_frontmatter(fm, skill_dir),
        check_skill_md(body, skill_dir),
        check_progressive_disclosure(body, skill_dir),
        check_scripts(skill_dir),
        check_references(skill_dir),
    ]

    # Calculate weighted score
    total_weight = sum(c.weight for c in categories)
    weighted_score = sum(c.score * c.weight for c in categories) / total_weight

    # Collect all findings
    all_findings = []
    for cat in categories:
        all_findings.extend(cat.findings)

    return {
        "valid": True,
        "score": round(weighted_score, 1),
        "grade": (
            "A" if weighted_score >= 90 else
            "B" if weighted_score >= 80 else
            "C" if weighted_score >= 70 else
            "D" if weighted_score >= 60 else
            "F"
        ),
        "categories": [
            {
                "name": c.name,
                "score": round(c.score, 1),
                "weight": c.weight,
                "findings": [
                    {
                        "severity": f.severity,
                        "message": f.message,
                        "suggestion": f.suggestion,
                    }
                    for f in c.findings
                ]
            }
            for c in categories
        ],
        "summary": {
            "errors": len([f for f in all_findings if f.severity == "error"]),
            "warnings": len([f for f in all_findings if f.severity == "warning"]),
            "info": len([f for f in all_findings if f.severity == "info"]),
        },
        "skill_dir": str(skill_dir),
    }


def print_results(results: dict, verbose: bool = False) -> None:
    """Print human-readable validation results."""
    if not results["valid"]:
        print(f"ERROR: {results['error']}")
        return

    score = results["score"]
    grade = results["grade"]

    # Score header
    print(f"\n{'=' * 60}")
    print(f"  Skill Quality Score: {score}/100 (Grade: {grade})")
    print(f"  Path: {results['skill_dir']}")
    print(f"{'=' * 60}\n")

    # Category breakdown
    print("Category Scores:")
    for cat in results["categories"]:
        bar_len = int(cat["score"] / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        weight_pct = int(cat["weight"] * 100)
        print(f"  {cat['name']:<25} {bar} {cat['score']:>5.1f}  (weight: {weight_pct}%)")

    # Findings
    summary = results["summary"]
    print(f"\nFindings: {summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info\n")

    severity_icon = {"error": "✗", "warning": "!", "info": "·"}

    for cat in results["categories"]:
        if not cat["findings"]:
            continue

        if not verbose and all(f["severity"] == "info" for f in cat["findings"]):
            continue

        for f in cat["findings"]:
            if not verbose and f["severity"] == "info":
                continue
            icon = severity_icon.get(f["severity"], "?")
            print(f"  [{icon}] {f['message']}")
            if f["suggestion"]:
                print(f"      → {f['suggestion']}")

    if not verbose and summary["info"] > 0:
        print(f"\n  ({summary['info']} info-level findings hidden — use --verbose to see all)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Validate a skill against quality rubric and output a score (0-100)."
    )
    parser.add_argument("skill_dir", type=Path, help="Path to the skill directory")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all findings including info-level")
    args = parser.parse_args()

    if not args.skill_dir.is_dir():
        print(f"Error: '{args.skill_dir}' is not a directory", file=sys.stderr)
        sys.exit(2)

    results = validate_skill(args.skill_dir, args.verbose)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_results(results, args.verbose)

    # Exit code based on score
    if not results["valid"]:
        sys.exit(2)
    elif results["score"] < 70:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
