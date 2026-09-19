"""

fastapi_service/services/analytics.py

Universal Analytics Engine
──────────────────────────
Works on any pandas DataFrame regardless of column names, types, or domain.

Pipeline:
  1. DataProfiler   → inspect every column, classify type, compute stats
  2. KPIGenerator   → build meaningful KPI cards from the profile
  3. ChartSelector  → decide which charts are appropriate and build their data
  4. DataSampler    → produce a safe preview of raw rows
  5. QualityAuditor → score overall data quality

Public surface:
  generate_analytics(df: pd.DataFrame) -> dict
"""

from __future__ import annotations

import math
import re
import warnings
import logging
from collections import Counter
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# Enums & Constants
# ─────────────────────────────────────────────────────────────────────────────

class ColKind(Enum):
    NUMERIC_CONTINUOUS = auto()   # floats, high-range integers
    NUMERIC_DISCRETE   = auto()   # integers with few unique values
    CATEGORICAL        = auto()   # text / low-cardinality (≤50 unique)
    HIGH_CARDINALITY   = auto()   # text with many unique values (names, IDs)
    DATETIME           = auto()
    BOOLEAN            = auto()
    CONSTANT           = auto()   # single value — useless for charts
    ID_LIKE            = auto()   # sequential ints or uuid-like strings


# How many unique values before categorical becomes "high cardinality"
_CAT_THRESHOLD         = 50
# If more than this fraction of a text column's values are unique, it's
# behaving like an identifier (e.g. "name" in a small dataset) even if the
# raw unique count is small — charting it as a "category" is meaningless.
_HIGH_CARD_RATIO       = 0.6
# Column names that are near-certainly identifiers, regardless of their data
_ID_NAME_RE            = re.compile(r"^(id|uuid|guid|pk|key|index|row|rowid|row_id)$|(_id|_uuid|_guid|_key)$", re.I)
# Min fraction of non-null values required to include a column in charts
_MIN_COVERAGE          = 0.10
# Max rows we send to the frontend for scatter / preview
_SCATTER_LIMIT         = 600
_PREVIEW_ROWS          = 100
# Max bars in a bar / donut chart
_MAX_BARS              = 25
_MAX_DONUT_SLICES      = 10


# ─────────────────────────────────────────────────────────────────────────────
# Column profile dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name:            str
    kind:            ColKind
    dtype_str:       str
    total:           int
    non_null:        int
    null_count:      int
    null_pct:        float
    unique_count:    int
    coverage:        float          # non_null / total

    # Numeric-only
    mean:            Optional[float] = None
    median:          Optional[float] = None
    std:             Optional[float] = None
    min_val:         Optional[float] = None
    max_val:         Optional[float] = None
    q1:              Optional[float] = None
    q3:              Optional[float] = None
    iqr:             Optional[float] = None
    skewness:        Optional[float] = None
    kurtosis:        Optional[float] = None
    zeros:           Optional[int]   = None
    negatives:       Optional[int]   = None
    outlier_count:   Optional[int]   = None
    sum_val:         Optional[float] = None
    cv:              Optional[float] = None   # coefficient of variation

    # Categorical / boolean-only
    top_value:       Optional[str]  = None
    top_freq:        Optional[int]  = None
    top_freq_pct:    Optional[float] = None
    value_counts:    Optional[List[Dict]] = field(default_factory=list)

    # Datetime-only
    min_date:        Optional[str]  = None
    max_date:        Optional[str]  = None
    date_range_days: Optional[int]  = None

    # Set when a column is deliberately excluded from charts/KPIs
    # (identifier-like or too high-cardinality to mean anything as a "category")
    excluded_reason: Optional[str]  = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.name
        return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. DataProfiler
# ─────────────────────────────────────────────────────────────────────────────

class DataProfiler:
    """Inspects every column and returns a ColumnProfile."""

    def profile(self, df: pd.DataFrame) -> List[ColumnProfile]:
        profiles = []
        for col in df.columns:
            try:
                profiles.append(self._profile_column(df[col], col))
            except Exception:
                # A column that fails to profile should never silently
                # disappear from the dashboard — log it (visible in server
                # logs) and fall back to a minimal profile so it's still
                # counted in totals rather than vanishing without a trace.
                logging.getLogger(__name__).exception("Failed to profile column %r — falling back to CATEGORICAL", col)
                total    = len(df[col])
                non_null = int(df[col].notna().sum())
                profiles.append(ColumnProfile(
                    name=col, dtype_str=str(df[col].dtype), total=total, non_null=non_null,
                    null_count=total - non_null,
                    null_pct=round((total - non_null) / total * 100, 2) if total else 0.0,
                    unique_count=int(df[col].nunique(dropna=True)),
                    coverage=round(non_null / total, 4) if total else 0.0,
                    kind=ColKind.HIGH_CARDINALITY,
                    excluded_reason="Could not be analyzed automatically — excluded from charts",
                ))
        return profiles

    # ── Column dispatcher ────────────────────────────────────────────────────

    def _profile_column(self, series: pd.Series, name: str) -> ColumnProfile:
        total      = len(series)
        non_null   = int(series.notna().sum())
        null_count = total - non_null
        null_pct   = round(null_count / total * 100, 2) if total else 0.0
        unique     = int(series.nunique(dropna=True))
        coverage   = round(non_null / total, 4) if total else 0.0

        base = dict(
            name=name, dtype_str=str(series.dtype),
            total=total, non_null=non_null, null_count=null_count,
            null_pct=null_pct, unique_count=unique, coverage=coverage,
        )

        if unique <= 1:
            return ColumnProfile(**base, kind=ColKind.CONSTANT)

        if self._is_datetime(series):
            return self._profile_datetime(series.dropna(), **base)

        if self._is_boolean(series):
            return self._profile_categorical(series.dropna().astype(str), ColKind.BOOLEAN, **base)

        name_looks_like_id = bool(_ID_NAME_RE.search(str(name).strip()))
        uniq_ratio = unique / max(non_null, 1)

        if self._is_numeric(series):
            # A purely sequential integer column (1,2,3…) or one literally
            # named "id"/"customer_id" is an identifier, not a measurement —
            # charting its histogram/scatter/box is meaningless. Catch this
            # BEFORE the generic numeric path, not after it.
            if self._is_id_like(series) or (name_looks_like_id and uniq_ratio > 0.9):
                return ColumnProfile(**base, kind=ColKind.ID_LIKE,
                                      excluded_reason=f"'{name}' looks like a row identifier, not a measurement — excluded from charts")
            return self._profile_numeric(pd.to_numeric(series, errors="coerce").dropna(), **base)

        if self._is_id_like(series):
            return ColumnProfile(**base, kind=ColKind.ID_LIKE,
                                  excluded_reason="Identifier column (UUID pattern) — excluded from charts")

        # Text / object — decide CATEGORICAL vs HIGH_CARDINALITY.
        # A column can be "high cardinality" two ways: too many raw unique
        # values (_CAT_THRESHOLD), OR — the case that used to slip through —
        # almost every value is unique relative to row count (e.g. a "name"
        # column where 10/10 rows are distinct). Both make it meaningless
        # as a chart category, so both get excluded, with a stated reason.
        clean = series.dropna().astype(str)

        if name_looks_like_id and uniq_ratio > 0.4:
            kind, reason = ColKind.ID_LIKE, f"Column name '{name}' looks like an identifier — excluded from charts"
        elif uniq_ratio > _HIGH_CARD_RATIO and unique > 3:
            kind   = ColKind.HIGH_CARDINALITY
            reason = f"{round(uniq_ratio*100)}% of values are unique — not a meaningful category, excluded from charts"
        elif unique > _CAT_THRESHOLD:
            kind   = ColKind.HIGH_CARDINALITY
            reason = f"{unique} distinct values — too many categories to chart usefully"
        else:
            kind, reason = ColKind.CATEGORICAL, None

        profile = self._profile_categorical(clean, kind, **base)
        profile.excluded_reason = reason
        return profile

    # ── Numeric ──────────────────────────────────────────────────────────────

    def _profile_numeric(self, s: pd.Series, **base) -> ColumnProfile:
        if s.empty:
            return ColumnProfile(**base, kind=ColKind.NUMERIC_CONTINUOUS)

        q1, q3   = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr      = q3 - q1
        lower    = q1 - 1.5 * iqr
        upper    = q3 + 1.5 * iqr
        outliers = int(((s < lower) | (s > upper)).sum())
        mean     = float(s.mean())
        std      = float(s.std())

        kind = (
            ColKind.NUMERIC_DISCRETE
            if (pd.api.types.is_integer_dtype(s) and s.nunique() <= 30)
            else ColKind.NUMERIC_CONTINUOUS
        )

        return ColumnProfile(
            **base, kind=kind,
            mean      = round(mean, 4),
            median    = round(float(s.median()), 4),
            std       = round(std, 4),
            min_val   = round(float(s.min()), 4),
            max_val   = round(float(s.max()), 4),
            q1        = round(q1, 4),
            q3        = round(q3, 4),
            iqr       = round(iqr, 4),
            skewness  = round(float(s.skew()), 4),
            kurtosis  = round(float(s.kurtosis()), 4),
            zeros     = int((s == 0).sum()),
            negatives = int((s < 0).sum()),
            outlier_count = outliers,
            sum_val   = round(float(s.sum()), 4),
            cv        = round(std / abs(mean) * 100, 2) if mean != 0 else None,
        )

    # ── Categorical ───────────────────────────────────────────────────────────

    def _profile_categorical(self, s: pd.Series, kind: ColKind, **base) -> ColumnProfile:
        if s.empty:
            return ColumnProfile(**base, kind=kind)
        vc        = s.value_counts()
        top_val   = str(vc.index[0])
        top_freq  = int(vc.iloc[0])
        total_nn  = base["non_null"]
        top_pct   = round(top_freq / total_nn * 100, 2) if total_nn else 0.0
        vc_list   = [
            {"label": str(k), "value": int(v), "pct": round(v / total_nn * 100, 2)}
            for k, v in vc.head(_MAX_BARS).items()
        ]
        return ColumnProfile(
            **base, kind=kind,
            top_value=top_val, top_freq=top_freq,
            top_freq_pct=top_pct, value_counts=vc_list,
        )

    # ── Datetime ──────────────────────────────────────────────────────────────

    def _profile_datetime(self, s: pd.Series, **base) -> ColumnProfile:
        parsed = pd.to_datetime(s, errors="coerce").dropna()
        if parsed.empty:
            return ColumnProfile(**base, kind=ColKind.DATETIME)
        mn, mx  = parsed.min(), parsed.max()
        span    = (mx - mn).days
        return ColumnProfile(
            **base, kind=ColKind.DATETIME,
            min_date=str(mn)[:10], max_date=str(mx)[:10], date_range_days=span,
        )

    # ── Type detection helpers ────────────────────────────────────────────────

    @staticmethod
    def _is_numeric(s: pd.Series) -> bool:
        if pd.api.types.is_numeric_dtype(s):
            return True
        conv = pd.to_numeric(s.dropna(), errors="coerce")
        return conv.notna().sum() / max(len(s.dropna()), 1) >= 0.80

    @staticmethod
    def _is_datetime(s: pd.Series) -> bool:
        if pd.api.types.is_datetime64_any_dtype(s):
            return True
        # pandas' newer "str" dtype isn't object dtype, so check both —
        # this is the same pandas-3.0 gap fixed elsewhere in this codebase.
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            sample = s.dropna().head(50)
            parsed = pd.to_datetime(sample, errors="coerce")
            return parsed.notna().sum() / max(len(sample), 1) >= 0.80
        return False

    @staticmethod
    def _is_boolean(s: pd.Series) -> bool:
        if pd.api.types.is_bool_dtype(s):
            return True
        vals = set(str(v).strip().lower() for v in s.dropna().unique())
        return vals <= {"true","false","yes","no","1","0","t","f","y","n"}

    @staticmethod
    def _is_id_like(s: pd.Series) -> bool:
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            sample = s.dropna().astype(str).head(100)
            uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
            if sample.str.match(uuid_re).mean() > 0.8:
                return True
        if pd.api.types.is_integer_dtype(s):
            vals   = s.dropna()
            if len(vals) < 2:
                return False
            diffs  = vals.sort_values().diff().dropna()
            return bool((diffs == 1).mean() > 0.90)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. KPI Generator
# ─────────────────────────────────────────────────────────────────────────────

class KPIGenerator:
    """
    Generates KPI cards from column profiles.

    Rules:
      - Always: Total Rows, Total Columns, Missing Cells, Completeness %
      - Per numeric column (top 4 by uniqueness):   Sum, Mean, Min, Max, Outliers
      - Per categorical column (top 2):             Most Common, Unique Count
      - Per datetime column (first):                Date Range
      - Data Quality Score (composite)
    """

    def generate(self, df: pd.DataFrame, profiles: List[ColumnProfile]) -> List[Dict]:
        kpis = []

        # ── Always-present dataset KPIs ───────────────────────────────────────
        total_cells   = df.size
        missing_cells = int(df.isnull().sum().sum())
        completeness  = round((1 - missing_cells / max(total_cells, 1)) * 100, 1)
        dup_rows      = int(df.duplicated().sum())

        kpis += [
            self._kpi("Total Rows",    len(df),          "rows",   "blue",    "table"),
            self._kpi("Total Columns", len(df.columns),  "cols",   "purple",  "columns"),
            self._kpi("Completeness",  f"{completeness}%","",      "green" if completeness > 90 else "yellow", "check-circle"),
            self._kpi("Missing Cells", missing_cells,    "cells",  "red" if missing_cells > 0 else "green", "alert-triangle"),
        ]

        if dup_rows:
            kpis.append(self._kpi("Duplicate Rows", dup_rows, "rows", "orange", "copy"))

        # ── Numeric KPIs (pick best columns) ─────────────────────────────────
        num_profiles = [
            p for p in profiles
            if p.kind in (ColKind.NUMERIC_CONTINUOUS, ColKind.NUMERIC_DISCRETE)
            and p.coverage >= _MIN_COVERAGE and p.sum_val is not None
        ]
        num_profiles.sort(key=lambda p: p.unique_count, reverse=True)

        for p in num_profiles[:5]:
            label = _humanize(p.name)
            kpis.append(self._kpi(f"{label} Sum",    _fmt_number(p.sum_val),   "",    "teal",   "sigma",       col=p.name))
            kpis.append(self._kpi(f"{label} Mean",   _fmt_number(p.mean),      "",    "indigo", "trending-up", col=p.name))
            kpis.append(self._kpi(f"{label} Max",    _fmt_number(p.max_val),   "",    "sky",    "arrow-up",    col=p.name))
            if p.outlier_count:
                kpis.append(self._kpi(f"{label} Outliers", p.outlier_count, "values", "orange", "zap", col=p.name))

        # ── Categorical KPIs ──────────────────────────────────────────────────
        cat_profiles = [
            p for p in profiles
            if p.kind in (ColKind.CATEGORICAL, ColKind.BOOLEAN)
            and p.coverage >= _MIN_COVERAGE
        ]
        for p in cat_profiles[:3]:
            label = _humanize(p.name)
            kpis.append(self._kpi(
                f"{label} (top)",
                str(p.top_value)[:30] if p.top_value else "—",
                f"{p.top_freq_pct}%", "violet", "star", col=p.name,
            ))
            kpis.append(self._kpi(f"{label} Unique", p.unique_count, "values", "rose", "filter", col=p.name))

        # ── Datetime KPIs ─────────────────────────────────────────────────────
        date_profiles = [p for p in profiles if p.kind == ColKind.DATETIME]
        for p in date_profiles[:1]:
            kpis.append(self._kpi("Date From",     p.min_date or "—", "", "amber", "calendar", col=p.name))
            kpis.append(self._kpi("Date To",       p.max_date or "—", "", "amber", "calendar", col=p.name))
            kpis.append(self._kpi("Date Span",     p.date_range_days or 0, "days", "amber", "clock", col=p.name))

        # ── Quality score ─────────────────────────────────────────────────────
        quality = self._quality_score(profiles, completeness, dup_rows, len(df))
        kpis.append(self._kpi("Quality Score", f"{quality}/100", "", "green" if quality >= 80 else "orange", "shield", col=None))

        return kpis

    @staticmethod
    def _kpi(label: str, value: Any, suffix: str, color: str, icon: str, col: str = None) -> Dict:
        return {
            "label":  label,
            "value":  str(value),
            "suffix": suffix,
            "color":  color,
            "icon":   icon,
            "column": col,
        }

    @staticmethod
    def _quality_score(profiles, completeness, dup_rows, row_count) -> int:
        score = 100
        score -= max(0, (100 - completeness) * 0.5)
        if row_count > 0:
            score -= min(20, dup_rows / row_count * 100)
        constant_cols = sum(1 for p in profiles if p.kind == ColKind.CONSTANT)
        score -= constant_cols * 5
        return max(0, round(score))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chart Builder
# ─────────────────────────────────────────────────────────────────────────────

class ChartBuilder:
    """
    Decides which charts to render and builds their data payloads.

    Chart types produced:
      histogram        – distribution of any numeric column
      bar              – category frequencies
      donut            – category proportions (≤10 slices)
      scatter          – two numeric columns
      line             – time-series or sorted numeric sequence
      area             – cumulative line
      heatmap          – correlation matrix (≥3 numeric cols)
      box              – quartile box plot for any numeric column
      grouped_bar      – cross-tab: numeric grouped by categorical
      stacked_bar      – two categorical columns cross-tab
      treemap          – hierarchical: category → size by count or sum
      bubble           – three numeric dimensions
      pareto           – frequency bars + cumulative % line
      missing_bar      – horizontal missing-value audit
    """

    def build(self, df: pd.DataFrame, profiles: List[ColumnProfile]) -> List[Dict]:
        charts = []
        by_kind = _group_by_kind(profiles)

        num_cols  = by_kind.get(ColKind.NUMERIC_CONTINUOUS,  []) + by_kind.get(ColKind.NUMERIC_DISCRETE, [])
        cat_cols  = by_kind.get(ColKind.CATEGORICAL, [])
        bool_cols = by_kind.get(ColKind.BOOLEAN,     [])
        date_cols = by_kind.get(ColKind.DATETIME,    [])

        num_cols  = [p for p in num_cols  if p.coverage >= _MIN_COVERAGE]
        cat_cols  = [p for p in cat_cols  if p.coverage >= _MIN_COVERAGE]
        bool_cols = [p for p in bool_cols if p.coverage >= _MIN_COVERAGE]
        date_cols = [p for p in date_cols if p.coverage >= _MIN_COVERAGE]

        # ── 1. Distribution histograms (numeric cols) ─────────────────────────
        for p in num_cols[:6]:
            hist = self._histogram(df[p.name].dropna(), p)
            if hist:
                charts.append({
                    "id":    f"hist_{p.name}",
                    "type":  "histogram",
                    "title": f"Distribution — {_humanize(p.name)}",
                    "column": p.name,
                    "data":  hist,
                    "meta":  {"mean": p.mean, "median": p.median, "std": p.std},
                    "summary": _summary_histogram(p),
                })

        # ── 2. One chart per categorical column — the shape that best fits its
        #     cardinality, instead of stacking bar+donut+treemap+pareto on the
        #     same column (that was redundant: all four show the same counts).
        for p in (cat_cols + bool_cols)[:6]:
            if not p.value_counts:
                continue
            n = p.unique_count
            if n <= 6:
                total = sum(v["value"] for v in p.value_counts)
                slices = [{"label": v["label"], "value": v["value"], "pct": round(v["value"]/total*100, 1)} for v in p.value_counts[:_MAX_DONUT_SLICES]]
                charts.append({"id": f"donut_{p.name}", "type": "donut", "title": f"Proportion — {_humanize(p.name)}",
                               "column": p.name, "data": {"slices": slices, "total": total},
                               "summary": _summary_categorical(p, "makes up")})
            elif n <= 20:
                charts.append({"id": f"bar_{p.name}", "type": "bar", "title": f"Frequency — {_humanize(p.name)}",
                               "column": p.name, "data": p.value_counts[:_MAX_BARS], "meta": {"unique_count": n},
                               "summary": _summary_categorical(p, "appears most often, at")})
            elif n <= 40:
                pareto = self._pareto(p.value_counts)
                if pareto:
                    charts.append({"id": f"pareto_{p.name}", "type": "pareto", "title": f"Pareto — {_humanize(p.name)}",
                                   "column": p.name, "data": pareto, "summary": _summary_pareto(pareto, p)})
            else:
                tm = self._treemap_count(df, p.name) if not num_cols else self._treemap(df, p.name, num_cols[0].name, agg="sum")
                if tm:
                    charts.append({"id": f"treemap_{p.name}", "type": "treemap", "title": f"Treemap — {_humanize(p.name)}",
                                   "column": p.name, "data": tm, "summary": _summary_categorical(p, "is the largest group, at")})

        # ── 3. Scatter plots (pairs of numeric cols) ──────────────────────────
        pairs = _get_pairs(num_cols, max_pairs=4)
        for (px, py) in pairs:
            pts = self._scatter_points(df, px.name, py.name)
            if pts:
                trend = _linear_trend(pts)
                corr  = _pearson(pts)
                charts.append({
                    "id":    f"scatter_{px.name}_{py.name}",
                    "type":  "scatter",
                    "title": f"{_humanize(px.name)} vs {_humanize(py.name)}",
                    "x_col": px.name, "y_col": py.name,
                    "data":  {"points": pts, "trend": trend},
                    "meta":  {"correlation": corr},
                    "summary": _summary_scatter(px.name, py.name, corr),
                })

        # ── 4. Bubble (three numeric cols) ───────────────────────────────────
        if len(num_cols) >= 3:
            px, py, pz = num_cols[0], num_cols[1], num_cols[2]
            pts = self._bubble_points(df, px.name, py.name, pz.name)
            if pts:
                charts.append({
                    "id":    f"bubble_{px.name}_{py.name}_{pz.name}",
                    "type":  "bubble",
                    "title": f"Bubble — {_humanize(px.name)} / {_humanize(py.name)} / {_humanize(pz.name)}",
                    "x_col": px.name, "y_col": py.name, "z_col": pz.name,
                    "data":  pts,
                    "summary": f"Each point is a row — position shows {_humanize(px.name)} vs {_humanize(py.name)}, and size shows {_humanize(pz.name)}.",
                })

        # ── 5. Line / Area (time series) — one date × up to 2 numeric cols ────
        for dp in date_cols[:1]:
            for np_ in num_cols[:2]:
                series = self._time_series(df, dp.name, np_.name)
                if series and len(series) >= 3:
                    trend = _linear_trend([{"x": i, "y": pt["value"]} for i, pt in enumerate(series)])
                    charts.append({
                        "id":       f"line_{dp.name}_{np_.name}",
                        "type":     "line",
                        "title":    f"{_humanize(np_.name)} Over Time",
                        "date_col": dp.name, "value_col": np_.name,
                        "data":     series,
                        "summary":  _summary_trend(np_.name, trend, series),
                    })

        # ── 6. Line (sorted numeric as proxy sequence) — only without dates ───
        if not date_cols and num_cols:
            for p in num_cols[:2]:
                seq = self._numeric_sequence(df, p.name)
                if seq and len(seq) >= 10:
                    charts.append({
                        "id":    f"line_seq_{p.name}",
                        "type":  "line",
                        "title": f"{_humanize(p.name)} — Sequence",
                        "column": p.name,
                        "data":  seq,
                        "summary": f"{_humanize(p.name)} across rows in file order — ranges from {p.min_val} to {p.max_val}.",
                    })

        # ── 7. Correlation heatmap ────────────────────────────────────────────
        if len(num_cols) >= 3:
            hm = self._correlation_heatmap(df, num_cols[:12])
            if hm:
                charts.append({
                    "id":    "heatmap_correlation",
                    "type":  "heatmap",
                    "title": "Correlation Matrix",
                    "data":  hm,
                    "summary": _summary_heatmap(hm),
                })

        # ── 8. Box plots (numeric cols) ────────────────────────────────────────
        for p in num_cols[:4]:
            box = self._box_plot(df[p.name].dropna(), p)
            if box:
                charts.append({
                    "id":    f"box_{p.name}",
                    "type":  "box",
                    "title": f"Box Plot — {_humanize(p.name)}",
                    "column": p.name,
                    "data":  box,
                    "summary": _summary_box(p.name, box),
                })

        # ── 9. Numeric-by-category — pick the single best grouping column ─────
        best_group = next((cp for cp in cat_cols if 2 <= cp.unique_count <= 15), None)
        if num_cols and best_group:
            for np_ in num_cols[:2]:
                grouped = self._grouped_box(df, np_.name, best_group.name)
                if grouped:
                    charts.append({
                        "id":      f"grouped_box_{np_.name}_{best_group.name}",
                        "type":    "grouped_box",
                        "title":   f"{_humanize(np_.name)} by {_humanize(best_group.name)}",
                        "num_col": np_.name, "cat_col": best_group.name,
                        "data":    grouped,
                        "summary": _summary_grouped(np_.name, best_group.name, grouped, "median"),
                    })
                gb = self._grouped_bar(df, np_.name, best_group.name)
                if gb:
                    charts.append({
                        "id":      f"grouped_bar_{np_.name}_{best_group.name}",
                        "type":    "grouped_bar",
                        "title":   f"{_humanize(np_.name)} by {_humanize(best_group.name)}",
                        "num_col": np_.name, "cat_col": best_group.name,
                        "data":    gb,
                        "summary": _summary_grouped(np_.name, best_group.name, gb, "sum"),
                    })

        # ── 10. Stacked bar (two categorical cross-tab) ────────────────────────
        if len(cat_cols) >= 2:
            c1, c2 = cat_cols[0], cat_cols[1]
            if c1.unique_count <= 20 and c2.unique_count <= 10:
                sb = self._stacked_bar(df, c1.name, c2.name)
                if sb:
                    charts.append({
                        "id":    f"stacked_{c1.name}_{c2.name}",
                        "type":  "stacked_bar",
                        "title": f"{_humanize(c1.name)} × {_humanize(c2.name)}",
                        "x_col": c1.name, "group_col": c2.name,
                        "data":  sb,
                        "summary": f"Breaks down {_humanize(c1.name)} by {_humanize(c2.name)} so you can compare composition across groups.",
                    })

        # ── 11. Missing value audit ─────────────────────────────────────────────
        missing = [
            {"column": p.name, "missing": p.null_count, "pct": p.null_pct, "kind": p.kind.name}
            for p in profiles if p.null_count > 0
        ]
        if missing:
            missing = sorted(missing, key=lambda x: x["pct"], reverse=True)
            charts.append({
                "id":    "missing_audit",
                "type":  "missing_bar",
                "title": "Missing Values",
                "data":  missing,
                "summary": f"{_humanize(missing[0]['column'])} has the most gaps — {missing[0]['pct']}% missing." if missing else "No missing values.",
            })

        return charts

    # ── Chart data builders ───────────────────────────────────────────────────

    @staticmethod
    def _histogram(s: pd.Series, p: ColumnProfile) -> List[Dict]:
        if s.empty or len(s) < 2:
            return []
        n_bins = min(40, max(5, int(np.sqrt(len(s)))))
        try:
            counts, edges = np.histogram(s.dropna(), bins=n_bins)
            return [
                {"x0": _sf(edges[i]), "x1": _sf(edges[i+1]), "count": int(counts[i])}
                for i in range(len(counts))
                if counts[i] > 0
            ]
        except Exception:
            return []

    @staticmethod
    def _scatter_points(df: pd.DataFrame, x: str, y: str) -> List[Dict]:
        try:
            sub = df[[x, y]].dropna().head(_SCATTER_LIMIT)
            xv  = pd.to_numeric(sub[x], errors="coerce")
            yv  = pd.to_numeric(sub[y], errors="coerce")
            mask = xv.notna() & yv.notna()
            return [{"x": _sf(xv.iloc[i]), "y": _sf(yv.iloc[i])} for i in range(mask.sum()) if mask.iloc[i]]
        except Exception:
            return []

    @staticmethod
    def _bubble_points(df: pd.DataFrame, x: str, y: str, z: str) -> List[Dict]:
        try:
            sub  = df[[x, y, z]].dropna().head(300)
            zmax = float(pd.to_numeric(sub[z], errors="coerce").max())
            if not zmax:
                return []
            pts = []
            for _, row in sub.iterrows():
                xv = _sf(row[x]); yv = _sf(row[y]); zv = _sf(row[z])
                pts.append({"x": xv, "y": yv, "z": zv, "r": round(zv / zmax * 40 + 4, 1)})
            return pts
        except Exception:
            return []

    @staticmethod
    def _time_series(df: pd.DataFrame, date_col: str, val_col: str) -> List[Dict]:
        try:
            sub  = df[[date_col, val_col]].copy()
            sub[date_col] = pd.to_datetime(sub[date_col], errors="coerce")
            sub[val_col]  = pd.to_numeric(sub[val_col], errors="coerce")
            sub           = sub.dropna().sort_values(date_col)
            agg = sub.groupby(sub[date_col].dt.date)[val_col].mean().reset_index()
            return [{"date": str(row[date_col]), "value": _sf(row[val_col])} for _, row in agg.head(300).iterrows()]
        except Exception:
            return []

    @staticmethod
    def _cumulative(series: List[Dict]) -> List[Dict]:
        result, running = [], 0.0
        for pt in series:
            running += pt["value"]
            result.append({"date": pt["date"], "value": round(running, 4)})
        return result

    @staticmethod
    def _numeric_sequence(df: pd.DataFrame, col: str) -> List[Dict]:
        try:
            s = pd.to_numeric(df[col], errors="coerce").dropna().reset_index(drop=True)
            step = max(1, len(s) // 200)
            return [{"index": int(i), "value": _sf(v)} for i, v in s.iloc[::step].items()]
        except Exception:
            return []

    @staticmethod
    def _correlation_heatmap(df: pd.DataFrame, num_profiles: List[ColumnProfile]) -> Optional[Dict]:
        try:
            cols = [p.name for p in num_profiles]
            sub  = df[cols].apply(pd.to_numeric, errors="coerce").dropna(how="all")
            corr = sub.corr().round(3)
            valid_cols = [c for c in cols if c in corr.columns]
            if len(valid_cols) < 2:
                return None
            corr = corr.loc[valid_cols, valid_cols]
            return {
                "columns": valid_cols,
                "matrix":  [[_sf(v) for v in row] for row in corr.values.tolist()],
            }
        except Exception:
            return None

    @staticmethod
    def _box_plot(s: pd.Series, p: ColumnProfile) -> Optional[Dict]:
        if s.empty or len(s) < 5:
            return None
        s = pd.to_numeric(s, errors="coerce").dropna()
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr    = q3 - q1
        lower  = q1 - 1.5 * iqr
        upper  = q3 + 1.5 * iqr
        return {
            "min":      _sf(float(s.min())),
            "q1":       _sf(q1),
            "median":   _sf(float(s.median())),
            "q3":       _sf(q3),
            "max":      _sf(float(s.max())),
            "mean":     _sf(float(s.mean())),
            "outliers": [_sf(float(v)) for v in s[(s < lower) | (s > upper)].head(50)],
            "whisker_low":  _sf(max(float(s.min()), lower)),
            "whisker_high": _sf(min(float(s.max()), upper)),
        }

    @staticmethod
    def _grouped_box(df: pd.DataFrame, num_col: str, cat_col: str) -> List[Dict]:
        try:
            groups = []
            for grp, sub in df.groupby(cat_col)[num_col]:
                s = pd.to_numeric(sub, errors="coerce").dropna()
                if len(s) < 3:
                    continue
                q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
                groups.append({
                    "group":   str(grp)[:40],
                    "min":     _sf(float(s.min())),
                    "q1":      _sf(q1),
                    "median":  _sf(float(s.median())),
                    "q3":      _sf(q3),
                    "max":     _sf(float(s.max())),
                    "count":   len(s),
                })
            return groups
        except Exception:
            return []

    @staticmethod
    def _grouped_bar(df: pd.DataFrame, num_col: str, cat_col: str) -> List[Dict]:
        try:
            grp = (
                df.groupby(cat_col)[num_col]
                .agg(["mean","sum","count"])
                .reset_index()
                .sort_values("sum", ascending=False)
                .head(_MAX_BARS)
            )
            return [
                {
                    "label": str(row[cat_col])[:40],
                    "mean":  _sf(row["mean"]),
                    "sum":   _sf(row["sum"]),
                    "count": int(row["count"]),
                }
                for _, row in grp.iterrows()
            ]
        except Exception:
            return []

    @staticmethod
    def _stacked_bar(df: pd.DataFrame, x_col: str, grp_col: str) -> Optional[Dict]:
        try:
            ct   = pd.crosstab(df[x_col], df[grp_col])
            cats = ct.columns.astype(str).tolist()[:10]
            rows = []
            for idx, row in ct.head(_MAX_BARS).iterrows():
                entry = {"label": str(idx)[:40]}
                entry.update({c: int(row[c]) for c in cats if c in row.index.astype(str)})
                rows.append(entry)
            return {"labels": cats, "rows": rows}
        except Exception:
            return None

    @staticmethod
    def _treemap(df: pd.DataFrame, cat_col: str, num_col: str, agg: str = "sum") -> List[Dict]:
        try:
            s = pd.to_numeric(df[num_col], errors="coerce")
            g = df.groupby(cat_col)[num_col].apply(lambda x: float(pd.to_numeric(x, errors="coerce").sum())).reset_index()
            g.columns = ["label","value"]
            g = g.sort_values("value", ascending=False).head(_MAX_BARS)
            total = g["value"].sum()
            return [{"label": str(r["label"])[:40], "value": _sf(r["value"]), "pct": round(r["value"]/total*100,1)} for _,r in g.iterrows()]
        except Exception:
            return []

    @staticmethod
    def _treemap_count(df: pd.DataFrame, cat_col: str) -> List[Dict]:
        try:
            vc    = df[cat_col].value_counts().head(_MAX_BARS)
            total = int(vc.sum())
            return [{"label": str(k)[:40], "value": int(v), "pct": round(v/total*100,1)} for k,v in vc.items()]
        except Exception:
            return []

    @staticmethod
    def _pareto(vc_list: List[Dict]) -> List[Dict]:
        try:
            total = sum(v["value"] for v in vc_list)
            if total == 0:
                return []
            cum, result = 0.0, []
            for v in vc_list[:_MAX_BARS]:
                cum += v["value"] / total * 100
                result.append({"label": v["label"], "value": v["value"], "cumulative_pct": round(cum, 1)})
            return result
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Data Sampler
# ─────────────────────────────────────────────────────────────────────────────

class DataSampler:
    def sample(self, df: pd.DataFrame, profiles: List[ColumnProfile]) -> Dict:
        preview = df.head(_PREVIEW_ROWS).copy()
        for p in profiles:
            if p.kind == ColKind.DATETIME and p.name in preview.columns:
                preview[p.name] = preview[p.name].astype(str)
        preview = preview.fillna("")
        return {
            "columns":   [p.name for p in profiles],
            "col_kinds": {p.name: p.kind.name for p in profiles},
            "rows":      preview.values.tolist(),
            "total_rows": len(df),
            "showing":   min(_PREVIEW_ROWS, len(df)),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Quality Auditor
# ─────────────────────────────────────────────────────────────────────────────

class QualityAuditor:
    def audit(self, df: pd.DataFrame, profiles: List[ColumnProfile]) -> Dict:
        issues = []
        for p in profiles:
            if p.null_pct > 50:
                issues.append({"col": p.name, "severity": "high",   "issue": f"{p.null_pct}% missing values"})
            elif p.null_pct > 10:
                issues.append({"col": p.name, "severity": "medium", "issue": f"{p.null_pct}% missing values"})
            if p.kind == ColKind.CONSTANT:
                issues.append({"col": p.name, "severity": "low",    "issue": "Column is constant — no variance"})
            if p.kind in (ColKind.NUMERIC_CONTINUOUS, ColKind.NUMERIC_DISCRETE):
                if p.cv and p.cv > 200:
                    issues.append({"col": p.name, "severity": "medium", "issue": f"Very high variance (CV={p.cv}%)"})
                if p.outlier_count and p.outlier_count > p.non_null * 0.05:
                    issues.append({"col": p.name, "severity": "low", "issue": f"{p.outlier_count} outliers detected"})
        dup_rows = int(df.duplicated().sum())
        if dup_rows:
            issues.append({"col": "_dataset", "severity": "medium", "issue": f"{dup_rows} duplicate rows"})
        return {
            "issues":    sorted(issues, key=lambda x: {"high":0,"medium":1,"low":2}[x["severity"]]),
            "issue_count": len(issues),
            "high_count":  sum(1 for i in issues if i["severity"]=="high"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Descriptive Stats Table
# ─────────────────────────────────────────────────────────────────────────────

class DescriptiveStatsBuilder:
    """Builds a clean stats table — one row per column, all types included."""

    def build(self, profiles: List[ColumnProfile]) -> Dict:
        rows = []
        for p in profiles:
            row = {
                "column":   p.name,
                "kind":     p.kind.name,
                "dtype":    p.dtype_str,
                "total":    p.total,
                "non_null": p.non_null,
                "null_pct": f"{p.null_pct}%",
                "unique":   p.unique_count,
                "coverage": f"{round(p.coverage*100,1)}%",
            }
            if p.kind in (ColKind.NUMERIC_CONTINUOUS, ColKind.NUMERIC_DISCRETE):
                row.update({
                    "min":      p.min_val,
                    "max":      p.max_val,
                    "mean":     p.mean,
                    "median":   p.median,
                    "std":      p.std,
                    "q1":       p.q1,
                    "q3":       p.q3,
                    "skewness": p.skewness,
                    "outliers": p.outlier_count,
                    "cv_pct":   p.cv,
                })
            elif p.kind in (ColKind.CATEGORICAL, ColKind.BOOLEAN):
                row.update({"top_value": p.top_value, "top_freq_pct": f"{p.top_freq_pct}%"})
            elif p.kind == ColKind.DATETIME:
                row.update({"min_date": p.min_date, "max_date": p.max_date, "span_days": p.date_range_days})
            rows.append(row)
        return {
            "rows":    rows,
            "columns": ["column","kind","dtype","total","non_null","null_pct","unique","coverage",
                        "min","max","mean","median","std","q1","q3","skewness","outliers","cv_pct",
                        "top_value","top_freq_pct","min_date","max_date","span_days"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_analytics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Entry point. Accepts any pandas DataFrame.
    Returns a complete analytics payload ready for JSON serialisation.

    Output keys:
      summary        – dataset-level stats (rows, cols, memory, etc.)
      profiles       – per-column profiles
      kpis           – KPI card list
      charts         – all chart definitions and data
      descriptive    – stats table
      quality        – data quality audit
      preview        – raw data preview
    """
    if df.empty:
        return {"error": "Empty dataset — nothing to analyse."}

    profiler  = DataProfiler()
    profiles  = profiler.profile(df)

    kpis      = KPIGenerator().generate(df, profiles)
    charts    = ChartBuilder().build(df, profiles)
    stats     = DescriptiveStatsBuilder().build(profiles)
    quality   = QualityAuditor().audit(df, profiles)
    preview   = DataSampler().sample(df, profiles)

    kind_counts = Counter(p.kind.name for p in profiles)
    excluded_columns = [
        {"column": p.name, "kind": p.kind.name, "reason": p.excluded_reason}
        for p in profiles if p.excluded_reason
    ]

    summary = {
        "total_rows":    len(df),
        "total_cols":    len(df.columns),
        "numeric_cols":  kind_counts.get("NUMERIC_CONTINUOUS", 0) + kind_counts.get("NUMERIC_DISCRETE", 0),
        "categorical_cols": kind_counts.get("CATEGORICAL", 0) + kind_counts.get("BOOLEAN", 0),
        "datetime_cols": kind_counts.get("DATETIME", 0),
        "constant_cols": kind_counts.get("CONSTANT", 0),
        "id_cols":       kind_counts.get("ID_LIKE", 0),
        "high_cardinality_cols": kind_counts.get("HIGH_CARDINALITY", 0),
        "excluded_columns": excluded_columns,
        "total_missing": int(df.isnull().sum().sum()),
        "completeness_pct": round((1 - df.isnull().sum().sum() / max(df.size, 1)) * 100, 1),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_kb":     round(df.memory_usage(deep=True).sum() / 1024, 1),
        "chart_count":   len(charts),
        "kpi_count":     len(kpis),
    }

    return {
        "summary":     summary,
        "profiles":    [p.to_dict() for p in profiles],
        "kpis":        kpis,
        "charts":      charts,
        "descriptive": stats,
        "quality":     quality,
        "preview":     preview,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _sf(v) -> float:
    """Safe float — converts to float, replaces NaN/Inf with None."""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _fmt_number(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if abs(f) >= 1_000_000_000: return f"{f/1_000_000_000:.2f}B"
        if abs(f) >= 1_000_000:     return f"{f/1_000_000:.2f}M"
        if abs(f) >= 1_000:         return f"{f/1_000:.1f}K"
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _humanize(name: str) -> str:
    s = re.sub(r"[_\-]", " ", str(name))
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return s.strip().title()


# ─────────────────────────────────────────────────────────────────────────────
# Plain-language chart summaries — shown on hover in the UI so a chart can be
# understood in one sentence without having to read the axes.
# ─────────────────────────────────────────────────────────────────────────────

def _skew_desc(skew: Optional[float]) -> str:
    if skew is None:
        return ""
    if skew > 1:    return "with a long tail toward higher values"
    if skew > 0.3:  return "skewed slightly toward higher values"
    if skew < -1:   return "with a long tail toward lower values"
    if skew < -0.3: return "skewed slightly toward lower values"
    return "fairly symmetric"


def _corr_desc(r: Optional[float]) -> str:
    if r is None:
        return "no clear relationship"
    a = abs(r)
    strength = "very strong" if a >= 0.8 else "strong" if a >= 0.6 else "moderate" if a >= 0.3 else "weak"
    direction = "positive" if r > 0 else "negative"
    return f"a {strength} {direction} relationship (r={r})" if a >= 0.3 else "little to no relationship"


def _summary_histogram(p: ColumnProfile) -> str:
    return (f"{_humanize(p.name)} ranges from {_fmt_number(p.min_val)} to {_fmt_number(p.max_val)}, "
            f"averaging {_fmt_number(p.mean)} (median {_fmt_number(p.median)}) — {_skew_desc(p.skewness)}.")


def _summary_categorical(p: ColumnProfile, verb: str) -> str:
    return (f"\"{p.top_value}\" {verb} {p.top_freq_pct}% of {p.unique_count} categories "
            f"({p.non_null} records total).")


def _summary_pareto(pareto: List[Dict], p: ColumnProfile) -> str:
    if not pareto:
        return f"Frequency breakdown of {_humanize(p.name)}."
    n80 = next((i+1 for i, r in enumerate(pareto) if r["cumulative_pct"] >= 80), len(pareto))
    return f"Just {n80} of {len(pareto)} categories account for 80% of all {_humanize(p.name)} records."


def _summary_scatter(x: str, y: str, corr: Optional[float]) -> str:
    return f"{_humanize(x)} and {_humanize(y)} show {_corr_desc(corr)}."


def _summary_trend(col: str, trend: Optional[Dict], series: List[Dict]) -> str:
    if not trend or len(series) < 2:
        return f"{_humanize(col)} over time."
    change = trend["y2"] - trend["y1"]
    direction = "risen" if change > 0 else "fallen" if change < 0 else "stayed flat"
    return f"{_humanize(col)} has {direction} from {_fmt_number(trend['y1'])} to {_fmt_number(trend['y2'])} across the period shown."


def _summary_heatmap(hm: Dict) -> str:
    cols, matrix = hm["columns"], hm["matrix"]
    best, best_r = None, 0
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            if matrix[i][j] is not None and abs(matrix[i][j]) > abs(best_r):
                best, best_r = (cols[i], cols[j]), matrix[i][j]
    if not best:
        return "Correlation between all numeric columns."
    return f"The strongest relationship is between {_humanize(best[0])} and {_humanize(best[1])} ({_corr_desc(best_r)})."


def _summary_box(col: str, box: Dict) -> str:
    n_out = len(box.get("outliers") or [])
    out_txt = f" {n_out} outlier(s) detected." if n_out else " No outliers detected."
    return (f"Median {_humanize(col)} is {_fmt_number(box['median'])}, with the middle 50% of values "
            f"between {_fmt_number(box['q1'])} and {_fmt_number(box['q3'])}.{out_txt}")


def _summary_grouped(num_col: str, cat_col: str, rows: List[Dict], by: str) -> str:
    if not rows:
        return f"{_humanize(num_col)} broken down by {_humanize(cat_col)}."
    key = "median" if by == "median" else "sum"
    top = max(rows, key=lambda r: r.get(key, 0) or 0)
    label = top.get("group") or top.get("label", "")
    return f"\"{label}\" has the highest {by} {_humanize(num_col)} ({_fmt_number(top.get(key))}) among {_humanize(cat_col)} groups."


def _group_by_kind(profiles: List[ColumnProfile]) -> Dict[ColKind, List[ColumnProfile]]:
    out: Dict[ColKind, List[ColumnProfile]] = {}
    for p in profiles:
        out.setdefault(p.kind, []).append(p)
    return out


def _get_pairs(num_profiles: List[ColumnProfile], max_pairs: int = 4) -> List[Tuple]:
    pairs = []
    for i in range(len(num_profiles)):
        for j in range(i + 1, len(num_profiles)):
            pairs.append((num_profiles[i], num_profiles[j]))
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def _pearson(pts: List[Dict]) -> Optional[float]:
    try:
        xs = np.array([p["x"] for p in pts if p["x"] is not None], dtype=float)
        ys = np.array([p["y"] for p in pts if p["y"] is not None], dtype=float)
        if len(xs) < 3 or len(ys) < 3:
            return None
        r = float(np.corrcoef(xs, ys)[0, 1])
        return None if math.isnan(r) else round(r, 4)
    except Exception:
        return None


def _linear_trend(pts: List[Dict]) -> Optional[Dict]:
    try:
        xs = np.array([p["x"] for p in pts if p["x"] is not None], dtype=float)
        ys = np.array([p["y"] for p in pts if p["y"] is not None], dtype=float)
        if len(xs) < 3:
            return None
        m, b = np.polyfit(xs, ys, 1)
        return {
            "slope":     round(float(m), 6),
            "intercept": round(float(b), 4),
            "x1": _sf(float(xs.min())),
            "y1": _sf(float(m * xs.min() + b)),
            "x2": _sf(float(xs.max())),
            "y2": _sf(float(m * xs.max() + b)),
        }
    except Exception:
        return None