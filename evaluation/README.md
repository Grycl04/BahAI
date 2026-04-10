# NLU evaluation (local outputs)

Generated CSV/HTML/thesis markdown **are not committed to Git** — they live under `evaluation_outputs/` and `docs/evaluation/` on your machine only.

## Regenerate after training

From repo root:

```bash
python training/train_nlu.py
```

That refreshes `evaluation_outputs/aligned_option2_*.csv` (and the trained model).

## Rebuild per-intent metrics from detailed CSV

```bash
python evaluation/rebuild_option2_per_intent_metrics.py
```

## Thesis-style summary + CSV copies

```bash
python evaluation/build_thesis_accuracy_summary.py
```

Writes `docs/evaluation/AI_ACCURACY_TABLE_FOR_THESIS.md` and extra CSVs under `evaluation_outputs/`.

## HTML table for Word/PDF

```bash
python evaluation/export_accuracy_table.py
python evaluation/export_accuracy_table.py --four-columns --output evaluation_outputs/ai_accuracy_table_with_match_column.html
```

## Canonical Option 2 files (local)

- `evaluation_outputs/aligned_option2_detailed_predictions.csv`
- `evaluation_outputs/aligned_option2_per_intent_metrics.csv`
- `evaluation_outputs/aligned_accuracy_summary.csv`
- `evaluation_outputs/aligned_option2_confusion_pairs.csv`
