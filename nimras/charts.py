"""Charts for data reports, following the report-charts skill.

The skill's rules (nimras/skills/report_charts/SKILL.md) are applied in code: code picks the
chart types, computes every number and writes the finding-style titles, so the language model
never does arithmetic. Drawing uses the skill's own make_charts.py in its house style.
"""
import io
import json
import math
import re
import threading
import time
import uuid
from pathlib import PurePath

from . import config

TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MEASURE_HINTS = ("sales", "revenue", "amount", "total", "value", "profit", "income", "turnover",
                 "cost", "spend", "expense", "price")
TARGET_HINTS = ("target", "budget", "plan", "goal", "forecast", "quota")
COUNT_HINTS = ("orders", "units", "quantity", "qty", "count", "customers", "transactions", "visits")
TIME_WORDS = {"month", "date", "year", "quarter", "week", "day", "period", "time"}
ID_WORDS = {"id", "code", "zip", "postcode", "phone", "no", "number"}
MAX_BARS = 15

_DRAW_LOCK = threading.Lock()  # matplotlib's pyplot is not thread-safe


class DataError(ValueError):
    pass


def is_table(filename: str) -> bool:
    return PurePath(filename).suffix.lower() in TABLE_EXTENSIONS


def fmt(v) -> str:
    """Exact number with thousands separators (no rounding of whole numbers)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}"


def _words(name: str) -> set[str]:
    return set(re.findall(r"[a-z]+", str(name).lower()))


def _has(name: str, hints) -> bool:
    low = str(name).lower()
    return any(h in low for h in hints)


# ----------------------------------------------------------------------------- load
def load_table(filename: str, data: bytes):
    """Read a CSV/TSV/Excel file into a DataFrame, turning '1,234'-style text into numbers."""
    try:
        import pandas as pd
    except ImportError:
        raise DataError("Reading data files needs pandas: pip install pandas openpyxl")
    ext = PurePath(filename).suffix.lower()
    try:
        if ext in (".xlsx", ".xlsm", ".xls"):
            df = pd.read_excel(io.BytesIO(data))
        else:
            df = pd.read_csv(io.BytesIO(data), sep="\t" if ext == ".tsv" else None, engine="python")
    except Exception as e:
        raise DataError(f"Couldn't read the table: {e}")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object and df[c].notna().any():
            cleaned = df[c].astype(str).str.replace(r"[,\s$€£₹%]|^(Rs\.?|LKR|USD)", "", regex=True)
            num = pd.to_numeric(cleaned, errors="coerce")
            if num.notna().sum() >= 0.9 * df[c].notna().sum():
                df[c] = num
    if df.empty:
        raise DataError("The table is empty.")
    return df


# -------------------------------------------------------------------------- analyse
def _time_column(df):
    """Find the column that orders the data in time. Returns (column, sort_key or None, df)."""
    import pandas as pd

    def month_key(s):
        vals = s.dropna().astype(str).str.strip().str[:3].str.lower()
        if len(vals) and vals.isin(MONTHS).mean() >= 0.9:
            return s.astype(str).str.strip().str[:3].str.lower().map(lambda m: MONTHS.index(m) if m in MONTHS else 99)
        return None

    def parse_dates(s):
        if pd.api.types.is_numeric_dtype(s):
            return None
        try:
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            return None
        return parsed if parsed.notna().mean() >= 0.9 else None

    candidates = [c for c in df.columns if _words(c) & TIME_WORDS] + \
                 [c for c in df.columns if not (_words(c) & TIME_WORDS)]
    for c in candidates:
        s = df[c]
        hinted = bool(_words(c) & TIME_WORDS)
        if s.dtype == object and (key := month_key(s)) is not None:
            return c, key, df
        if hinted and pd.api.types.is_numeric_dtype(s):  # e.g. Year
            return c, s, df
        parsed = parse_dates(s) if (hinted or s.dtype == object) else None
        if parsed is not None and s.nunique() > 2:
            if s.nunique() > 24:  # many dates: group by month
                label = f"{c} (month)"
                df = df.assign(**{label: parsed.dt.to_period("M").astype(str)})
                return label, parsed, df
            return c, parsed, df
        if hinted and s.dtype == object and 2 <= s.nunique() <= 60:  # e.g. Quarter "Q1": keep file order
            return c, None, df
    return None, None, df


def _is_id(df, c) -> bool:
    if _words(c) & ID_WORDS:
        return True
    s = df[c].dropna()
    return len(s) > 10 and s.is_unique and (s % 1 == 0).all() and s.is_monotonic_increasing


def analyse(df) -> dict:
    import pandas as pd
    time_col, key, df = _time_column(df)
    if key is not None:
        df = df.assign(__order=key.values).sort_values("__order", kind="stable").drop(columns="__order")
    measures = [c for c in df.columns if c != time_col and pd.api.types.is_numeric_dtype(df[c])
                and not pd.api.types.is_bool_dtype(df[c]) and not _is_id(df, c)]
    if not measures:
        raise DataError("No numeric columns to chart.")
    dims = [c for c in df.columns if c != time_col and c not in measures
            and not pd.api.types.is_numeric_dtype(df[c]) and 2 <= df[c].nunique() < max(3, len(df))]
    target = next((m for m in measures if _has(m, TARGET_HINTS)), None)
    count = next((m for m in measures if _has(m, COUNT_HINTS) and m != target), None)
    main = (next((m for m in measures if _has(m, MEASURE_HINTS) and m not in (target, count)), None)
            or next((m for m in measures if m not in (target, count)), None) or measures[0])
    if count == main:
        count = None
    return {"df": df, "time": time_col, "dims": dims[:3], "measures": measures,
            "main": main, "target": target, "count": count}


# ----------------------------------------------------------------------------- plan
def plan(df, filename: str) -> dict:
    """Choose charts per the skill's rules and compute every figure they show."""
    a = analyse(df)
    df, main, target, count, time_col = a["df"], a["main"], a["target"], a["count"], a["time"]
    charts, facts, warnings = [], [], []

    used = [c for c in [time_col, *a["dims"], main, target, count] if c]
    for c in dict.fromkeys(used):
        n = int(df[c].isna().sum())
        if n:
            warnings.append(f"'{c}' has {n} missing value(s); those rows are left out of charts using it.")
    dups = int(df.duplicated().sum())
    if dups:
        warnings.append(f"The data has {dups} fully duplicated row(s); check them before trusting totals.")

    totals = {m: float(df[m].sum()) for m in a["measures"]}
    big = max(abs(v) for v in totals.values()) >= 10_000
    number_format = "thousands" if big else "plain"
    facts.append("**Dataset:** {:,} rows. Columns: {}.".format(len(df), ", ".join(df.columns)))
    facts.append("| Measure | Total | Average per row |\n|---|---|---|\n" + "\n".join(
        f"| {m} | {fmt(totals[m])} | {fmt(float(df[m].mean()))} |" for m in a["measures"]))

    # Change over time -> line (column when 6 or fewer periods and no target)
    if time_col:
        ys = [main] + ([target] if target else [])
        g = df.groupby(time_col, sort=False)[ys].sum()
        periods = [str(p) for p in g.index]
        first, last = float(g[main].iloc[0]), float(g[main].iloc[-1])
        if target:
            hit = int((g[main] >= g[target]).sum())
            unit = time_col.lower() + "s" if time_col.lower() in ("month", "week", "day", "quarter", "year") \
                else "periods"
            title = f"{main} met or beat {target} in {hit} of {len(g)} {unit}"
        elif len(g) >= 2 and first:
            pct = (last - first) / abs(first) * 100
            title = f"{main} {'rose' if pct >= 0 else 'fell'} {abs(pct):.0f}% from {periods[0]} to {periods[-1]}"
        else:
            title = f"{main} by {time_col}"
        peak = str(g[main].idxmax())
        kind = "column" if (len(g) <= 6 and not target) else "line"
        charts.append({"type": kind, "x": time_col, "y": ys if target else main, "sort": False,
                       "highlight": main if target else None, "title": title,
                       "subtitle": f"{main}{' vs ' + target if target else ''} by {time_col}, "
                                   f"{periods[0]} to {periods[-1]}",
                       "takeaway": f"{title}. The highest {time_col.lower()} was {peak} "
                                   f"({fmt(float(g[main].max()))}).",
                       "file": "trend.png"})
        header = f"| {time_col} | " + " | ".join(ys) + " |\n|---|" + "---|" * len(ys)
        rows = "\n".join(f"| {p} | " + " | ".join(fmt(float(g.loc[i, y])) for y in ys) + " |"
                         for p, i in zip(periods, g.index))
        facts.append(f"**{main} by {time_col}:**\n\n{header}\n{rows}")

    # Comparison across categories -> bar; share of a whole with <=5 parts -> donut
    for i, d in enumerate(a["dims"]):
        g = df.groupby(d)[main].sum().sort_values(ascending=False)
        total = float(g.sum())
        top, top_v = str(g.index[0]), float(g.iloc[0])
        share = top_v / total * 100 if total else 0
        x = d
        if len(g) > MAX_BARS:  # group the long tail into "Other"
            x = f"__{i}"
            keep = set(g.index[: MAX_BARS - 1])
            df = df.assign(**{x: df[d].where(df[d].isin(keep), "Other")})
        donut = i > 0 and len(g) <= 5 and total > 0 and (g >= 0).all()
        if donut:
            title = f"{top} makes up {share:.0f}% of {main}"
            spec = {"type": "pie", "donut": True, "x": x, "y": main, "max_slices": 5}
        else:
            title = f"{top} had the highest {main}, {share:.0f}% of the total"
            spec = {"type": "bar", "x": x, "y": main, "highlight": top}
        charts.append({**spec, "title": title, "subtitle": f"Total {main} by {d}",
                       "takeaway": f"{title} ({fmt(top_v)} of {fmt(total)}).", "file": f"by_{i}.png"})
        rows = "\n".join(f"| {k} | {fmt(float(v))} | {v / total * 100 if total else 0:.1f}% |"
                         for k, v in g.items())
        facts.append(f"**{main} by {d}:**\n\n| {d} | {main} | Share |\n|---|---|---|\n{rows}")

    if not charts:  # no time or category columns: compare measure totals
        charts.append({"type": "bar", "x": "__measure", "y": "__total", "title": f"Totals by measure",
                       "subtitle": "Sum of each numeric column", "takeaway": "Totals of each numeric column.",
                       "file": "totals.png", "_data": [{"__measure": m, "__total": v} for m, v in totals.items()]})

    # Dashboard: headline numbers, main trend full width, the rest in a grid
    if len(charts) >= 2:
        kpis = [{"label": f"Total {main}", "column": main, "agg": "sum", "format": number_format}]
        if target:
            kpis.append({"label": f"Total {target}", "column": target, "agg": "sum", "format": number_format})
        if count:
            kpis.append({"label": f"Total {count}", "column": count, "agg": "sum", "format": number_format})
            kpis.append({"label": f"{main} per {count.rstrip('s')}", "column": main, "divide_by": count,
                         "format": "plain"})
        span = ""
        if time_col:
            span = f", {df[time_col].astype(str).iloc[0]} to {df[time_col].astype(str).iloc[-1]}"
        charts.insert(0, {"type": "dashboard", "title": f"{PurePath(filename).stem}: summary",
                          "subtitle": f"{len(df):,} rows{span}", "kpis": kpis[:4],
                          "panels": [{k: v for k, v in c.items() if k not in ("file", "takeaway", "subtitle")}
                                     for c in charts[:4]],
                          "takeaway": "Headline numbers and all charts together on one page.",
                          "file": "dashboard.png"})

    return {"df": df, "charts": charts, "facts": facts, "warnings": warnings,
            "number_format": number_format, "main": main,
            "source": f"Source: {filename}, analysed {time.strftime('%d %b %Y')}"}


# --------------------------------------------------------------------------- render
def render(p: dict) -> list[dict]:
    """Draw the planned charts with the skill's script. Returns [{title, takeaway, url}]."""
    try:
        import matplotlib.pyplot as plt
        from .skills.report_charts import make_charts as mc
    except ImportError:
        raise DataError("Drawing charts needs matplotlib: pip install matplotlib")
    import pandas as pd

    chart_id = uuid.uuid4().hex
    out_dir = config.DATA_DIR / "charts" / chart_id
    out_dir.mkdir(parents=True, exist_ok=True)
    style = dict(mc.DEFAULT_STYLE)
    custom = config.DATA_DIR / "chart_style.json"  # skill section 7: match earlier charts
    if custom.exists():
        style.update(json.loads(custom.read_text(encoding="utf-8")))
    style["palette"] = style["palette"][: mc.MAX_COLORS]
    ctx = {"color_map": {}, "source": p["source"], "number_format": p["number_format"]}

    out = []
    with _DRAW_LOCK:
        mc.apply_base_style(style)
        plt.rcParams["text.parse_math"] = False  # "$" in labels is text, not maths
        for c in p["charts"]:
            spec = {k: v for k, v in c.items() if k not in ("takeaway", "_data")}
            df = pd.DataFrame(c["_data"]) if "_data" in c else p["df"]
            try:
                path = mc.dashboard(df, spec, style, ctx, out_dir) if spec["type"] == "dashboard" \
                    else mc.single_chart(df, spec, style, ctx, out_dir)
            except Exception as e:  # one bad chart shouldn't sink the report
                print(f"Chart '{c.get('title')}' failed: {e}")
                plt.close("all")
                continue
            out.append({"title": c["title"], "takeaway": c["takeaway"],
                        "url": f"/charts/{chart_id}/{path.name}"})
    return out
