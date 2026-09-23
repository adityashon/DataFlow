# DataFlow

**Turn any spreadsheet into a full analytics dashboard — charts, KPIs, a data-quality audit, and a plain-English report — in the time it takes to upload it.**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.2+-092E20?logo=django&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)
![D3.js](https://img.shields.io/badge/D3.js-7-F9A03C?logo=d3.js&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

No SQL, no spreadsheet formulas, no manually building charts. Drop in a
CSV or Excel file and get a dashboard back.

---

## Table of Contents

- [What it does](#what-it-does)
- [Who this is for](#who-this-is-for)
- [What makes the analysis smart, not generic](#what-makes-the-analysis-smart-instead-of-generic)
- [Features](#features-at-a-glance)
- [Architecture](#how-its-built)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Using it](#using-it)
- [Notes & limitations](#notes--limitations)
- [Contributing](#contributing)
- [License](#license)

---

## What it does

Upload a file and DataFlow will:

1. **Clean it automatically** — missing values, duplicate rows, and
   inconsistent types are detected and handled before analysis, with every
   step logged so nothing happens silently.
2. **Understand each column on its own terms** — it tells numbers apart
   from categories, dates, booleans, and identifiers (like an `order_id`
   or a customer name), and treats each one appropriately instead of
   trying to chart everything indiscriminately.
3. **Generate the charts that column actually deserves** — a histogram for
   a numeric spread, a donut for a 4-category field, a pareto chart for a
   30-category one, a real time-series line for a date column. One
   well-chosen chart per column, not four redundant ones stacked on top
   of each other.
4. **Explain itself** — every chart carries a one-sentence, plain-English
   summary (*"Revenue and Profit show a very strong positive relationship,
   r=0.94"*) that appears on hover, so you don't have to be a data analyst
   to read the room.
5. **Write you a report** — a structured, skimmable summary with
   highlighted figures, collapsible sections, and a one-click copy button,
   instead of a wall of numbers you have to interpret yourself.
6. **Look different every time** — the dashboard's visual theme is picked
   at random from five distinct SaaS-inspired styles (light and dark,
   different accent colors and layouts) on each upload, so the tool
   doesn't produce a stale, identical-looking dashboard twice in a row.
7. **Travel with you** — export the whole dashboard as a single,
   self-contained HTML file. No server, no login, no internet connection
   required to open it later — charts, styling, and data are all baked in.

## Who this is for

- **Anyone who gets handed a spreadsheet and needs to understand it fast**
  — a sales report, a survey export, a log of customer records — without
  opening Excel and building pivot tables by hand.
- **Analysts who want a first pass done for them** — automatic column
  classification and chart selection handles the repetitive setup work,
  leaving you to focus on what the data actually means.
- **Anyone who needs to share findings with someone non-technical** — the
  plain-language report and the standalone HTML export mean you can hand
  someone a single file and they'll understand what's in it without any
  explanation from you.

## What makes the analysis smart, instead of generic

Most auto-dashboard tools chart every column they're given, which means
you end up staring at a meaningless bar chart of customer IDs or a pie
chart where every slice is a different person's name. DataFlow doesn't do
that:

- Columns that are actually **identifiers** (sequential IDs, UUIDs, or
  columns where almost every value is unique) are automatically excluded
  from charts and KPIs — and you're told *why*, not left wondering where
  a column went.
- Categorical columns get **one** chart type, chosen by how many distinct
  values they have — not the same data plotted four redundant ways.
- Every chart's insight sentence is generated from the same statistics
  the chart is drawn from, so the summary you read always matches what
  you're looking at.

## Features at a glance

| Area | What you get |
|---|---|
| **Data ingestion** | CSV and Excel upload, automatic cleaning (missing values, duplicates, type coercion) with a visible cleaning report |
| **Column intelligence** | Automatic detection of numeric, categorical, boolean, datetime, and identifier columns, each handled appropriately |
| **Charts** | 15 chart types (histogram, bar, donut, scatter, bubble, line, area, heatmap, box plot, grouped box/bar, stacked bar, treemap, pareto, missing-value audit), auto-selected per column |
| **KPIs** | Auto-generated key metrics with icons, color coding, and animated count-up numbers; percentage-based metrics get a mini progress bar; scrolls horizontally with snap |
| **Data Quality** | A radial quality-score gauge plus a specific list of flagged issues (missing data, outliers, duplicates) |
| **Reports** | A structured, interactive report with collapsible sections, highlighted key figures, and a copy-to-clipboard button |
| **Hover insights** | Every chart explains itself in plain language via an info icon — hover it, read the takeaway, move on |
| **Search** | Live filtering of KPIs and charts by keyword, right from the top bar |
| **Themes** | Five distinct visual styles, randomly assigned per upload — light and dark, different sidebar layouts and accent colors |
| **Export** | One-click download of the entire dashboard as a single offline-ready HTML file, identical to what's on screen |



- **FastAPI** does the actual data work: reading the uploaded file,
  cleaning it, profiling every column, and generating the charts, KPIs,
  and quality report. It's a stateless, single-purpose service — it
  receives a file, returns structured JSON.
- **Django** is the user-facing side: it serves the upload form, calls
  FastAPI, stores the result in the session, and renders the dashboard.
  It also owns the randomized theme selection and the standalone-export
  logic.
- **D3.js**, loaded from a CDN, draws every chart directly in the
  browser from the JSON FastAPI produced — no build step, no bundler.

## Project structure

```
Visual/
├── manage.py                          # Django entry point
├── requirements.txt
├── config/                            # Django project settings & routing
│   ├── settings.py
│   └── urls.py
├── core/                              # Django app — the user-facing side
│   ├── views.py                       # upload / dashboard / download logic
│   ├── urls.py
│   └── templates/core/
│       ├── index.html                 # upload form
│       └── dashboard.html             # the dashboard itself (all 5 themes, all charts, reports)
└── fastapi_service/                   # FastAPI microservice — the data work
    ├── main.py                        # FastAPI app entry point
    ├── routers/process.py             # /api/process/ endpoint
    └── services/
        ├── ingest.py                  # file reading (CSV/Excel)
        ├── clean.py                   # missing values, duplicates, type fixes
        └── analytics.py               # column profiling, chart generation, KPIs, quality audit
```

## Getting started

**Requirements:** Python 3.10+

```bash
# 1. Clone the repo
git clone https://github.com/adityashon/DataFlow.git
cd DataFlow/Visual

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the FastAPI service (handles the actual data processing)
uvicorn fastapi_service.main:app --port 8001

# 4. In a second terminal, start the Django server (handles the UI)
python manage.py runserver 8000
```

Then open **http://127.0.0.1:8000** and upload a file.

> FastAPI's interactive API docs are available at `http://127.0.0.1:8001/docs`
> if you want to inspect or call the processing endpoint directly.

## Using it

1. **Upload** a CSV or Excel file from the home page.
2. You're taken straight to the **Dashboard** — KPIs across the top,
   a data-quality gauge, and every auto-generated chart below it. Hover
   the "i" on any chart for a plain-language explanation of what it shows.
3. Switch to **Data Sources** to see exactly what was cleaned, which
   columns were excluded from the analysis (and why), and a preview of
   the underlying data.
4. Switch to **Reports** for a structured written summary you can expand,
   collapse, and copy to share with someone else.
5. Click **Export** to download the whole thing as a single HTML file —
   open it later, on any machine, with no server running.

## Notes & limitations

- This is a **single-user, local-first** tool by design — there's no
  login system, and uploaded data lives only in your browser session
  (or in the exported file, once you download it).
- Column classification is intentionally conservative: if DataFlow can't
  confidently say a column is a meaningful category or measurement, it
  excludes it rather than guessing and showing you a misleading chart.
- It's a two-process app (Django + FastAPI) rather than a single
  serverless function, so it's built for a normal server/host rather than
  a static or edge-function deployment target.

## Contributing

Issues and pull requests are welcome. If you're proposing a larger change
(a new chart type, a new theme, a different cleaning strategy), open an
issue first so it can be discussed before you put the work in.

## License

[MIT](LICENSE)
