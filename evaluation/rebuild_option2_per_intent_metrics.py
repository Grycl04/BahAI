#!/usr/bin/env python3
"""
Rebuild evaluation_outputs/aligned_option2_per_intent_metrics.csv from
evaluation_outputs/aligned_option2_detailed_predictions.csv

Use when you updated the detailed predictions CSV (or HTML was regenerated)
but the per-intent metrics file was not refreshed.

Usage (repo root):
  python evaluation/rebuild_option2_per_intent_metrics.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAILED = ROOT / "evaluation_outputs" / "aligned_option2_detailed_predictions.csv"
OUT = ROOT / "evaluation_outputs" / "aligned_option2_per_intent_metrics.csv"


def main() -> None:
    if not DETAILED.is_file():
        raise SystemExit(f"Missing {DETAILED}")

    rows: list[tuple[str, str, str]] = []
    with DETAILED.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit("Empty CSV")
        # Normalize keys (strip); ignore trailing empty column in header
        fn = [h.strip() for h in reader.fieldnames if h and h.strip()]
        need = {"query", "expected_intent", "predicted_intent"}
        if not need.issubset(set(fn)):
            raise SystemExit(f"CSV must have columns {sorted(need)}; got {reader.fieldnames}")

        for row in reader:
            r = {k.strip(): (v or "").strip() for k, v in row.items() if k and k.strip()}
            q = r.get("query", "")
            exp = r.get("expected_intent", "")
            pred = r.get("predicted_intent", "")
            if not exp:
                continue
            rows.append((q, exp, pred))

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for _, exp, pred in rows:
        stats[exp]["total"] += 1
        if exp.lower() == pred.lower():
            stats[exp]["correct"] += 1

    n = len(rows)
    correct_all = sum(1 for _, e, p in rows if e.lower() == p.lower())
    wrong_all = n - correct_all
    acc_all = round(100.0 * correct_all / n, 2) if n else 0.0
    err_all = round(100.0 * wrong_all / n, 2) if n else 0.0

    per_rows: list[tuple[str, int, int, int, float, float]] = []
    for intent, s in stats.items():
        tot = s["total"]
        cor = s["correct"]
        wr = tot - cor
        ap = round(100.0 * cor / tot, 2) if tot else 0.0
        ep = round(100.0 * wr / tot, 2) if tot else 0.0
        per_rows.append((intent, tot, cor, wr, ap, ep))

    per_rows.sort(key=lambda r: (-r[4], r[0]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["intent", "test_queries", "correct", "wrong", "accuracy_percent", "error_percent"])
        for intent, tot, cor, wr, ap, ep in per_rows:
            w.writerow([intent, tot, cor, wr, ap, ep])
        w.writerow(["TOTAL:", n, correct_all, wrong_all, acc_all, err_all])

    print(f"Wrote {OUT} ({len(per_rows)} intents + TOTAL, from {n} detailed rows)")


if __name__ == "__main__":
    main()
