"""汇总分析：读 items.csv / runs.csv，产出三张表 + 三张图。

用法：
    python analyze.py           # 读 data/ 下的真实数据
    python analyze.py --demo    # 用合成数据预览输出长什么样

输入：
    data/items.csv  每题每题模型一行：三轴分数、总分、题面类型、错误标签
    data/runs.csv   豆包五次采样的分数

输出：
    output/analysis.md      汇总报告（表格）
    output/fig1_items.png   每题总分对比
    output/fig2_type.png    题面类型 × 平均分
    output/fig3_stability.png  五次采样稳定性

说明：控制台用英文，避免 Windows 终端中文乱码；生成的 md 是 UTF-8。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"

MODELS = ["gpt", "doubao"]
MODEL_LABEL = {"gpt": "GPT", "doubao": "豆包"}
RUN_COLS = ["run1", "run2", "run3", "run4", "run5"]
# 题面类型的固定顺序：越靠前越自足
TYPE_ORDER = ["S", "R", "A", "P"]
# 失效层级：L0 定义 -> L3 边界
LAYERS = ["L0", "L1", "L2", "L3"]
LAYER_LABEL = {"L0": "L0 定义", "L1": "L1 构造", "L2": "L2 推理", "L3": "L3 边界"}

DEMO_SPEC = [
    ("Q1", "Demo Problem 1", "P", 8.5, 3.0),
    ("Q2", "Demo Problem 2", "A", 6.0, 5.5),
    ("Q3", "Demo Problem 3", "S", 9.0, 8.5),
    ("Q4", "Demo Problem 4", "P", 7.0, 2.5),
    ("Q5", "Demo Problem 5", "R", 8.0, 7.0),
    ("Q6", "Demo Problem 6", "P", 8.0, 4.0),
    ("Q7", "Demo Problem 7", "S", 9.5, 9.0),
    ("Q8", "Demo Problem 8", "A", 5.5, 5.0),
    ("Q9", "Demo Problem 9", "R", 7.5, 6.5),
    ("Q10", "Demo Problem 10", "S", 9.0, 8.0),
    ("Q11", "Demo Problem 11", "P", 6.5, 3.5),
    ("Q12", "Demo Problem 12", "R", 8.5, 7.5),
]


# ---------------------------------------------------------------- 读数据
def load_items(demo: bool = False) -> pd.DataFrame:
    if demo:
        return _demo_items()
    df = pd.read_csv(DATA / "items.csv", dtype=str).fillna("")
    for c in ["def_score", "reason_score", "pres_score", "total", "first_fail", "missing_steps"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["prompt_type"] = df["prompt_type"].str.strip().str.upper()
    if "fail_layer" in df.columns:
        df["fail_layer"] = df["fail_layer"].str.strip().str.upper()
    return df


def load_runs(demo: bool = False) -> pd.DataFrame:
    if demo:
        return _demo_runs()
    df = pd.read_csv(DATA / "runs.csv", dtype=str).fillna("")
    for c in RUN_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _demo_items() -> pd.DataFrame:
    """合成数据：故意让 P 类题得分低，用来演示"结论从哪来"。"""
    rows = []
    tags = {
        "Q1": ("E1;E3", "E1;E3;E5"),
        "Q2": ("E3", "E3;E5"),
        "Q3": ("", ""),
        "Q4": ("E1;E3", "E1;E3;E5"),
        "Q5": ("E5", "E5"),
        "Q6": ("E1;E3", "E1;E3;E5"),
        "Q7": ("", "E5"),
        "Q8": ("E3", "E3;E5"),
        "Q9": ("E5", "E5"),
        "Q10": ("", ""),
        "Q11": ("E1;E3", "E1;E3"),
        "Q12": ("E5", "E5"),
    }
    for qid, title, ptype, g, d in DEMO_SPEC:
        for model, total in (("gpt", g), ("doubao", d)):
            rows.append(
                {
                    "item_id": qid,
                    "title": title,
                    "prompt_type": ptype,
                    "model": model,
                    "def_score": round(total * 0.4, 1),
                    "reason_score": round(total * 0.5, 1),
                    "pres_score": round(total * 0.1, 1),
                    "total": total,
                    "error_tags": tags[qid][0 if model == "gpt" else 1],
                    "note": "",
                }
            )
    return pd.DataFrame(rows)


def _demo_runs() -> pd.DataFrame:
    """五次采样围绕豆包总分波动，保证与第 2 张表对得上。"""
    import random

    random.seed(7)
    rows = []
    for qid, _title, _ptype, _g, doubao_total in DEMO_SPEC:
        vals = [
            round(min(10.0, max(0.0, doubao_total + random.uniform(-1.2, 1.2))), 1)
            for _ in range(5)
        ]
        rows.append({"item_id": qid, **dict(zip(RUN_COLS, vals))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 表格
def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "|".join(["---"] * len(cols)) + "|",
    ]
    # 用 itertuples 而不是 iterrows：iterrows 会把整行统一转成 float，整数列会变成 12.00
    for tup in df.itertuples(index=False, name=None):
        cells = []
        for v in tup:
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                cells.append("")
            elif isinstance(v, bool):
                cells.append("是" if v else "否")
            elif isinstance(v, (int, float)):
                cells.append(str(int(v)) if float(v).is_integer() else f"{v:.2f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def has_data(df: pd.DataFrame, col: str = "total") -> bool:
    return col in df and df[col].notna().any()


def natural_key(s: str) -> int:
    """Q10 排在 Q9 后面，而不是 Q1 后面。"""
    digits = re.sub(r"\D", "", str(s))
    return int(digits) if digits else 0


# ---------------------------------------------------------------- 三张表
def table1_by_item(items: pd.DataFrame) -> pd.DataFrame:
    wide = items.pivot_table(index="item_id", columns="model", values="total", aggfunc="first")
    wide = wide.reindex(sorted(wide.index, key=natural_key))
    meta = (
        items.drop_duplicates("item_id")
        .set_index("item_id")[["title", "prompt_type"]]
    )
    out = meta.join(wide).reindex(columns=["title", "prompt_type", *MODELS])
    out.columns = ["题目", "题面类型", "GPT", "豆包"]
    return out.reset_index().rename(columns={"item_id": "ID"})


def table2_error_tags(items: pd.DataFrame) -> pd.DataFrame:
    rec = []
    for _, r in items.iterrows():
        raw = str(r.get("error_tags", "") or "")
        for tag in raw.replace("，", ";").replace(",", ";").split(";"):
            tag = tag.strip()
            if tag:
                rec.append({"tag": tag, "model": r["model"]})
    if not rec:
        return pd.DataFrame(columns=["错误标签", "GPT", "豆包"])
    t = pd.crosstab(pd.DataFrame(rec)["tag"], pd.DataFrame(rec)["model"]).reindex(columns=MODELS, fill_value=0)
    t = t.reset_index().rename(columns={"tag": "错误标签", "gpt": "GPT", "doubao": "豆包"})
    t[["GPT", "豆包"]] = t[["GPT", "豆包"]].astype(int)
    return t


def table3_by_type(items: pd.DataFrame) -> pd.DataFrame:
    ok = items.dropna(subset=["total"])
    if ok.empty:
        return pd.DataFrame(columns=["题面类型", "GPT 平均", "豆包 平均", "差值"])
    ok = ok.copy()
    ok["prompt_type"] = pd.Categorical(ok["prompt_type"], categories=TYPE_ORDER, ordered=True)
    g = ok.groupby(["prompt_type", "model"], observed=False)["total"].mean().unstack()
    g = g.reindex(columns=MODELS).sort_index()
    g["diff"] = g["gpt"] - g["doubao"]
    g = g.reset_index().rename(
        columns={
            "prompt_type": "题面类型",
            "gpt": "GPT 平均",
            "doubao": "豆包 平均",
            "diff": "差值",
        }
    )
    return g


def table4_overall(items: pd.DataFrame) -> pd.DataFrame:
    ok = items.dropna(subset=["total"])
    if ok.empty:
        return pd.DataFrame(columns=["模型", "平均分", "题数", "≥9 分题数"])
    rows = []
    for m in MODELS:
        s = ok[ok["model"] == m]["total"]
        rows.append(
            {
                "模型": MODEL_LABEL[m],
                "平均分": s.mean(),
                "题数": len(s),
                "≥9 分题数": int((s >= 9).sum()),
            }
        )
    df = pd.DataFrame(rows)
    df["题数"] = df["题数"].astype(int)
    df["≥9 分题数"] = df["≥9 分题数"].astype(int)
    return df


def table5_stability(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty or runs[RUN_COLS].isna().all().all():
        return pd.DataFrame(columns=["ID", "均值", "标准差", "极差"])
    r = runs.copy()
    r["均值"] = r[RUN_COLS].mean(axis=1)
    r["标准差"] = r[RUN_COLS].std(axis=1, ddof=1)
    r["极差"] = r[RUN_COLS].max(axis=1) - r[RUN_COLS].min(axis=1)
    out = r[["item_id", "均值", "标准差", "极差"]].rename(columns={"item_id": "ID"})
    return out


def table6_layers(items: pd.DataFrame) -> pd.DataFrame:
    """首次失效的层级分布。未失效 = first_fail 为 0 或空。"""
    if "fail_layer" not in items.columns:
        return pd.DataFrame(columns=["失效层级", "GPT", "豆包"])
    df = items.copy()
    df["fail_layer"] = df["fail_layer"].fillna("").astype(str).str.strip().str.upper()
    df.loc[df["fail_layer"] == "", "fail_layer"] = "未失效"
    t = pd.crosstab(df["fail_layer"], df["model"]).reindex(columns=MODELS, fill_value=0)
    t = t.reindex([*LAYERS, "未失效"], fill_value=0).reset_index()
    t.columns = ["失效层级", "GPT", "豆包"]
    t[["GPT", "豆包"]] = t[["GPT", "豆包"]].astype(int)
    t["层级"] = t["失效层级"].map(lambda x: LAYER_LABEL.get(x, x))
    return t[["层级", "GPT", "豆包"]]


def table7_missing(items: pd.DataFrame) -> pd.DataFrame:
    """缺失必要步骤数：对 10 分答案也有效，所以不会饱和。"""
    if "missing_steps" not in items.columns:
        return pd.DataFrame(columns=["模型", "平均缺步", "有缺步题数", "最大缺步"])
    ok = items.dropna(subset=["missing_steps"])
    if ok.empty:
        return pd.DataFrame(columns=["模型", "平均缺步", "有缺步题数", "最大缺步"])
    rows = []
    for m in MODELS:
        s = ok[ok["model"] == m]["missing_steps"]
        if s.empty:
            continue
        rows.append(
            {
                "模型": MODEL_LABEL[m],
                "平均缺步": round(float(s.mean()), 2),
                "有缺步题数": int((s > 0).sum()),
                "最大缺步": int(s.max()),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 图
def make_figures(items: pd.DataFrame, runs: pd.DataFrame) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skip figures")
        return []

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    OUT.mkdir(exist_ok=True)
    figs: list[Path] = []

    ok = items.dropna(subset=["total"])
    if not ok.empty:
        wide = ok.pivot_table(index="item_id", columns="model", values="total", aggfunc="first").reindex(columns=MODELS)
        wide = wide.reindex(sorted(wide.index, key=natural_key))

        # 图 1：每题总分对比
        fig, ax = plt.subplots(figsize=(10, 4.5))
        x = range(len(wide))
        w = 0.38
        for i, m in enumerate(MODELS):
            ax.bar([v + (i - 0.5) * w for v in x], wide[m], w, label=MODEL_LABEL[m])
        ax.set_xticks(list(x))
        ax.set_xticklabels(wide.index, fontsize=9)
        ax.set_ylim(0, 10.5)
        ax.set_ylabel("总分")
        ax.set_title("每题得分对比")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        p = OUT / "fig1_items.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        figs.append(p)

        # 图 2：题面类型 × 平均分
        g = ok.groupby(["prompt_type", "model"])["total"].mean().unstack().reindex(columns=MODELS)
        if not g.empty:
            fig, ax = plt.subplots(figsize=(6, 4))
            g.plot(kind="bar", ax=ax, rot=0)
            ax.set_ylim(0, 10.5)
            ax.set_ylabel("平均分")
            ax.set_xlabel("题面类型（S/R/A/P）")
            ax.set_title("题面定义充分性 × 平均分")
            ax.legend([MODEL_LABEL[m] for m in g.columns])
            ax.grid(axis="y", alpha=0.3)
            p = OUT / "fig2_type.png"
            fig.tight_layout()
            fig.savefig(p, dpi=150)
            plt.close(fig)
            figs.append(p)

    # 图 3：五次采样稳定性
    if not runs.empty and not runs[RUN_COLS].isna().all().all():
        r = runs.copy()
        mean = r[RUN_COLS].mean(axis=1)
        lo = mean - r[RUN_COLS].min(axis=1)
        hi = r[RUN_COLS].max(axis=1) - mean
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.errorbar(
            range(len(r)), mean, yerr=[lo, hi], fmt="o", capsize=4, color="#2b6cb0"
        )
        ax.set_xticks(range(len(r)))
        ax.set_xticklabels(r["item_id"], fontsize=9)
        ax.set_ylim(0, 10.5)
        ax.set_ylabel("分数")
        ax.set_title("豆包五次采样：均值与极差")
        ax.grid(axis="y", alpha=0.3)
        p = OUT / "fig3_stability.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        figs.append(p)

    # 图 4：首次失效层级（堆叠）
    if "fail_layer" in items.columns and not items.empty:
        df = items.copy()
        df["fail_layer"] = df["fail_layer"].fillna("").astype(str).str.strip().str.upper()
        df.loc[df["fail_layer"] == "", "fail_layer"] = "未失效"
        ct = pd.crosstab(df["fail_layer"], df["model"]).reindex(columns=MODELS, fill_value=0)
        ct = ct.reindex([*LAYERS, "未失效"], fill_value=0)
        has_layers = df["fail_layer"].isin(LAYERS).any()
        if has_layers and int(ct.to_numpy().sum()) > 0:
            fig, ax = plt.subplots(figsize=(6, 4))
            bottom = None
            for layer in [*LAYERS, "未失效"]:
                vals = ct.loc[layer].to_numpy(dtype=float)
                ax.bar(
                    [MODEL_LABEL[m] for m in MODELS],
                    vals,
                    bottom=bottom,
                    label=LAYER_LABEL.get(layer, layer),
                )
                bottom = vals if bottom is None else bottom + vals
            ax.set_ylabel("题数")
            ax.set_title("首次失效层级分布")
            ax.legend(fontsize=8)
            ax.grid(axis="y", alpha=0.3)
            p = OUT / "fig4_layers.png"
            fig.tight_layout()
            fig.savefig(p, dpi=150)
            plt.close(fig)
            figs.append(p)

    return figs


# ---------------------------------------------------------------- 主流程
def build_report(items: pd.DataFrame, runs: pd.DataFrame) -> str:
    parts = ["# 汇总分析\n"]

    if not has_data(items):
        parts.append("> 数据为空。请在 `data/items.csv` 填入分数后重新运行。\n")
        parts.append("先跑 `python analyze.py --demo` 看输出长什么样。\n")
    else:
        parts.append("## 1. 总体\n")
        parts.append(md_table(table4_overall(items)) + "\n")

        parts.append("## 2. 每题得分\n")
        parts.append(md_table(table1_by_item(items)) + "\n")

        parts.append("## 3. 错误标签频次\n")
        parts.append(md_table(table2_error_tags(items)) + "\n")

        parts.append("## 4. 题面定义充分性 × 平均分\n")
        parts.append(md_table(table3_by_type(items)) + "\n")

        parts.append("## 5. 豆包五次采样稳定性\n")
        parts.append(md_table(table5_stability(runs)) + "\n")

        parts.append("## 6. 首次失效层级\n")
        parts.append(md_table(table6_layers(items)) + "\n")

        parts.append("## 7. 缺失必要步骤（对满分答案也有效）\n")
        parts.append(md_table(table7_missing(items)) + "\n")

        parts.append("## 8. 结论草稿（自己改）\n")
        parts.append("- 主要发现 1：\n- 主要发现 2：\n- 有效性限制：\n")

    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="用合成数据预览")
    args = ap.parse_args()

    items = load_items(args.demo)
    runs = load_runs(args.demo)

    OUT.mkdir(exist_ok=True)
    report = build_report(items, runs)
    name = "demo_analysis.md" if args.demo else "analysis.md"
    (OUT / name).write_text(report, encoding="utf-8")

    figs = make_figures(items, runs)
    print(f"report : output/{name}")
    print(f"filled : {int(items['total'].notna().sum())} rows with scores")
    for f in figs:
        print(f"figure : output/{f.name}")


if __name__ == "__main__":
    main()
