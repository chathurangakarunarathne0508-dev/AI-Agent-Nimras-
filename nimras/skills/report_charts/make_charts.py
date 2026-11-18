#!/usr/bin/env python3
"""
make_charts.py - report charts in one consistent house style.

Draws bar/column, line, pie/donut charts and multi-panel dashboards from a
CSV or Excel file, driven by a small JSON spec. A style JSON can override the
house style so new charts match earlier ones.

Usage
-----
  python make_charts.py --data sales.csv --spec spec.json --out charts/
  python make_charts.py --data sales.xlsx --sheet Q3 --spec spec.json --style my_style.json
  python make_charts.py --example-spec > spec.json        # print a starter spec
  python make_charts.py --example-style > style.json      # print the default style

Spec format (JSON)
------------------
{
  "charts": [
    {"type": "bar",  "x": "Region", "y": "Sales", "title": "...", "subtitle": "...",
     "highlight": "North", "horizontal": false, "sort": true, "file": "sales_by_region.png"},
    {"type": "line", "x": "Month", "y": ["Sales", "Target"], "title": "...", "highlight": "Sales"},
    {"type": "pie",  "x": "Channel", "y": "Revenue", "donut": true, "max_slices": 5},
    {"type": "dashboard", "title": "...", "kpis": [
        {"label": "Revenue", "column": "Revenue", "agg": "sum", "format": "currency", "change": 8.5},
        {"label": "Avg. order", "column": "Revenue", "divide_by": "Orders", "format": "currency"}],
     "panels": [ <chart specs as above, without "file"> ], "file": "dashboard.png"}
  ],
  "source": "Source: company sales system, Nov 2026",
  "number_format": "thousands"      # plain | thousands | currency | percent
}

Any chart may also carry "agg": "sum" | "mean" | "count" | "none" (default "sum")
to group rows by the x column before plotting.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

# --------------------------------------------------------------------------
# House style (the skill's defaults). Override any key with --style file.json
# --------------------------------------------------------------------------
DEFAULT_STYLE = {
    "font": "DejaVu Sans",
    "accent": "#2563EB",                 # the series that matters
    "neutral": "#B8BEC8",                # everything else
    "palette": ["#2563EB", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6", "#64748B"],
    "text": "#1F2937",
    "muted": "#6B7280",
    "grid": "#E5E7EB",
    "background": "#FFFFFF",
    "title_size": 15,
    "subtitle_size": 11,
    "label_size": 10,
    "source_size": 8.5,
    "figsize": [9, 5.2],
    "dashboard_figsize": [15, 9.5],
    "dpi": 200,
    "currency_symbol": "$",
    "decimals": 0,
}

MAX_COLORS = 6


# ----------------------------- formatting ---------------------------------
def fmt_number(v, kind, style):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    d = style["decimals"]
    if kind == "percent":
        return f"{v:.{max(d, 0)}f}%"
    if kind == "currency":
        return f"{style['currency_symbol']}{_short(v, d)}"
    if kind == "thousands":
        return _short(v, d)
    return f"{v:,.{d}f}"


def _short(v, d):
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:,.{max(d, 1)}f}{suf}"
    return f"{v:,.{d}f}"


def axis_formatter(kind, style):
    return mticker.FuncFormatter(lambda v, _p: fmt_number(v, kind, style))


# ----------------------------- data ---------------------------------------
def load_data(path, sheet=None):
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(p, sheet_name=sheet or 0)
    return pd.read_csv(p)


def check_data(df, cols):
    """Return a list of plain-language warnings; never alters the data."""
    warnings = []
    for c in cols:
        if c not in df.columns:
            raise SystemExit(f"Column '{c}' not found. Available: {list(df.columns)}")
        n = df[c].isna().sum()
        if n:
            warnings.append(f"'{c}' has {n} missing value(s); those rows are left out.")
    dups = df.duplicated().sum()
    if dups:
        warnings.append(f"Data has {dups} fully duplicated row(s); check before trusting totals.")
    return warnings


def prepare(df, x, ys, agg):
    data = df[[x] + ys].dropna()
    if agg and agg != "none":
        data = data.groupby(x, sort=False, as_index=False).agg({y: agg for y in ys})
    return data


# ----------------------------- drawing helpers -----------------------------
def apply_base_style(style):
    plt.rcParams.update({
        "font.family": style["font"],
        "text.color": style["text"],
        "axes.labelcolor": style["muted"],
        "xtick.color": style["muted"],
        "ytick.color": style["muted"],
        "axes.edgecolor": style["grid"],
        "figure.facecolor": style["background"],
        "axes.facecolor": style["background"],
        "font.size": style["label_size"],
    })


def clean_axes(ax, style, horizontal=False):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(style["grid"])
    if horizontal:
        ax.xaxis.grid(True, color=style["grid"], linewidth=0.8)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(True)
        ax.spines["left"].set_color(style["grid"])
    else:
        ax.yaxis.grid(True, color=style["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def titles(ax, spec, style, panel=False):
    title = spec.get("title", "")
    sub = spec.get("subtitle", "")
    size = style["title_size"] - (3 if panel else 0)
    ax.set_title(title, loc="left", fontsize=size, fontweight="bold",
                 color=style["text"], pad=24 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=style["subtitle_size"] - (1 if panel else 0),
                color=style["muted"], va="bottom")


def colors_for(labels, highlight, style, color_map):
    """Accent for the highlighted label, neutral for the rest; otherwise a
    consistent category->color map shared across the whole report."""
    if highlight is not None:
        return [style["accent"] if str(l) == str(highlight) else style["neutral"] for l in labels]
    out = []
    for l in labels:
        key = str(l)
        if key not in color_map:
            color_map[key] = style["palette"][len(color_map) % len(style["palette"])]
        out.append(color_map[key])
    return out


# ----------------------------- chart types ---------------------------------
def draw_bar(ax, df, spec, style, ctx):
    x, y = spec["x"], spec["y"]
    data = prepare(df, x, [y], spec.get("agg", "sum"))
    if spec.get("sort", True):
        data = data.sort_values(y, ascending=False)
    labels = data[x].astype(str).tolist()
    values = data[y].tolist()
    long_labels = max((len(l) for l in labels), default=0) > 12 or len(labels) > 8
    horizontal = spec.get("horizontal", long_labels)
    cols = colors_for(labels, spec.get("highlight"), style, ctx["color_map"])
    kind = spec.get("number_format", ctx["number_format"])

    if horizontal:
        labels, values, cols = labels[::-1], values[::-1], cols[::-1]
        bars = ax.barh(labels, values, color=cols, height=0.65)
        ax.xaxis.set_major_formatter(axis_formatter(kind, style))
        ax.set_xlim(0, max(values + [0]) * 1.15 or 1)
    else:
        bars = ax.bar(labels, values, color=cols, width=0.65)
        ax.yaxis.set_major_formatter(axis_formatter(kind, style))
        ax.set_ylim(0, max(values + [0]) * 1.15 or 1)
    clean_axes(ax, style, horizontal)

    if spec.get("labels", True):
        for b, v in zip(bars, values):
            txt = fmt_number(v, kind, style)
            if horizontal:
                ax.text(b.get_width(), b.get_y() + b.get_height() / 2, " " + txt,
                        va="center", fontsize=style["label_size"] - 1, color=style["text"])
            else:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), txt,
                        ha="center", va="bottom", fontsize=style["label_size"] - 1, color=style["text"])
    return data


def draw_line(ax, df, spec, style, ctx):
    x = spec["x"]
    ys = spec["y"] if isinstance(spec["y"], list) else [spec["y"]]
    data = prepare(df, x, ys, spec.get("agg", "sum"))
    kind = spec.get("number_format", ctx["number_format"])
    hl = spec.get("highlight")
    xs = data[x].astype(str).tolist()
    cols = colors_for(ys, hl if hl and len(ys) > 1 else None, style, ctx["color_map"])
    if len(ys) == 1 and not hl:
        cols = [style["accent"]]

    for y, c in zip(ys, cols):
        lw = 2.8 if (hl is None or y == hl) else 1.8
        ax.plot(xs, data[y], color=c, linewidth=lw, marker="o", markersize=3.5)
        # direct label at line end instead of a legend
        ax.annotate(f" {y}  {fmt_number(data[y].iloc[-1], kind, style)}",
                    (len(xs) - 1, data[y].iloc[-1]), color=c,
                    fontsize=style["label_size"] - 1, fontweight="bold", va="center")
    ax.yaxis.set_major_formatter(axis_formatter(kind, style))
    if spec.get("zero_base", False):
        ax.set_ylim(bottom=0)
    ax.set_xlim(-0.3, len(xs) - 1 + max(0.8, len(xs) * 0.18))
    step = max(1, math.ceil(len(xs) / 12))
    ax.set_xticks(range(0, len(xs), step))
    ax.set_xticklabels(xs[::step])
    clean_axes(ax, style)
    return data


def draw_pie(ax, df, spec, style, ctx):
    x, y = spec["x"], spec["y"]
    data = prepare(df, x, [y], spec.get("agg", "sum")).sort_values(y, ascending=False)
    max_slices = spec.get("max_slices", 5)
    if len(data) > max_slices:
        top = data.iloc[: max_slices - 1]
        other = pd.DataFrame({x: ["Other"], y: [data.iloc[max_slices - 1:][y].sum()]})
        data = pd.concat([top, other], ignore_index=True)
    labels = data[x].astype(str).tolist()
    values = data[y].tolist()
    total = sum(values)
    cols = colors_for(labels, spec.get("highlight"), style, ctx["color_map"])
    width = 0.38 if spec.get("donut", True) else 1
    wedges, _ = ax.pie(values, colors=cols, startangle=90, counterclock=False,
                       wedgeprops={"width": width, "edgecolor": style["background"], "linewidth": 2})
    for w, lab, v in zip(wedges, labels, values):
        ang = math.radians((w.theta1 + w.theta2) / 2)
        r = 1.18
        ax.text(r * math.cos(ang), r * math.sin(ang), f"{lab}\n{v / total * 100:.0f}%",
                ha="center", va="center", fontsize=style["label_size"] - 1, color=style["text"])
    if spec.get("donut", True):
        kind = spec.get("number_format", ctx["number_format"])
        ax.text(0, 0, fmt_number(total, kind, style), ha="center", va="center",
                fontsize=style["title_size"], fontweight="bold", color=style["text"])
    ax.set_aspect("equal")
    return data


DRAW = {"bar": draw_bar, "column": draw_bar, "line": draw_line, "pie": draw_pie, "donut": draw_pie}


def add_source(fig, text, style):
    if text:
        fig.text(0.01, 0.01, text, fontsize=style["source_size"], color=style["muted"], ha="left", va="bottom")


# ----------------------------- outputs -------------------------------------
def single_chart(df, spec, style, ctx, out_dir):
    fig, ax = plt.subplots(figsize=style["figsize"])
    if spec["type"] == "donut":
        spec = {**spec, "donut": True}
    DRAW[spec["type"]](ax, df, spec, style, ctx)
    titles(ax, spec, style)
    add_source(fig, spec.get("source", ctx["source"]), style)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    name = spec.get("file") or f"{spec['type']}_{_slug(spec.get('title', 'chart'))}.png"
    path = out_dir / name
    fig.savefig(path, dpi=style["dpi"], bbox_inches="tight")
    plt.close(fig)
    return path


def kpi_value(df, k):
    col, agg = k["column"], k.get("agg", "sum")
    if k.get("divide_by"):
        den = df[k["divide_by"]].sum()
        return df[col].sum() / den if den else None
    s = df[col].dropna()
    return {"sum": s.sum(), "mean": s.mean(), "count": s.count(), "max": s.max(), "min": s.min(), "last": s.iloc[-1] if len(s) else None}[agg]


def dashboard(df, spec, style, ctx, out_dir):
    kpis = spec.get("kpis", [])[:5]
    panels = spec.get("panels", [])
    if not panels:
        raise SystemExit("Dashboard needs at least one panel.")
    fig = plt.figure(figsize=style["dashboard_figsize"])
    rows_panels = 1 + math.ceil((len(panels) - 1) / 2)       # first panel full width
    heights = ([0.55] if kpis else []) + [1.6] + [1.3] * (rows_panels - 1)
    gs = fig.add_gridspec(len(heights), 2, height_ratios=heights, hspace=0.75, wspace=0.25, top=0.9)
    r = 0

    fig.text(0.01, 0.995, spec.get("title", "Dashboard"), ha="left", va="top", fontsize=style["title_size"] + 4,
             fontweight="bold", color=style["text"])
    if spec.get("subtitle"):
        fig.text(0.01, 0.955, spec["subtitle"], va="top", fontsize=style["subtitle_size"] + 1, color=style["muted"])

    if kpis:
        sub = gs[r, :].subgridspec(1, len(kpis), wspace=0.15)
        for i, k in enumerate(kpis):
            ax = fig.add_subplot(sub[0, i])
            ax.axis("off")
            ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color="#F3F4F6", zorder=0))
            v = kpi_value(df, k)
            ax.text(0.06, 0.68, k["label"], transform=ax.transAxes, fontsize=style["label_size"],
                    color=style["muted"], va="center")
            ax.text(0.06, 0.3, fmt_number(v, k.get("format", ctx["number_format"]), style),
                    transform=ax.transAxes, fontsize=style["title_size"] + 6, fontweight="bold",
                    color=style["text"], va="center")
            if "change" in k:
                ch = k["change"]
                col = "#059669" if ch >= 0 else "#DC2626"
                ax.text(0.94, 0.3, f"{'▲' if ch >= 0 else '▼'} {abs(ch):.1f}%", transform=ax.transAxes,
                        ha="right", fontsize=style["label_size"] + 1, color=col, va="center")
        r += 1

    for i, p in enumerate(panels):
        if i == 0:
            ax = fig.add_subplot(gs[r, :])
        else:
            row = r + 1 + (i - 1) // 2
            colspan = slice(None) if (i == len(panels) - 1 and (i - 1) % 2 == 0) else (i - 1) % 2
            ax = fig.add_subplot(gs[row, colspan])
        if p["type"] == "donut":
            p = {**p, "donut": True}
        DRAW[p["type"]](ax, df, p, style, ctx)
        titles(ax, p, style, panel=True)

    add_source(fig, spec.get("source", ctx["source"]), style)
    name = spec.get("file") or f"dashboard_{_slug(spec.get('title', 'dashboard'))}.png"
    path = out_dir / name
    fig.savefig(path, dpi=style["dpi"], bbox_inches="tight")
    plt.close(fig)
    return path


def _slug(s):
    return "".join(c.lower() if c.isalnum() else "_" for c in s).strip("_")[:40] or "chart"


def cols_in(spec):
    if spec["type"] == "dashboard":
        out = [c for k in spec.get("kpis", []) for c in (k["column"], k.get("divide_by")) if c]
        for p in spec.get("panels", []):
            out += cols_in(p)
        return out
    ys = spec["y"] if isinstance(spec["y"], list) else [spec["y"]]
    return [spec["x"]] + ys


# ----------------------------- examples ------------------------------------
EXAMPLE_SPEC = {
    "source": "Source: sales system, exported Nov 2026",
    "number_format": "thousands",
    "charts": [
        {"type": "bar", "x": "Region", "y": "Sales", "highlight": "North",
         "title": "North led all regions in sales", "subtitle": "Total sales, Jan-Sep 2026"},
        {"type": "line", "x": "Month", "y": ["Sales", "Target"], "highlight": "Sales",
         "title": "Sales passed target from March", "subtitle": "Monthly sales vs target"},
        {"type": "pie", "x": "Channel", "y": "Sales", "donut": True,
         "title": "Online is half of all sales", "subtitle": "Share of sales by channel"},
        {"type": "dashboard", "title": "Sales report, Q1-Q3 2026", "subtitle": "All regions",
         "kpis": [{"label": "Total sales", "column": "Sales", "agg": "sum", "format": "currency", "change": 12.4},
                  {"label": "Orders", "column": "Orders", "agg": "sum", "format": "thousands", "change": -3.1},
                  {"label": "Avg. order value", "column": "Sales", "divide_by": "Orders", "format": "currency"}],
         "panels": [
             {"type": "line", "x": "Month", "y": ["Sales", "Target"], "highlight": "Sales",
              "title": "Monthly sales vs target"},
             {"type": "bar", "x": "Region", "y": "Sales", "highlight": "North", "title": "Sales by region"},
             {"type": "pie", "x": "Channel", "y": "Sales", "title": "Sales by channel"}]},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="Report charts in a consistent house style.")
    ap.add_argument("--data", help="CSV or Excel file")
    ap.add_argument("--sheet", help="Excel sheet name (default: first sheet)")
    ap.add_argument("--spec", help="JSON spec file listing the charts")
    ap.add_argument("--style", help="JSON file overriding house style keys (to match earlier charts)")
    ap.add_argument("--out", default="charts", help="Output folder (default: charts)")
    ap.add_argument("--example-spec", action="store_true", help="Print a starter spec and exit")
    ap.add_argument("--example-style", action="store_true", help="Print the default style and exit")
    a = ap.parse_args()

    if a.example_spec:
        print(json.dumps(EXAMPLE_SPEC, indent=2)); return
    if a.example_style:
        print(json.dumps(DEFAULT_STYLE, indent=2)); return
    if not (a.data and a.spec):
        ap.error("--data and --spec are required (or use --example-spec / --example-style)")

    style = dict(DEFAULT_STYLE)
    if a.style:
        style.update(json.loads(Path(a.style).read_text()))
    style["palette"] = style["palette"][:MAX_COLORS]
    apply_base_style(style)

    spec = json.loads(Path(a.spec).read_text())
    df = load_data(a.data, a.sheet)
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {"color_map": {}, "source": spec.get("source", ""),
           "number_format": spec.get("number_format", "plain")}

    warnings = []
    for c in spec["charts"]:
        warnings += check_data(df, list(dict.fromkeys(cols_in(c))))
    for w in dict.fromkeys(warnings):
        print("WARNING:", w, file=sys.stderr)

    for c in spec["charts"]:
        path = dashboard(df, c, style, ctx, out_dir) if c["type"] == "dashboard" \
            else single_chart(df, c, style, ctx, out_dir)
        print(path)


if __name__ == "__main__":
    main()
