"""
LLM-based rubric item tagger for gdpval dataset.

Each rubric criterion gets exactly ONE most-relevant tag from an 11-category taxonomy.
Uses DeepSeek-v4-flash via OpenAI-compatible API; async concurrent batches.
Checkpointed for resume on interruption.

Outputs:
  all_tasks_tagged.jsonl  - all 220 tasks, each rubric_item has a single rubric_type_tag
  rubric_tag_dict.json    - {rubric_item_id: tag} for quick lookup when analyzing model results
"""

import asyncio
import json
import os
import threading
from pathlib import Path
from openai import AsyncOpenAI

# ── Config ────────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

BATCH_SIZE = 50
CONCURRENCY = 8

SCRIPT_DIR = Path(__file__).parent
CHECKPOINT_FILE = SCRIPT_DIR / "rubric_tags_checkpoint.jsonl"
OUTPUT_FILE = SCRIPT_DIR / "all_tasks_tagged.jsonl"
DICT_FILE = SCRIPT_DIR / "rubric_tag_dict.json"
INPUT_FILE = SCRIPT_DIR / "all_tasks.jsonl"

# ── Taxonomy ──────────────────────────────────────────────────────────────────
TAXONOMY = """
deliverable_format    - The primary concern is whether the output is the correct file type/format (PDF, Word, Excel, PNG, ZIP, etc.) or that a specific named file was produced
document_structure    - The primary concern is internal organization: sections, headings, table columns/rows, page orientation, worksheet names, page count, appendix, cover page
content_presence      - The primary concern is whether a required element, topic, or section exists somewhere in the output (but not the correctness of exact values)
specific_value        - The primary concern is whether a specific exact numeric value, text string, date, or named entity is correct (e.g. exact dollar amounts, exact percentages, exact person names used)
domain_knowledge      - The primary concern is correctness of domain-specific facts, regulations, or professional principles (medical, legal, financial, engineering knowledge)
reference_compliance  - The primary concern is whether the output correctly uses or matches data from a provided reference file supplied with the task
calculation_formula   - The primary concern is whether arithmetic, spreadsheet formulas, or derived computations are correct
visual_element        - The primary concern is whether a required visual item (diagram, chart, icon, stage plot, image, flow chart) is created and/or placed correctly
writing_quality       - The primary concern is writing tone, professional language, clarity, style, consistency, or overall aesthetic quality
instruction_follow    - The primary concern is following a specific constraint or directive from the prompt (ordering, naming convention, what to include/exclude, word limit, etc.)
external_sourcing     - The primary concern is use of external sources: academic citations, web links, publicly available data, sourcing from credible organizations
"""

SYSTEM_PROMPT = f"""You are classifying rubric criteria from a professional task evaluation dataset (GDPVal).
Each criterion is a single grading item used to assess AI-generated work products.

Assign EXACTLY ONE tag — the most relevant one — from this taxonomy:
{TAXONOMY}

Rules:
- Choose the single tag that best describes what the criterion is PRIMARILY TESTING
- Return ONLY valid JSON: an array of objects with "id" (integer) and "tag" (single string)
- No markdown, no explanation — just the JSON array
"""


# ── Checkpoint ────────────────────────────────────────────────────────────────
def load_checkpoint() -> dict[str, str]:
    done: dict[str, str] = {}
    if CHECKPOINT_FILE.exists():
        with CHECKPOINT_FILE.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    done[entry["rubric_item_id"]] = entry["tag"]
    return done


# ── Async batch classifier ────────────────────────────────────────────────────
async def classify_batch(
    client: AsyncOpenAI,
    items: list[dict],
    checkpoint_lock: threading.Lock,
    checkpoint_f,
    done: dict,
    counter: list,
    total: int,
) -> None:
    indexed = [{"id": i, "criterion": b["criterion"]} for i, b in enumerate(items)]
    lines_text = "\n".join(f'{item["id"]}. {item["criterion"]}' for item in indexed)
    user_msg = f"Classify these {len(items)} rubric criteria (one tag each):\n\n{lines_text}"

    for attempt in range(5):
        try:
            response = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=8192,
                temperature=0,
            )
            text = (response.choices[0].message.content or "").strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            results = json.loads(text)
            id_map = {r["id"]: r["tag"] for r in results}

            with checkpoint_lock:
                for i, item_meta in enumerate(items):
                    tag = id_map.get(i, "content_presence")
                    entry = {"rubric_item_id": item_meta["rubric_item_id"], "tag": tag}
                    checkpoint_f.write(json.dumps(entry) + "\n")
                    done[item_meta["rubric_item_id"]] = tag
                checkpoint_f.flush()
                counter[0] += len(items)
                pct = 100 * counter[0] / total
                print(f"  {counter[0]}/{total}  ({pct:.1f}%)", flush=True)
            return

        except Exception as e:
            wait = 2 ** attempt
            print(f"  Attempt {attempt + 1}/5 error: {e}  (retry in {wait}s)")
            await asyncio.sleep(wait)

    # Fallback
    with checkpoint_lock:
        for item_meta in items:
            entry = {"rubric_item_id": item_meta["rubric_item_id"], "tag": "content_presence"}
            checkpoint_f.write(json.dumps(entry) + "\n")
            done[item_meta["rubric_item_id"]] = "content_presence"
        checkpoint_f.flush()
        counter[0] += len(items)
        print(f"  FALLBACK batch: {counter[0]}/{total}", flush=True)


async def run_all(client: AsyncOpenAI, pending: list[dict], done: dict, checkpoint_f) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = threading.Lock()
    counter = [0]
    total = len(pending)

    async def bounded(batch):
        async with sem:
            await classify_batch(client, batch, lock, checkpoint_f, done, counter, total)

    batches = [pending[i: i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    await asyncio.gather(*[bounded(b) for b in batches])


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    tasks = []
    with INPUT_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    print(f"Loaded {len(tasks)} tasks")

    done = load_checkpoint()
    print(f"Already classified: {len(done)} items")

    pending: list[dict] = []
    for task in tasks:
        for item in task["rubric_items"]:
            rid = item["rubric_item_id"]
            if rid not in done:
                pending.append({"rubric_item_id": rid, "criterion": item["criterion"]})
    print(f"Items to classify: {len(pending)}")

    if pending:
        with CHECKPOINT_FILE.open("a", encoding="utf-8") as checkpoint_f:
            asyncio.run(run_all(client, pending, done, checkpoint_f))

    print(f"\nDone. Total classified: {len(done)}")

    # Write tagged JSONL and build lookup dict
    rubric_tag_dict: dict[str, str] = {}  # rubric_item_id -> tag
    tag_distribution: dict[str, int] = {}

    with OUTPUT_FILE.open("w", encoding="utf-8") as out_f:
        for task in tasks:
            for item in task["rubric_items"]:
                rid = item["rubric_item_id"]
                tag = done.get(rid, "content_presence")
                item["rubric_type_tag"] = tag
                rubric_tag_dict[rid] = tag
                tag_distribution[tag] = tag_distribution.get(tag, 0) + 1

            # Task-level: unique tags across rubric items (for quick overview)
            task_tags = sorted(set(item["rubric_type_tag"] for item in task["rubric_items"]))
            task["task_rubric_type_tags"] = task_tags

            out_f.write(json.dumps(task, ensure_ascii=False) + "\n")

    # Write lookup dict
    DICT_FILE.write_text(json.dumps(rubric_tag_dict, ensure_ascii=False, indent=2))

    print(f"\nWrote {OUTPUT_FILE}")
    print(f"Wrote lookup dict ({len(rubric_tag_dict)} entries) to {DICT_FILE}")

    print("\n=== Rubric item tag distribution ===")
    total = sum(tag_distribution.values())
    for tag, count in sorted(tag_distribution.items(), key=lambda x: -x[1]):
        print(f"  {tag:<25} {count:>5}  ({100*count/total:.1f}%)")

    print("\n=== Task-level tag coverage ===")
    task_tag_counts: dict[str, int] = {}
    for task in tasks:
        for t in task["task_rubric_type_tags"]:
            task_tag_counts[t] = task_tag_counts.get(t, 0) + 1
    for tag, count in sorted(task_tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag:<25} {count:>3} tasks  ({100*count/len(tasks):.0f}%)")


if __name__ == "__main__":
    main()
