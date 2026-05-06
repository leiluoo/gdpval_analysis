"""
Download full gdpval dataset (all 220 tasks) and classify rubric items by type.

Rubric type taxonomy:
- file_format: Criteria about what file type/format is produced (PDF, Word, Excel, PNG, etc.)
- document_structure: Page count, orientation, sections/headings, table layout, single-page constraints
- content_completeness: Whether all required elements/items are present in the output
- content_accuracy: Specific factual content, exact values, correct text, citations
- visual_diagram: Charts, images, diagrams, flow charts, icons, plots
- quantitative: Numeric calculations, budget totals, formulas, percentages, arithmetic
- web_research: Internet research, external links/URLs, publicly available sources
- technical_spec: Specific technical configurations, settings, hardware specifications
- formatting_style: Visual formatting, typography, overall presentation quality
- instruction_follow: Following specific instructions about naming, phrasing, directives
"""

import json
import re
from datasets import load_dataset
from pathlib import Path

# ── Taxonomy keyword patterns ────────────────────────────────────────────────

def classify_rubric_item(criterion: str, score: int) -> list[str]:
    c = criterion.lower()
    tags = []

    # file_format: about the file type/format of deliverable
    if re.search(
        r'\b(pdf|\.pdf|docx|\.docx|\.doc\b|word document|microsoft word|excel|\.xlsx|\.xls\b|\.xlsm|'
        r'workbook|\.pptx|\.ppt\b|powerpoint|\.png\b|\.jpg\b|\.mp4\b|\.zip\b|'
        r'file (is|format|type|extension|delivered|submitted|provided|saved)|'
        r'deliverable is (a|an)|delivered as|submitted as|provided as|saved as|'
        r'exports? (as|to)|single file|file opens|file name|basename|filename)',
        c
    ):
        tags.append('file_format')

    # document_structure: sections, headings, layout, page constraints
    if re.search(
        r'\b(section|heading|header|footer|title|page|landscape|portrait|orientation|'
        r'table|column|row|bullet|numbered list|one.page|single.page|'
        r'margin|font size|font type|paragraph|appendix|cover page|table of contents|'
        r'tab\b|worksheet named|sheet named|sheet tab|'
        r'layout|structure|order|sequence|side.by.side|'
        r'labeled (section|paragraph|heading)|clearly identif|'
        r'organized by|sorted by|grouped by|arranged by|'
        r'displays? (monthly|weekly|daily|quarterly|annual)|'
        r'schedule (is|contains|covers|shows)|'
        r'detail(ed)? schedule)',
        c
    ):
        tags.append('document_structure')

    # visual_diagram: images, diagrams, charts, icons, visual elements
    if re.search(
        r'\b(image|diagram|chart|plot|figure|icon|visual|graphic|illustration|'
        r'screenshot|photo|picture|drawing|map|wiring|signal flow|stage plot|'
        r'flowchart|flow chart|process (map|diagram)|infographic|'
        r'\.png\b|\.jpg\b|\.svg\b|rendered|annotated|color.coded|colour.coded|'
        r'arrow|node|shape|connector|swim.?lane|lane)',
        c
    ):
        tags.append('visual_diagram')

    # quantitative: calculations, numbers, budget, formulas
    if re.search(
        r'\b(calculat|formula|budget|total|sum|subtotal|price|cost|\$|usd|'
        r'percentage|percent|%|ratio|rate|average|mean|median|'
        r'numeric|number|count|quantity|amount|value|equals?|'
        r'arithmetic|within [\d±]|less than|greater than|at most|at least \d|'
        r'within \±|\+\/\-|rounding|±\d|'
        r'beginning balance|current month|amortiz|depreciat|accumulat|'
        r'line \d+[a-z]?|form \d{4}|schedule [a-z0-9]|'
        r'\bis \$|\bis \d+[,\d]*\.?\d*|revenue|income|tax|deduction|'
        r'balance|ledger|journal entry|credit|debit|'
        r'\b\d+ fte\b|fte (of|under|to)|revises? \d|reduces? \d|'
        r'compares? (current|planned)|\d+[-–]\d{2,4} fte|'
        r'duration (is|of)|\d+ (minutes?|seconds?|hours?)|between \d:\d)',
        c
    ):
        tags.append('quantitative')

    # web_research: internet sourcing, URLs, external references
    if re.search(
        r'\b(link|url|http|website|web|online|internet|'
        r'public(ly)? available|retailer|product page|'
        r'cit(e|es|ing|ation)|reference[sd]?|source[sd]?|'
        r'academic article|journal|peer.reviewed|publication|'
        r'based on.*source|adapted from)',
        c
    ):
        tags.append('web_research')

    # technical_spec: hardware specs, software settings, technical configurations
    if re.search(
        r'\b(specification|spec\b|bandwidth|frequency|channel|rf\b|xlr|'
        r'input|output|signal|voltage|impedance|ohm|watt|'
        r'resolution|bit\b|sample rate|latency|compression|reverb|delay|eq\b|'
        r'microphone|amplifier|transmitter|receiver|antenna|'
        r'api|endpoint|parameter|configuration|setting|protocol|'
        r'formula[s]?\b|cell reference|named range|structured table|vlookup|'
        r'pivot table|macro|vba\b|function\b.*excel)',
        c
    ):
        tags.append('technical_spec')

    # content_accuracy: exact text, specific factual requirements, named entities
    if re.search(
        r'\b(exact(ly)?|specific(ally)?|correct(ly)?|accurate(ly)?|'
        r'matches?|equal[s]?|named|labeled|titled|states?\b|'
        r'mentions?|identifies?|includes? (the|a specific|the exact)|'
        r'explicitly (states?|mentions?|says?|indicates?)|'
        r'the (title|author|date|name|value|text|word|phrase|label)\b|'
        r'the memo (communicates|clarifies|outlines|explains|states|describes)|'
        r'the (document|report|plan|note|letter|email|brief) (specif|describ|explain|outlin|clarif|states|communicates|confirms)|'
        r'revises?|explains? that|addressed to|describes the|'
        r'background and|proposed (reductions?|changes?)|'
        r'harmonic key|in (g|a|b|c|d|e|f) (major|minor)|'
        r'(placed|position(ed)?) (between|on stage|at center|upstage|downstage))',
        c
    ):
        tags.append('content_accuracy')

    # content_completeness: presence of required elements
    if re.search(
        r'\b(includes?|contains?|covers?|provides?|presents?|lists?|'
        r'at least (one|two|three|\d+)|all (required|listed|specified)|'
        r'each (of|item|section|article|study)|'
        r'every (item|column|row|field)|'
        r'present\b|provided\b|appear[s]?\b)',
        c
    ):
        tags.append('content_completeness')

    # formatting_style: overall quality, visual style, subjective presentation
    if re.search(
        r'\b(format(ting)?|style|presentation|overall|appearance|'
        r'professional|clean|readable|legible|consistent|'
        r'color|colour|spacing|alignment|indentation|'
        r'visually|aesthetic|polished|concise|point.form|'
        r'overall formatting and style)',
        c
    ):
        tags.append('formatting_style')

    # instruction_follow: following specific prompt instructions (naming, directives, constraints)
    if re.search(
        r'\b(should|must|need to|required to|instructed|'
        r'as (instructed|specified|requested|directed|stated)|'
        r'per (the|instructions?|requirements?|prompt)|'
        r'directive|action verb|imperative|'
        r'counterclockwise|clockwise|'
        r'does not|excludes?|omits?|without|no (more than|less than)|'
        r'only (the|two|one|five)|'
        r'numbered (counterclockwise|from|starting)|'
        r'placed (diagonally|at|in front|behind))',
        c
    ):
        tags.append('instruction_follow')

    # Catch-all: if nothing matched, mark as 'general'
    if not tags:
        tags.append('general')

    return tags


def make_task_level_tags(rubric_items: list[dict]) -> list[str]:
    """Summarize rubric item types into task-level tags."""
    all_item_tags = set()
    for item in rubric_items:
        for t in item.get('rubric_type_tags', []):
            all_item_tags.add(t)
    return sorted(all_item_tags)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading gdpval dataset from HuggingFace...")
    ds = load_dataset('openai/gdpval')
    train = ds['train']
    print(f"Loaded {len(train)} tasks total")

    out_dir = Path(__file__).parent
    all_tasks_path = out_dir / 'all_tasks.jsonl'
    with_ref_path = out_dir / 'tasks_with_reference.jsonl'

    no_ref_count = 0
    with_ref_count = 0
    tag_distribution = {}  # rubric type tag -> count

    with open(all_tasks_path, 'w') as f_all, \
         open(with_ref_path, 'w') as f_ref:

        for row in train:
            rubric_items = json.loads(row['rubric_json'])

            # Classify each rubric item
            for item in rubric_items:
                type_tags = classify_rubric_item(
                    item.get('criterion', ''),
                    item.get('score', 0)
                )
                item['rubric_type_tags'] = type_tags
                for t in type_tags:
                    tag_distribution[t] = tag_distribution.get(t, 0) + 1

            task = {
                'task_id': row['task_id'],
                'sector': row['sector'],
                'occupation': row['occupation'],
                'prompt': row['prompt'],
                'has_reference_files': bool(row['reference_files']),
                'reference_file_urls': row['reference_file_urls'],
                'rubric': row['rubric_pretty'],
                'rubric_items': rubric_items,
                'task_rubric_type_tags': make_task_level_tags(rubric_items),
            }

            f_all.write(json.dumps(task, ensure_ascii=False) + '\n')

            if row['reference_files']:
                f_ref.write(json.dumps(task, ensure_ascii=False) + '\n')
                with_ref_count += 1
            else:
                no_ref_count += 1

    print(f"\nWrote {len(train)} tasks to {all_tasks_path}")
    print(f"  - {no_ref_count} tasks without reference files")
    print(f"  - {with_ref_count} tasks with reference files -> {with_ref_path}")

    print("\n=== Rubric item type tag distribution ===")
    total_items = sum(tag_distribution.values())
    for tag, count in sorted(tag_distribution.items(), key=lambda x: -x[1]):
        pct = 100.0 * count / total_items
        print(f"  {tag:<25} {count:>5}  ({pct:.1f}%)")

    # Also compute task-level distribution
    print("\n=== Task-level rubric type coverage ===")
    task_tag_counts = {}
    with open(all_tasks_path) as f:
        for line in f:
            task = json.loads(line)
            for t in task['task_rubric_type_tags']:
                task_tag_counts[t] = task_tag_counts.get(t, 0) + 1
    for tag, count in sorted(task_tag_counts.items(), key=lambda x: -x[1]):
        pct = 100.0 * count / len(train)
        print(f"  {tag:<25} {count:>3} tasks  ({pct:.0f}%)")


if __name__ == '__main__':
    main()
