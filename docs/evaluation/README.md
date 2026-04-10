# AI accuracy table (thesis format)

## Quick: success %, fail %, and “what it gets wrong”

- **Readable doc (tables + explanation):** [`AI_ACCURACY_TABLE_FOR_THESIS.md`](AI_ACCURACY_TABLE_FOR_THESIS.md)
- **Canonical CSVs (keep these):**
  - **Option 2 (fair / held-out):** `aligned_option2_detailed_predictions.csv`, `aligned_option2_per_intent_metrics.csv`, `aligned_accuracy_summary.csv`, `aligned_option2_confusion_pairs.csv`
  - **Option 1 (older / all queries):** `option1_detailed_predictions.csv`, `option1_per_intent_metrics.csv`
- **Optional:** Regenerate extra thesis-style copies (one-row overall + renamed columns) with `python evaluation/build_thesis_accuracy_summary.py`

---

Your advisers’ **3-column** layout maps to the evaluation CSVs like this:

| Column in sketch | Use in BahAI export |
|------------------|---------------------|
| **Query**        | User message / test utterance |
| *(2nd column)*   | **Expected intent** (ground truth from training labels) |
| *(3rd column)*   | **Predicted intent** (what the NLU model returned) |

Optional **4th column** “Match: Correct / Incorrect” is available if the panel wants an explicit accuracy column per row.

## Files that already contain query + intents

- **`evaluation_outputs/aligned_option2_detailed_predictions.csv`** — full held-out test set (`query`, `expected_intent`, `predicted_intent`).
- **`evaluation_outputs/option1_detailed_predictions.csv`** — includes an extra **`source`** column (which JSON the line came from).

## Generate a printable HTML table (like a Word table)

From the repo root:

```bash
python evaluation/export_accuracy_table.py
```

Default output: **`evaluation_outputs/ai_accuracy_table_aligned_option2.html`** (all rows).

**Sample only** (e.g. first 40 lines for the chapter body; put the rest in an appendix):

```bash
python evaluation/export_accuracy_table.py --limit 40 --output docs/evaluation/accuracy_table_sample_40.html
```

**Add “Match” column:**

```bash
python evaluation/export_accuracy_table.py --four-columns --output evaluation_outputs/ai_accuracy_table_with_match_column.html
```

**Option 1 (325-query) sheet:**

```bash
python evaluation/export_accuracy_table.py --input evaluation_outputs/option1_detailed_predictions.csv --output evaluation_outputs/ai_accuracy_table_option1.html
```

Open the `.html` in a browser, copy into Word, or **Print → PDF** for submission.

Per-intent summary (not query-by-query): **`evaluation_outputs/aligned_option2_per_intent_metrics.csv`**.
