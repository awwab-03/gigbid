"""Optional loader for the Kaggle Upwork datasets placed in data/raw/.

Real rows contribute job titles, budgets, hourly ranges, dates and countries. They are used
for the ~1,500 historical jobs behind the pricing statistics. Job text in the live stream and
the dev set is synthetic and built around the gold requirements (see docs/DATA_CARD.md).

The loader is tolerant of column-name differences between the shared datasets. If no CSV is
present it returns an empty list and the generator falls back to fully synthetic history.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

CATEGORY_KEYWORDS = {
    "ai_ml": ["machine learning", " ml ", "ai ", " ai", "llm", "chatbot", "gpt", "nlp", "computer vision",
              "deep learning", "rag", "openai", "langchain", "neural", "agent"],
    "data_science": ["data scien", "predictive", "forecast", "model", "statistic"],
    "data_analytics": ["dashboard", "power bi", "tableau", "excel", "sql", "analyst", "analytics", "looker",
                       "report", "data analysis", "bigquery", "spreadsheet"],
    "ecommerce": ["shopify", "woocommerce", "ecommerce", "e-commerce", "store", "amazon seller"],
    "web_dev": ["website", "web app", "react", "next.js", "nextjs", "node", "django", "frontend", "front-end",
                "backend", "back-end", "full stack", "full-stack", "api", "wordpress", "laravel", "vue"],
}

TITLE_COLS = ["title", "job_title", "Title", "Job Title", "name"]
BUDGET_COLS = ["budget", "Budget", "fixed_price", "price", "amount"]
HLOW_COLS = ["hourly_low", "Hourly Low", "min_hourly", "hourly_min"]
HHIGH_COLS = ["hourly_high", "Hourly High", "max_hourly", "hourly_max"]
DATE_COLS = ["published_date", "date", "posted_on", "created_at", "Date"]
COUNTRY_COLS = ["country", "Country", "client_country"]


def categorise(title: str) -> str:
    t = f" {title.lower()} "
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return "other"


def _pick(row: dict, cols: list[str]):
    for c in cols:
        if c in row and row[c] not in (None, "", "nan", "NaN"):
            return row[c]
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d,.]+", str(v))
    if not m:
        return None
    try:
        x = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return x if math.isfinite(x) and x > 0 else None


def load_kaggle_rows(raw_dir: Path, limit_per_file: int = 40000) -> list[dict]:
    rows: list[dict] = []
    if not raw_dir.exists():
        return rows
    for path in sorted(raw_dir.rglob("*.csv")):
        with path.open(encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for i, r in enumerate(reader):
                if i >= limit_per_file:
                    break
                title = _pick(r, TITLE_COLS)
                if not title:
                    continue
                budget = _num(_pick(r, BUDGET_COLS))
                hlo, hhi = _num(_pick(r, HLOW_COLS)), _num(_pick(r, HHIGH_COLS))
                if budget is None and hlo is None and hhi is None:
                    continue
                is_hourly = (hlo is not None or hhi is not None) and budget is None
                rows.append({
                    "title": str(title).strip()[:160],
                    "category": categorise(str(title)),
                    "budget": budget,
                    "hourly_low": hlo,
                    "hourly_high": hhi or hlo,
                    "is_hourly": bool(is_hourly),
                    "published_date": str(_pick(r, DATE_COLS) or "")[:10],
                    "country": _pick(r, COUNTRY_COLS) or "",
                    "source": f"kaggle:{path.name}",
                })
    return rows
