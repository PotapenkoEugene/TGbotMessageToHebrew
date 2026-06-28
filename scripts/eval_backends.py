#!/usr/bin/env python3
"""
Eval harness — compare translation backends on real bot data.

Runs one backend (configured via env vars) on a sample of real messages
from the tgbot.db and saves results to eval_results/<backend>_<timestamp>.json.

Usage
-----
Single-backend run (run once per model):
    TRANSLATOR_BACKEND=claude python scripts/eval_backends.py
    TRANSLATOR_BACKEND=local LOCAL_LLM_URL=http://localhost:8080/v1 \\
        LOCAL_LLM_MODEL=dictalm3-12b PRON_STYLE=both \\
        python scripts/eval_backends.py

Then generate the comparison report:
    python scripts/eval_backends.py --report

Options
-------
  --n N           Sample size per task type (default: 10)
  --db PATH       Path to tgbot.db (default: from config / ~/Library/Application Support/tgbot/tgbot.db)
  --output FILE   Override output file path
  --report        Generate HTML comparison report from all saved eval_results/*.json files
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("BOT_TOKEN", "eval-placeholder")

import aiosqlite  # noqa: E402

from tgbot.config import config  # noqa: E402
from tgbot.translators import make_translator  # noqa: E402

DEFAULT_DB = Path.home() / "Library" / "Application Support" / "tgbot" / "tgbot.db"
EVAL_RESULTS_DIR = Path(__file__).parent.parent / "eval_results"


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

async def sample_bot_messages(db_path: str, n: int) -> list[dict]:
    """Return up to n rows from bot_messages, balanced across RU→HE and EN→HE."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT original_text, translation FROM bot_messages
            ORDER BY RANDOM() LIMIT ?
            """,
            (n * 2,),  # fetch more, then filter
        ) as cur:
            rows = await cur.fetchall()
    return [{"original": r["original_text"], "translation": r["translation"]} for r in rows][:n]


async def sample_problems(db_path: str, n: int) -> list[dict]:
    """Return up to n explain interactions from the problems table."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT original_text, translation FROM problems ORDER BY RANDOM() LIMIT ?",
            (n,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"original": r["original_text"], "translation": r["translation"]} for r in rows]


# ---------------------------------------------------------------------------
# Per-task evaluation
# ---------------------------------------------------------------------------

async def eval_translate_to_hebrew(tr, items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        t0 = time.monotonic()
        try:
            he, pron = await tr.translate_to_hebrew(item["original"])
            elapsed = time.monotonic() - t0
            results.append({
                "input": item["original"],
                "he": he,
                "pron": pron,
                "latency_s": round(elapsed, 2),
                "ok": True,
            })
        except Exception as exc:
            elapsed = time.monotonic() - t0
            results.append({
                "input": item["original"],
                "error": str(exc),
                "latency_s": round(elapsed, 2),
                "ok": False,
            })
    return results


async def eval_translate_to_russian(tr, items: list[dict]) -> list[dict]:
    """Translate the Hebrew part (first line of stored translation) back to Russian."""
    results = []
    for item in items:
        he_text = item["translation"].split("\n")[0]
        t0 = time.monotonic()
        try:
            ru = await tr.translate_to_russian(he_text)
            elapsed = time.monotonic() - t0
            results.append({
                "input": he_text,
                "translation": ru,
                "reference_original": item["original"],
                "latency_s": round(elapsed, 2),
                "ok": True,
            })
        except Exception as exc:
            elapsed = time.monotonic() - t0
            results.append({
                "input": he_text,
                "error": str(exc),
                "latency_s": round(elapsed, 2),
                "ok": False,
            })
    return results


async def eval_explain(tr, items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        t0 = time.monotonic()
        try:
            result = await tr.explain(item["original"], item["translation"])
            elapsed = time.monotonic() - t0
            results.append({
                "input_original": item["original"],
                "input_translation": item["translation"],
                "result": result,
                "latency_s": round(elapsed, 2),
                "ok": True,
            })
        except Exception as exc:
            elapsed = time.monotonic() - t0
            results.append({
                "input_original": item["original"],
                "error": str(exc),
                "latency_s": round(elapsed, 2),
                "ok": False,
            })
    return results


async def eval_grammar_check(tr, items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        he_text = item["translation"].split("\n")[0]
        t0 = time.monotonic()
        try:
            result = await tr.grammar_check(he_text)
            elapsed = time.monotonic() - t0
            results.append({
                "input": he_text,
                "result": result,
                "latency_s": round(elapsed, 2),
                "ok": True,
            })
        except Exception as exc:
            elapsed = time.monotonic() - t0
            results.append({
                "input": he_text,
                "error": str(exc),
                "latency_s": round(elapsed, 2),
                "ok": False,
            })
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _avg(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def generate_report(result_files: list[Path]) -> str:
    """Produce a self-contained HTML comparison table from eval result files."""
    all_runs: list[dict] = []
    for f in sorted(result_files):
        with open(f) as fh:
            all_runs.append(json.load(fh))

    if not all_runs:
        return "<p>No eval results found.</p>"

    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem}",
        "h1,h2{color:#333}",
        "table{border-collapse:collapse;width:100%;margin-bottom:2rem}",
        "th,td{border:1px solid #ccc;padding:6px 10px;vertical-align:top;text-align:left}",
        "th{background:#f0f0f0}",
        ".he{direction:rtl;font-size:1.1em}",
        ".ok{color:green}.err{color:red}",
        ".pron{font-style:italic;white-space:pre-line}",
        "</style></head><body>",
        "<h1>Translation Backend Comparison</h1>",
    ]

    # Summary table
    lines.append("<h2>Summary</h2>")
    lines.append("<table><tr><th>Backend</th><th>Model</th><th>Tasks</th>"
                 "<th>HE avg latency</th><th>RU avg latency</th><th>JSON valid %</th></tr>")
    for run in all_runs:
        backend = run.get("backend", "?")
        model = run.get("model", "?")
        tasks = ", ".join(run.get("tasks_run", []))

        he_lats = [r["latency_s"] for r in run.get("translate_to_hebrew", []) if r["ok"]]
        ru_lats = [r["latency_s"] for r in run.get("translate_to_russian", []) if r["ok"]]
        all_results = (
            run.get("translate_to_hebrew", []) +
            run.get("translate_to_russian", []) +
            run.get("explain", []) +
            run.get("grammar_check", [])
        )
        ok_count = sum(1 for r in all_results if r["ok"])
        total = len(all_results)
        pct = round(100 * ok_count / total) if total else 0

        lines.append(
            f"<tr><td>{backend}</td><td>{model}</td><td>{tasks}</td>"
            f"<td>{_avg(he_lats)}s</td><td>{_avg(ru_lats)}s</td>"
            f"<td class='{'ok' if pct > 90 else 'err'}'>{pct}%</td></tr>"
        )
    lines.append("</table>")

    # Per-task comparison
    for task in ("translate_to_hebrew", "translate_to_russian", "explain", "grammar_check"):
        # Collect runs that have this task
        task_runs = [(r, r.get(task, [])) for r in all_runs if r.get(task)]
        if not task_runs:
            continue

        lines.append(f"<h2>{task}</h2>")

        # Find common inputs across runs (by input field)
        first_inputs = [item.get("input") or item.get("input_original") or ""
                        for item in task_runs[0][1]]

        headers = ["#", "Input"] + [r["backend"] + " / " + r.get("model", "?")
                                     for r, _ in task_runs]
        lines.append("<table><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")

        for i, inp in enumerate(first_inputs):
            cells = [str(i + 1), f"<td>{inp[:120]}</td>"]
            for run, items in task_runs:
                if i >= len(items):
                    cells.append("<td>—</td>")
                    continue
                item = items[i]
                if not item["ok"]:
                    cells.append(f"<td class='err'>ERROR: {item.get('error','?')[:80]}</td>")
                    continue

                if task == "translate_to_hebrew":
                    pron = item.get("pron", "")
                    lat = round(item.get("latency_s", 0), 2)
                    cells.append(
                        f"<td>"
                        f"<span class='he'>{item.get('he','')}</span><br>"
                        f"<span class='pron'>{pron}</span><br>"
                        f"<small>{lat}s</small>"
                        f"</td>"
                    )
                elif task == "translate_to_russian":
                    cells.append(
                        f"<td>{item.get('translation','')}<br>"
                        f"<small>{item.get('latency_s')}s</small></td>"
                    )
                elif task == "explain":
                    rows = item.get("result", {}).get("rows", [])
                    ctx = item.get("result", {}).get("context", "")
                    row_html = "<br>".join(
                        f"<span class='he'>{r['he']}</span> {r.get('base','')} — {r['ru']}"
                        for r in rows
                    )
                    cells.append(
                        f"<td>{row_html}<br><em>{ctx}</em><br>"
                        f"<small>{item.get('latency_s')}s</small></td>"
                    )
                elif task == "grammar_check":
                    issues = item.get("result", {}).get("issues", [])
                    summary = item.get("result", {}).get("summary", "")
                    issue_html = "<br>".join(
                        f"<span class='he'>{iss['phrase']}</span>→"
                        f"<span class='he'>{iss.get('suggest','')}</span>: {iss.get('why','')}"
                        for iss in issues
                    ) or "✓ no issues"
                    cells.append(
                        f"<td>{issue_html}<br><em>{summary}</em><br>"
                        f"<small>{item.get('latency_s')}s</small></td>"
                    )

            lines.append("<tr>" + "".join(f"<td>{c}</td>" if not c.startswith("<td") else c
                                          for c in cells) + "</tr>")

        lines.append("</table>")

    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_eval(db_path: str, n: int, output_path: Path) -> None:
    backend_name = config.translator_backend
    model_name = (
        config.local_llm_model if backend_name == "local" else config.claude_model
    )
    pron_style = config.pron_style

    print(f"Backend: {backend_name}  Model: {model_name}  pron_style: {pron_style}")
    print(f"DB: {db_path}  n={n}")

    tr = make_translator()
    print("Starting translator...")
    await tr.start()

    print("Sampling data from DB...")
    msg_items = await sample_bot_messages(db_path, n)
    explain_items = await sample_problems(db_path, n)

    # Fall back to msg_items for explain/grammar if problems table is sparse
    if len(explain_items) < n // 2:
        explain_items = msg_items[: n // 2]
        print(f"  problems table sparse, using {len(explain_items)} bot_messages for explain/grammar")

    tasks_run = []
    results: dict = {
        "backend": backend_name,
        "model": model_name,
        "pron_style": pron_style,
        "n": n,
        "db": str(db_path),
    }

    print(f"\n[1/4] translate_to_hebrew  ({len(msg_items)} items)...")
    results["translate_to_hebrew"] = await eval_translate_to_hebrew(tr, msg_items)
    tasks_run.append("translate_to_hebrew")
    ok = sum(1 for r in results["translate_to_hebrew"] if r["ok"])
    print(f"      {ok}/{len(msg_items)} ok")

    print(f"[2/4] translate_to_russian ({len(msg_items)} items)...")
    results["translate_to_russian"] = await eval_translate_to_russian(tr, msg_items)
    tasks_run.append("translate_to_russian")
    ok = sum(1 for r in results["translate_to_russian"] if r["ok"])
    print(f"      {ok}/{len(msg_items)} ok")

    print(f"[3/4] explain              ({len(explain_items)} items)...")
    results["explain"] = await eval_explain(tr, explain_items)
    tasks_run.append("explain")
    ok = sum(1 for r in results["explain"] if r["ok"])
    print(f"      {ok}/{len(explain_items)} ok")

    print(f"[4/4] grammar_check        ({len(explain_items)} items)...")
    results["grammar_check"] = await eval_grammar_check(tr, explain_items)
    tasks_run.append("grammar_check")
    ok = sum(1 for r in results["grammar_check"] if r["ok"])
    print(f"      {ok}/{len(explain_items)} ok")

    results["tasks_run"] = tasks_run

    print("\nStopping translator...")
    await tr.stop()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate translation backends")
    parser.add_argument("--n", type=int, default=10, help="Sample size per task")
    parser.add_argument("--db", type=str, default=None, help="Path to tgbot.db")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--report", action="store_true",
                        help="Generate HTML comparison report from saved results")
    args = parser.parse_args()

    if args.report:
        result_files = list(EVAL_RESULTS_DIR.glob("*.json"))
        if not result_files:
            print(f"No result files found in {EVAL_RESULTS_DIR}")
            sys.exit(1)
        report_html = generate_report(result_files)
        report_path = EVAL_RESULTS_DIR / "comparison_report.html"
        with open(report_path, "w") as f:
            f.write(report_html)
        print(f"Report saved to {report_path}")
        return

    db_path = args.db or str(DEFAULT_DB if DEFAULT_DB.exists() else config.db_path)

    if args.output:
        output_path = Path(args.output)
    else:
        backend_name = config.translator_backend
        model_slug = (
            config.local_llm_model if backend_name == "local" else config.claude_model
        ).replace("/", "-").replace(":", "-")
        ts = str(int(time.time()))
        output_path = EVAL_RESULTS_DIR / f"{backend_name}_{model_slug}_{ts}.json"

    asyncio.run(run_eval(db_path, args.n, output_path))


if __name__ == "__main__":
    main()
