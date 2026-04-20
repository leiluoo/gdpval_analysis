#!/usr/bin/env python3
"""
Generate agentic tasks and write to generated_tasks.jsonl.

Usage:
    python build_prompt.py                 # generate 5000 tasks
    python build_prompt.py --count 100     # generate 100 tasks
    python build_prompt.py --resume        # continue from existing output
    python build_prompt.py --count 10 --role "Nurse"  # filter by role
"""

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from threading import Lock

import os

import openai
from tqdm import tqdm

BASE_DIR    = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "generated_tasks.jsonl"
MODEL       = "gpt-5.1"
WORKERS     = 64

FORMATS = {
    "Microsoft Word (.docx)": {
        "weight": 48,
        "constraints": (
            "- Required file extension: .docx\n"
            "- Specify the page limit (e.g., 1 page, 2–3 pages)\n"
            "- Include clearly labeled section headings\n"
            "- May include tables, numbered lists, headers/footers"
        ),
    },
    "PDF (.pdf)": {
        "weight": 45,
        "constraints": (
            "- Required file extension: .pdf\n"
            "- Specify the exact page count or page limit\n"
            "- May specify page orientation (portrait or landscape)\n"
            "- Suitable for: formal reports, reference sheets, regulatory submissions"
        ),
    },
    "Excel (.xlsx)": {
        "weight": 21,
        "constraints": (
            "- Required file extension: .xlsx\n"
            "- Specify the worksheet (tab) names\n"
            "- Specify key column headers by name\n"
            "- Suitable for: trackers, financial models, schedules, contact lists"
        ),
    },
    "PowerPoint (.pptx)": {
        "weight": 16,
        "constraints": (
            "- Required file extension: .pptx\n"
            "- Specify the slide count (e.g., 8–12 slides)\n"
            "- Include a title slide; content slides use bullet points\n"
            "- Suitable for: briefings, training decks, strategy presentations"
        ),
    },
    "ZIP archive (.zip)": {
        "weight": 4,
        "constraints": (
            "- Required file extension: .zip\n"
            "- List exactly which files must be inside the archive\n"
            "- Each file inside has its own format (.py, .tf, .md, .json, etc.)\n"
            "- Suitable for: code deliverables, multi-document packages"
        ),
    },
}

_NAMES   = list(FORMATS.keys())
_WEIGHTS = [FORMATS[n]["weight"] for n in _NAMES]


def load_roles() -> list[dict]:
    with open(BASE_DIR / "task_statements.jsonl") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_template() -> str:
    with open(BASE_DIR / "task_generator_prompt.md") as f:
        return f.read()


def sample_format() -> tuple[str, str]:
    name = random.choices(_NAMES, weights=_WEIGHTS, k=1)[0]
    return name, FORMATS[name]["constraints"]


def build_prompt(template: str, role: dict, task: str,
                 fmt_name: str, fmt_constraints: str) -> str:
    return (
        template
        .replace("<<JOB_TITLE>>",         role["title"])
        .replace("<<ROLE_TASKS>>",         "\n".join(f"- {t}" for t in role["tasks"]))
        .replace("<<SELECTED_TASK>>",      task)
        .replace("<<TARGET_FORMAT>>",      fmt_name)
        .replace("<<FORMAT_CONSTRAINTS>>", fmt_constraints)
    )


def parse_response(raw: str) -> dict:
    """Extract and validate the JSON object from the model response."""
    text = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$",        "", text.strip(), flags=re.MULTILINE).strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object in response")

    parsed = json.loads(match.group())

    if "prompt" not in parsed or "rubric" not in parsed:
        raise ValueError(f"Missing fields, got keys: {list(parsed.keys())}")

    if len(parsed["prompt"].split()) < 80:
        raise ValueError(f"Prompt too short ({len(parsed['prompt'].split())} words)")

    n_criteria = len(re.findall(r"^\[[\+\-][\+\-]?\d+\]", parsed["rubric"], re.MULTILINE))
    if n_criteria < 10:
        raise ValueError(f"Rubric too sparse ({n_criteria} criteria)")

    return parsed


def count_existing(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path) as f:
        return sum(1 for l in f if l.strip())


def worker(client: openai.OpenAI, template: str, roles: list[dict]) -> dict:
    """Generate one task. Returns dict with prompt/rubric/_role/_fmt. Raises on failure."""
    role              = random.choice(roles)
    task              = random.choice(role["tasks"])
    fmt_name, fmt_con = sample_format()
    prompt            = build_prompt(template, role, task, fmt_name, fmt_con)

    last_err = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            raw    = resp.choices[0].message.content
            parsed = parse_response(raw)
            parsed["_role"] = role["title"]
            parsed["_fmt"]  = fmt_name
            return parsed
        except openai.RateLimitError:
            time.sleep(60 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed after 3 attempts: {last_err}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count",   type=int, default=5000)
    parser.add_argument("--resume",  action="store_true",
                        help="Continue appending to existing output file")
    parser.add_argument("--role",    type=str, default=None,
                        help="Filter roles by substring")
    parser.add_argument("--workers", type=int, default=WORKERS,
                        help=f"Concurrent workers (default: {WORKERS})")
    args = parser.parse_args()

    if OUTPUT_FILE.exists() and not args.resume:
        print(f"ERROR: {OUTPUT_FILE} already exists. Use --resume to append, "
              "or delete the file first.", file=sys.stderr)
        sys.exit(1)

    roles    = load_roles()
    template = load_template()
    client   = openai.OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ["OPENAI_API_KEY"],
    )

    if args.role:
        roles = [r for r in roles if args.role.lower() in r["title"].lower()]
        if not roles:
            print(f"No roles matching '{args.role}'", file=sys.stderr)
            sys.exit(1)

    already_done = count_existing(OUTPUT_FILE)
    target       = args.count
    remaining    = target - already_done

    if remaining <= 0:
        print(f"Already have {already_done} tasks, nothing to do.")
        return

    write_lock = Lock()
    success    = already_done
    skipped    = 0

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        with tqdm(total=target, initial=already_done, unit="task",
                  dynamic_ncols=True) as pbar:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                # Fill the initial pool
                pending = {
                    executor.submit(worker, client, template, roles)
                    for _ in range(min(args.workers, remaining))
                }

                while pending and success < target:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)

                    for f in done:
                        try:
                            result = f.result()
                            record = {"prompt": result["prompt"], "rubric": result["rubric"]}
                            with write_lock:
                                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                                out.flush()
                            success += 1
                            pbar.update(1)
                            pbar.set_postfix_str(
                                f"{result['_role'][:28]} | {result['_fmt'].split('(')[0].strip()[:6]}"
                            )
                        except Exception as e:
                            skipped += 1
                            tqdm.write(f"  SKIP ({skipped}): {e}")

                        # Keep the pool full
                        if success + len(pending) < target:
                            pending.add(executor.submit(worker, client, template, roles))

    print(f"\nDone. {success}/{target} written, {skipped} skipped  →  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
