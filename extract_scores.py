"""从本地 benchmark 目录（q1..q12 的 benchmark_qN.md）里抽取分数。

不同题目的排版不完全一致，按以下优先级找 GPT 总分：
    1) "GPT 5.6 Pro：X/10"
    2) 表格 "| **总分** | **X/10** |"
    3) 正文 "**总分：X/10**"
    4) 兜底：第一条总分

豆包得分：
    1) "第 k 次：X/10"（可能少于 5 条，void 的那次不计）
    2) 旧版没有分次标题 → 用六条总分里的后五条

用法：
    python extract_scores.py            # 只打印
    python extract_scores.py --write    # 写入 data/items.csv 和 data/runs.csv
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

# 本地 benchmark 目录（该目录含原始题目与回答，不要提交到公开仓库）
BENCH = Path(__file__).resolve().parent.parent.parent / "benchmark"
OUT = Path(__file__).parent / "data"

NUM = r"([0-9]+(?:\.[0-9]+)?)"
RE_TITLE = re.compile(r"^#\s*Benchmark Item\s*(Q\d+)\s*[:：]\s*(.+)$", re.M)
RE_TYPE = re.compile(r"\*\*标签：\s*([SRAP])\b")
RE_GPT_LINE = re.compile(r"GPT\s*5\.6\s*Pro[^\n]{0,20}?[：:]\s*\$?\s*" + NUM + r"\s*/\s*10")
RE_TOTAL_TABLE = re.compile(r"\|\s*\*\*总分\*\*\s*\|\s*\*\*\s*\$?\s*" + NUM + r"\s*/\s*10")
RE_TOTAL = re.compile(r"总分[：:]\s*\$?\s*" + NUM + r"\s*/\s*10")
RE_RUN = re.compile(r"第\s*([1-5])\s*次：\s*" + NUM + r"\s*/\s*10")
RE_AXIS = re.compile(r"Definition Recovery[：:]\s*([0-9.]+)\s*/\s*([0-9.]+)")


def parse_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")

    m = RE_TITLE.search(text)
    qid = m.group(1) if m else path.parent.name[:2].upper()
    title = m.group(2).strip() if m else ""

    mt = RE_TYPE.search(text)
    ptype = mt.group(1) if mt else ""

    gpt = None
    for rx in (RE_GPT_LINE, RE_TOTAL_TABLE, RE_TOTAL):
        hit = rx.search(text)
        if hit:
            gpt = float(hit.group(1))
            break

    totals = [float(x) for x in RE_TOTAL.findall(text)]

    runs = {}
    for k, v in RE_RUN.findall(text):
        runs[int(k)] = float(v)

    if runs:
        doubao = [runs[k] for k in sorted(runs)]
        src = f"分次({len(doubao)}/5)"
    elif len(totals) >= 6:
        doubao = totals[1:6]
        src = "旧版后五条"
    else:
        doubao = []
        src = "缺"

    if gpt is None and totals:
        gpt = totals[0]

    ax = RE_AXIS.search(text)

    return {
        "item_id": qid,
        "title": title,
        "prompt_type": ptype,
        "gpt": gpt,
        "runs": doubao,
        "run_src": src,
        "def_axis": ax.group(1) if ax else "",
        "def_axis_max": ax.group(2) if ax else "",
        "file": path.parent.name,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = [parse_file(f) for f in sorted(BENCH.glob("q*/benchmark_q*.md"))]
    rows.sort(key=lambda r: int(re.sub(r"\D", "", r["item_id"]) or 0))

    print(f"{'ID':<5}{'type':<5}{'GPT':>6}  {'doubao runs':<30}{'src':<12}  title")
    print("-" * 105)
    problems = []
    for r in rows:
        d = " ".join(f"{x:.1f}" for x in r["runs"]) or "-"
        g = f"{r['gpt']:.1f}" if r["gpt"] is not None else "??"
        print(f"{r['item_id']:<5}{r['prompt_type'] or '?':<5}{g:>6}  {d:<30}{r['run_src']:<12}  {r['title'][:38]}")
        if r["gpt"] is None or not r["runs"] or not r["prompt_type"]:
            problems.append(r["file"])

    print()
    if problems:
        print("CHECK MANUALLY:", ", ".join(problems))
    else:
        print("OK: 12 items parsed.")

    if args.write:
        # 保留手工维护的列（first_fail / fail_layer / missing_steps / error_tags / note）
        path = OUT / "items.csv"
        extra_cols = ["def_score", "reason_score", "pres_score", "first_fail", "fail_layer", "missing_steps", "error_tags"]
        old = {}
        if path.exists():
            prev = pd.read_csv(path, dtype=str).fillna("")
            for _, r in prev.iterrows():
                old[(r["item_id"], r["model"])] = r.to_dict()

        item_rows, run_rows = [], []
        for r in rows:
            for model in ("gpt", "doubao"):
                base = old.get((r["item_id"], model), {})
                total = r["gpt"] if model == "gpt" else (
                    round(sum(r["runs"]) / len(r["runs"]), 2) if r["runs"] else ""
                )
                row = {
                    "item_id": r["item_id"],
                    "title": r["title"],
                    "prompt_type": r["prompt_type"],
                    "model": model,
                    "total": "" if total == "" or total is None else total,
                }
                for c in extra_cols:
                    row[c] = base.get(c, "")
                if model == "doubao":
                    row["note"] = f"五次均值（有效 {len(r['runs'])} 次）"
                item_rows.append(row)

            run_rows.append(
                {
                    "item_id": r["item_id"],
                    **{f"run{i}": (r["runs"][i - 1] if len(r["runs"]) >= i else "") for i in range(1, 6)},
                }
            )

        cols = [
            "item_id", "title", "prompt_type", "model", "def_score", "reason_score",
            "pres_score", "total", "first_fail", "fail_layer", "missing_steps", "error_tags", "note",
        ]
        pd.DataFrame(item_rows)[cols].to_csv(path, index=False, encoding="utf-8-sig")
        pd.DataFrame(run_rows).to_csv(OUT / "runs.csv", index=False, encoding="utf-8-sig")
        print(f"written: {path}")
        print(f"written: {OUT / 'runs.csv'}")


if __name__ == "__main__":
    main()
