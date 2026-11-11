"""把过程指标（fail_layer / missing_steps）写入 items.csv。

来源：逐题核对文档 L/M 节标注的「首个关键错误/可改进点/遗漏」。
层级：L0 定义 / L1 构造 / L2 推理 / L3 边界与严谨；无首错填空字符串。
first_fail 因各题 rubric 结构不统一，跨题不可比，留空。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "data"
CSV = OUT / "items.csv"

# (item_id, model) -> (fail_layer, missing_steps)
METRICS = {
    ("Q1", "gpt"): ("L3", 2),
    ("Q1", "doubao"): ("L3", 2),
    ("Q2", "gpt"): ("L0", 1),
    ("Q2", "doubao"): ("L2", 1),
    ("Q3", "gpt"): ("L3", 1),
    ("Q3", "doubao"): ("L0", 1),
    ("Q4", "gpt"): ("L3", 1),
    ("Q4", "doubao"): ("L3", 2),
    ("Q5", "gpt"): ("L2", 1),
    ("Q5", "doubao"): ("L2", 2),
    ("Q6", "gpt"): ("", 0),
    ("Q6", "doubao"): ("L2", 1),
    ("Q7", "gpt"): ("L0", 1),
    ("Q7", "doubao"): ("L0", 2),
    ("Q8", "gpt"): ("L0", 2),
    ("Q8", "doubao"): ("L0", 1),
    ("Q9", "gpt"): ("", 0),
    ("Q9", "doubao"): ("L0", 1),
    ("Q10", "gpt"): ("L0", 1),
    ("Q10", "doubao"): ("L0", 1),
    ("Q11", "gpt"): ("", 0),
    ("Q11", "doubao"): ("L0", 2),
    ("Q12", "gpt"): ("", 0),
    ("Q12", "doubao"): ("L2", 3),
}

# 豆包过程指标取自哪一次（最佳那次）
BEST_RUN = {
    "Q1": 5, "Q2": 2, "Q3": 1, "Q4": 1, "Q5": 4, "Q6": 4,
    "Q7": 4, "Q8": 2, "Q9": 2, "Q10": 1, "Q11": 5, "Q12": 1,
}


def main() -> None:
    df = pd.read_csv(CSV, dtype=str).fillna("")
    for (qid, model), (layer, steps) in METRICS.items():
        mask = (df["item_id"] == qid) & (df["model"] == model)
        df.loc[mask, "fail_layer"] = layer
        df.loc[mask, "missing_steps"] = str(steps)
        if model == "doubao":
            df.loc[mask, "note"] = f"五次均值；过程指标取最佳第 {BEST_RUN[qid]} 次"
    df.to_csv(CSV, index=False, encoding="utf-8-sig")
    print(f"written: {CSV}")
    print(f"rows with fail_layer filled: {int((df['fail_layer'] != '').sum())}")
    print(f"rows with missing_steps>0: {int((pd.to_numeric(df['missing_steps'], errors='coerce') > 0).sum())}")


if __name__ == "__main__":
    main()
