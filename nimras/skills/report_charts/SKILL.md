---
name: report-charts
description: Use when the user asks for charts, graphs or a dashboard for a report, wants a new chart to match their earlier ones, or wants an old chart rebuilt or updated with new data.
---

# Report charts

Make charts for reports that look like one consistent set: bar/column, line/trend, pie/donut, and multi-chart dashboards. Covers three jobs: making new charts, matching the style of earlier charts, and rebuilding or updating an old chart with new data.

## 1. Work out which job this is

- **New chart(s) from data**: the user gives data (pasted, a file, or a connected source) and wants charts.
- **Match an earlier chart**: the user attaches or points to a previous chart. Read it first and copy its style: colors, fonts, title wording, axis and legend placement, number formats, proportions. Write those into a style JSON for the script (section 7).
- **Rebuild or update**: the user has an old chart and new data. Keep everything about the chart the same except the data, and say what changed in the numbers. Reuse the old spec and style files if they exist.

If an earlier chart is mentioned but not attached or reachable, ask for it once (image, file or the code behind it). If it can't be supplied, use the house style below and say so in one line.

## 2. Get the data right before drawing

- Load the data into a file and compute with code; never estimate values by eye.
- Check for missing values, mixed units, duplicate rows and totals that don't add up. Report anything odd in one line instead of silently fixing it. The script prints these as WARNING lines.
- Never invent or fill in numbers. If data is missing for a chart, leave it out and say so.

## 3. Pick the chart form

| What the report needs to show | Use |
|---|---|
| Comparison across categories | Bar / column (horizontal bars when labels are long or there are more than about 8 categories) |
| Change over time | Line (column if 6 or fewer periods) |
| Share of a whole, 5 or fewer parts | Pie / donut |
| Share of a whole, more than 5 parts | Sorted bar; group small parts into "Other" |
| Several of these together | Dashboard |

Sort bars by value unless the categories have a natural order (months, stages). Start bar axes at zero.

## 4. House style (used unless an earlier chart sets a different one)

- Title states the finding, not just the topic ("Sales rose 18% in Q3", not "Sales by quarter"). Check the finding against the data before using it as a title. Subtitle gives the unit and period.
- One accent color for the series that matters, neutral grey for the rest; at most 6 colors in one chart. Keep the same color for the same category across every chart in a report.
- Label values directly on the marks where there is room; drop the legend when direct labels do the job.
- Light horizontal gridlines only, no chart border, no 3D, no shadows, no gradient fills.
- Consistent number format across the report (thousands separators, same decimal places, currency or % shown once in the axis title or subtitle).
- Readable text sizes; do not rotate axis labels, switch to horizontal bars instead.
- Add a short source line under each chart (data source and date).

Once a style is settled in a conversation (from an earlier chart or the user's corrections), keep it for every later chart in that conversation.

## 5. Dashboards

- Top row: 3 to 5 headline numbers (value, and change versus the previous period).
- Then the main trend chart at full width, then supporting comparison and share charts in a grid.
- Same palette, fonts and number formats in every panel; one title for the whole dashboard and a short title per panel.
- Limit to what fits one screen or page; move the rest to a second page.

## 6. Deliver

- No format stated: show the chart in the chat for a quick look; for something the user will keep or share, make it a dashboard or page they can open and share.
- Format stated (PNG, Excel, PowerPoint, PDF, Word): deliver in that format. For Excel, build native charts tied to the data sheet so they update when numbers change. The script's PNGs can be placed into PowerPoint, Word or PDF outputs.
- With each chart, add one or two sentences on the main takeaway. Do not restate every data point.

## 7. The script: scripts/make_charts.py

Use it for PNG charts and dashboards in the house style. It needs Python 3 with pandas, matplotlib and openpyxl (`pip install pandas matplotlib openpyxl`).

```
python scripts/make_charts.py --example-spec  > spec.json    # starter spec
python scripts/make_charts.py --example-style > style.json   # default style to edit
python scripts/make_charts.py --data data.csv --spec spec.json [--style style.json] [--sheet Name] --out charts/
```

- `--data`: CSV or Excel file. Rows are grouped by the chart's `x` column and summed by default (`"agg": "sum" | "mean" | "count" | "none"`).
- `--spec`: JSON listing the charts. Types: `bar`/`column`, `line`, `pie`/`donut`, `dashboard`. Useful keys: `title`, `subtitle`, `highlight` (the one category or series to colour with the accent), `horizontal`, `sort`, `max_slices`, `number_format` (`plain`, `thousands`, `currency`, `percent`), `file`. Dashboards take `kpis` (`column`, `agg` or `divide_by`, `format`, optional `change` in %) and `panels` (chart specs).
- `--style`: JSON overriding any house style key (`accent`, `neutral`, `palette`, `font`, sizes, `currency_symbol`, `decimals`, `dpi`). To match an earlier chart, set these from what the earlier chart shows and save the file so later updates reuse it.
- Prints each output path, and WARNING lines for missing columns, missing values and duplicate rows.

See `examples/` for sample data, a spec, a style file and the dashboard it produces.

## 8. Check before handing over

- Open or render the result and look at it: no overlapping labels, no cut-off text, colors distinguishable, legend matches the series.
- Re-check totals and percentages against the source data (pie shares sum to 100%), and check that each title's claim is true for the data.
- For an update, confirm that only the data changed and the style still matches the original.
