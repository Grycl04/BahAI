#!/usr/bin/env python3
"""
Build thesis-ready AI accuracy tables from evaluation_outputs CSVs.

Outputs:
  - evaluation_outputs/thesis_nlu_overall_performance.csv
  - evaluation_outputs/thesis_nlu_per_intent_success_fail.csv
  - docs/evaluation/AI_ACCURACY_TABLE_FOR_THESIS.md

Run from repo root:
  python evaluation/build_thesis_accuracy_summary.py
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "evaluation_outputs" / "aligned_option2_detailed_predictions.csv"
PER_INTENT = ROOT / "evaluation_outputs" / "aligned_option2_per_intent_metrics.csv"
CONFUSION = ROOT / "evaluation_outputs" / "aligned_option2_confusion_pairs.csv"
OUT_OVERALL = ROOT / "evaluation_outputs" / "thesis_nlu_overall_performance.csv"
OUT_PER_INTENT = ROOT / "evaluation_outputs" / "thesis_nlu_per_intent_success_fail.csv"
OUT_MD = ROOT / "docs" / "evaluation" / "AI_ACCURACY_TABLE_FOR_THESIS.md"


def main() -> None:
    if not PRED.is_file():
        raise SystemExit(f"Missing {PRED}")
    if not PER_INTENT.is_file():
        raise SystemExit(f"Missing {PER_INTENT}")

    rows: list[dict[str, str]] = []
    with PRED.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k.strip(): (v or "").strip() for k, v in row.items()})

    n = len(rows)
    correct = sum(
        1
        for row in rows
        if row.get("expected_intent", "").lower() == row.get("predicted_intent", "").lower()
    )
    wrong = n - correct
    success_pct = round(100.0 * correct / n, 2) if n else 0.0
    fail_pct = round(100.0 * wrong / n, 2) if n else 0.0

    # Overall CSV (single-row + label rows for Word paste)
    OUT_OVERALL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_OVERALL.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "Evaluation",
                "Total_queries",
                "Successful_predictions",
                "Failed_predictions",
                "Success_rate_percent",
                "Fail_rate_percent",
            ]
        )
        w.writerow(
            [
                "Custom NLU (TF-IDF + classifier), held-out 20% after class balancing (aligned Option 2)",
                n,
                correct,
                wrong,
                success_pct,
                fail_pct,
            ]
        )

    # Per-intent: rename to thesis columns
    intent_rows: list[dict[str, str]] = []
    with PER_INTENT.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            intent_rows.append({k.strip(): (v or "").strip() for k, v in row.items()})

    with OUT_PER_INTENT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "Intent_label",
                "Test_queries",
                "Correct",
                "Wrong",
                "Success_rate_percent",
                "Fail_rate_percent",
            ]
        )
        for row in intent_rows:
            w.writerow(
                [
                    row.get("intent", ""),
                    row.get("test_queries", ""),
                    row.get("correct", ""),
                    row.get("wrong", ""),
                    row.get("accuracy_percent", ""),
                    row.get("error_percent", ""),
                ]
            )

    # Confusion top lines for markdown
    confusion_lines: list[str] = []
    if CONFUSION.is_file():
        with CONFUSION.open(encoding="utf-8-sig", newline="") as f:
            cr = csv.DictReader(f)
            for i, row in enumerate(cr):
                if i >= 12:
                    break
                confusion_lines.append(
                    f"| {row.get('expected_intent','')} | {row.get('predicted_intent','')} | {row.get('count','')} |"
                )

    # Hardest intents (by fail %)
    def fail_key(r: dict[str, str]) -> float:
        try:
            return float(r.get("error_percent", "0") or 0)
        except ValueError:
            return 0.0

    hardest = sorted(intent_rows, key=fail_key, reverse=True)[:8]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = f"""# AI accuracy tables (custom NLU model)

This document summarizes **your own trained intent classifier** (not an external chat API).  
Metrics come from **held-out test data** (20% holdout, stratified after balancing):  
`evaluation_outputs/aligned_option2_detailed_predictions.csv`.

---

## Table 1 — Overall NLU performance (all test queries)

| Metric | Value |
|--------|------:|
| **Total test queries** | {n} |
| **Successful predictions** (expected intent = predicted intent) | {correct} |
| **Failed predictions** (wrong intent) | {wrong} |
| **Success rate** | **{success_pct}%** |
| **Fail rate** (classification error) | **{fail_pct}%** |

*Fail rate* = the model picked the **wrong intent label** for that query.  
The live BahAI chatbot **adds rule-based overrides** on top of this model (not counted in this table).

CSV copy-paste: `evaluation_outputs/thesis_nlu_overall_performance.csv`

---

## Table 2 — Per-intent success and fail (%)

Each row is one **intent class**. **Success rate %** = correct ÷ test queries for that intent. **Fail %** = wrong ÷ test queries.

| Intent | Test queries | Success rate % | Fail % |
|--------|-------------:|---------------:|-------:|
"""
    for row in intent_rows:
        md += f"| `{row.get('intent','')}` | {row.get('test_queries','')} | {row.get('accuracy_percent','')}% | {row.get('error_percent','')}% |\n"

    md += """
Full table CSV: `evaluation_outputs/thesis_nlu_per_intent_success_fail.csv`

---

## Table 3 — What the model gets wrong most often (top confusion pairs)

True label → wrongly predicted as → count (held-out test):

| Expected intent | Predicted instead | Count |
|-----------------|-------------------|------:|
"""
    if confusion_lines:
        md += "\n".join(confusion_lines) + "\n"
    else:
        md += "| *Run evaluation to generate* `aligned_option2_confusion_pairs.csv` | | |\n"

    md += f"""
Source: `evaluation_outputs/aligned_option2_confusion_pairs.csv`

---

## “What it cannot answer” (how to explain in your paper)

1. **Wrong intent ({fail_pct}% of test queries)** — The model still **answers**, but may run the **wrong handler** (e.g. confuses `greeting` with `about_system`). That is **classification error**, not silence.

2. **`out_of_scope` intent** — Training includes off-topic phrases; **not every possible off-topic** is in data. In held-out evaluation, `out_of_scope` had **{next((r.get('error_percent','n/a') for r in intent_rows if r.get('intent')=='out_of_scope'), 'n/a')}%** fail rate (see Table 2).

3. **Production system** — After NLU, `chatbot_backend.py` applies **regex / keyword overrides** and optional **Groq/OpenAI fallback** for some cases; that is **beyond** this pure NLU accuracy table.

### Intents with highest fail rate (hardest for the model)

| Intent | Success % | Fail % |
|--------|----------:|-------:|
"""
    for row in hardest:
        md += f"| `{row.get('intent','')}` | {row.get('accuracy_percent','')}% | {row.get('error_percent','')}% |\n"

    md += """
---

## Files to submit with the thesis

| File | Purpose |
|------|---------|
| `evaluation_outputs/thesis_nlu_overall_performance.csv` | One-row overall success/fail % |
| `evaluation_outputs/thesis_nlu_per_intent_success_fail.csv` | Per-intent success % / fail % |
| `evaluation_outputs/aligned_option2_detailed_predictions.csv` | Every query + expected + predicted intent |
| `evaluation/build_thesis_accuracy_summary.py` | Regenerate tables after retraining |

"""

    OUT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT_OVERALL}")
    print(f"Wrote {OUT_PER_INTENT}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
