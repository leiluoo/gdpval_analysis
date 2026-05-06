"""
Analyze judge results by rubric tag category.

Reads result.jsonl from a/task_{i}/workdir/result.jsonl via MoXing,
joins with rubric_tag_dict.json, and reports pass rate by tag.

Usage:
  python analyze_results.py --base obs://your-bucket/path/to/a
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import moxing as mox

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
TAG_DICT_PATH = SCRIPT_DIR / "rubric_tag_dict.json"

ALL_TAGS = [
    "deliverable_format",
    "document_structure",
    "content_presence",
    "specific_value",
    "domain_knowledge",
    "reference_compliance",
    "calculation_formula",
    "visual_element",
    "writing_quality",
    "instruction_follow",
    "external_sourcing",
]


def load_tag_dict() -> dict[str, str]:
    return json.loads(TAG_DICT_PATH.read_text(encoding="utf-8"))


def iter_task_dirs(base: str) -> list[str]:
    """Return sorted list of task_i paths that exist under base."""
    entries = mox.file.list_directory(base)
    task_dirs = sorted(
        e for e in entries
        if e.startswith("task_") and mox.file.is_directory(f"{base}/{e}")
    )
    return [f"{base}/{d}" for d in task_dirs]


def load_result_jsonl(path: str) -> list[dict]:
    """Read and parse result.jsonl from an OBS path."""
    raw = mox.file.read(path)
    return json.loads(raw)


def analyze(base: str, tag_dict: dict[str, str]) -> None:
    # Per-tag accumulators: {tag: {"total": int, "pass": int, "score_sum": float, "score_max": float}}
    tag_stats: dict[str, dict] = {
        t: {"total": 0, "pass": 0, "score_sum": 0.0, "score_max": 0.0}
        for t in ALL_TAGS
    }
    unmatched_criteria: list[str] = []

    task_dirs = iter_task_dirs(base)
    print(f"Found {len(task_dirs)} task directories under {base}\n")

    for task_dir in task_dirs:
        result_path = f"{task_dir}/workdir/result.json"
        if not mox.file.exists(result_path):
            print(f"  [SKIP] {result_path} not found")
            continue

        try:
            items = load_result_jsonl(result_path)
        except Exception as e:
            print(f"  [ERROR] {result_path}: {e}")
            continue

        for item in items:
            criterion = item.get("criterion", "")
            passed = bool(item.get("result", False))
            score = float(item.get("score", 1))

            tag = tag_dict.get(criterion)
            if tag is None:
                unmatched_criteria.append(criterion)
                tag = "content_presence"  # fallback

            s = tag_stats[tag]
            s["total"] += 1
            s["score_max"] += score
            if passed:
                s["pass"] += 1
                s["score_sum"] += score

    # ── Print report ──────────────────────────────────────────────────────────
    print("=" * 72)
    print(f"{'Tag':<25} {'Pass':>6} {'Total':>6} {'PassRate':>9} {'ScoreRate':>10}")
    print("-" * 72)

    overall_pass = overall_total = 0
    overall_score = overall_score_max = 0.0

    rows = []
    for tag in ALL_TAGS:
        s = tag_stats[tag]
        if s["total"] == 0:
            continue
        pass_rate = s["pass"] / s["total"]
        score_rate = s["score_sum"] / s["score_max"] if s["score_max"] > 0 else 0.0
        rows.append((tag, s["pass"], s["total"], pass_rate, score_rate, s["score_sum"], s["score_max"]))
        overall_pass += s["pass"]
        overall_total += s["total"]
        overall_score += s["score_sum"]
        overall_score_max += s["score_max"]

    rows.sort(key=lambda r: r[0])

    for tag, p, t, pr, sr, _, _ in rows:
        bar = "█" * int(sr * 20)
        print(f"  {tag:<23} {p:>6} {t:>6}   {pr:>7.1%}   {sr:>8.1%}  {bar}")

    print("-" * 72)
    if overall_total > 0:
        overall_pr = overall_pass / overall_total
        overall_sr = overall_score / overall_score_max if overall_score_max > 0 else 0.0
        print(f"  {'OVERALL':<23} {overall_pass:>6} {overall_total:>6}   {overall_pr:>7.1%}   {overall_sr:>8.1%}")
    print("=" * 72)

    if unmatched_criteria:
        unique_unmatched = list(dict.fromkeys(unmatched_criteria))
        print(f"\n[WARN] {len(unmatched_criteria)} criteria not found in tag dict "
              f"({len(unique_unmatched)} unique), fell back to content_presence.")
        for c in unique_unmatched[:5]:
            print(f"  - {c[:100]}")
        if len(unique_unmatched) > 5:
            print(f"  ... and {len(unique_unmatched) - 5} more")


def main():
    parser = argparse.ArgumentParser(description="Analyze judge results by rubric tag")
    parser.add_argument("--base", required=True,
                        help="OBS base path containing task_i/ directories, e.g. obs://bucket/path/to/a")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    tag_dict = load_tag_dict()
    print(f"Loaded {len(tag_dict)} tag mappings\n")

    analyze(base, tag_dict)


if __name__ == "__main__":
    main()
