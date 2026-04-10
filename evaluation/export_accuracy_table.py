#!/usr/bin/env python3
"""
Build a thesis-style "AI accuracy table based on query" from evaluation CSVs.

Input CSV columns (required): query, expected_intent, predicted_intent
Optional column: source (ignored unless --four-columns adds Source)

Usage:
  python evaluation/export_accuracy_table.py
  python evaluation/export_accuracy_table.py --input evaluation_outputs/option1_detailed_predictions.csv --output docs/evaluation/accuracy_table_option1.html
  python evaluation/export_accuracy_table.py --limit 40   # sample only for Chapter 4
"""
from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "evaluation_outputs" / "aligned_option2_detailed_predictions.csv"
DEFAULT_OUTPUT = ROOT / "evaluation_outputs" / "ai_accuracy_table_aligned_option2.html"


def _rel_to_root(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


def main() -> None:
    p = argparse.ArgumentParser(description="Export HTML accuracy table from predictions CSV")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="CSV with query,expected_intent,predicted_intent")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output .html path")
    p.add_argument("--limit", type=int, default=0, help="Max rows (0 = all)")
    p.add_argument(
        "--four-columns",
        action="store_true",
        help="Add column: Match (Correct / Incorrect) — 4 columns total",
    )
    p.add_argument("--title", type=str, default="AI Accuracy Table (Based on Query)")
    args = p.parse_args()

    inp = args.input
    if not inp.is_file():
        raise SystemExit(f"Input not found: {inp}")

    rows: list[dict[str, str]] = []
    with inp.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        need = {"query", "expected_intent", "predicted_intent"}
        if not reader.fieldnames or not need.issubset({h.strip() for h in reader.fieldnames}):
            raise SystemExit(f"CSV must have columns: {sorted(need)}; got {reader.fieldnames}")
        for row in reader:
            rows.append({k.strip(): (v or "").strip() for k, v in row.items()})
            if args.limit and len(rows) >= args.limit:
                break

    correct = sum(
        1
        for r in rows
        if r.get("expected_intent", "").lower() == r.get("predicted_intent", "").lower()
    )
    n = len(rows)
    acc = (100.0 * correct / n) if n else 0.0

    cols = ["Query", "Expected intent", "Predicted intent"]
    if args.four_columns:
        cols.append("Match")

    # Simple print-friendly styles (works in browser and Word “open HTML”)
    style = """
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 24px; color: #1a1a1a; }
    h1 { font-size: 1.25rem; margin-bottom: 8px; }
    .meta { color: #444; font-size: 0.9rem; margin-bottom: 20px; }
    table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
    th, td { border: 1px solid #333; padding: 8px 10px; vertical-align: top; text-align: left; }
    th { background: #f0f4f8; font-weight: 600; }
    tr:nth-child(even) { background: #fafafa; }
    .wrong { background: #fff4f4 !important; }
    .note { margin-top: 16px; font-size: 0.85rem; color: #555; }
    """

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8"/>',
        f"<title>{html.escape(args.title)}</title>",
        f"<style>{style}</style>",
        "</head>",
        "<body>",
        f"<h1>{html.escape(args.title)}</h1>",
        "<div class='meta'>",
        f"<strong>Source file:</strong> {html.escape(_rel_to_root(inp))}<br/>",
        f"<strong>Rows shown:</strong> {n} &nbsp;|&nbsp; <strong>Correct:</strong> {correct} &nbsp;|&nbsp; <strong>Accuracy:</strong> {acc:.2f}%",
        "</div>",
        "<table>",
        "<thead><tr>",
    ]
    for c in cols:
        lines.append(f"<th>{html.escape(c)}</th>")
    lines.append("</tr></thead><tbody>")

    for r in rows:
        q = r.get("query", "")
        exp = r.get("expected_intent", "")
        pred = r.get("predicted_intent", "")
        ok = exp.lower() == pred.lower()
        tr_class = "" if ok else " class='wrong'"
        lines.append(f"<tr{tr_class}>")
        lines.append(f"<td>{html.escape(q)}</td>")
        lines.append(f"<td>{html.escape(exp)}</td>")
        lines.append(f"<td>{html.escape(pred)}</td>")
        if args.four_columns:
            lines.append(f"<td>{'Correct' if ok else 'Incorrect'}</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    lines.append(
        "<p class='note'>Expected intent = label from your dataset; predicted intent = NLU model output. "
        "Rows highlighted in light red are misclassifications. Full numeric summary: "
        "<code>evaluation_outputs/aligned_accuracy_summary.csv</code>.</p>"
    )
    lines.append("</body></html>")

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {n} rows → {out}")


if __name__ == "__main__":
    main()
