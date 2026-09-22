
      // ── Data injected by Django ────────────────────────────────────────────────
      // {{ analytics_json }} is the FastAPI response dict, serialised by the view:
      //   { success, filename, file_type, tables:[...], results:{ <table>: {cleaning_report, analytics} } }
      // analytics itself is: { summary, profiles, kpis, charts, descriptive, quality, preview }


      function showView(view, btn) {
        document
          .querySelectorAll(".nav-item[id]")
          .forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        document
          .getElementById("viewDashboard")
          .classList.toggle("active", view === "dashboard");
        document
          .getElementById("viewSources")
          .classList.toggle("active", view === "sources");
        document
          .getElementById("viewReports")
          .classList.toggle("active", view === "reports");
        document.getElementById("pageTitle").textContent = {
          dashboard: "Dashboard",
          sources: "Data Sources",
          reports: "Reports",
        }[view];
      }

      function toggleReportSection(head) {
        head.parentElement.classList.toggle("collapsed");
      }

      function copyReport() {
        const text = document.getElementById("reportContent").innerText;
        const btn = document.getElementById("copyReportBtn");
        navigator.clipboard
          ?.writeText(text)
          .then(() => {
            const orig = btn.textContent;
            btn.textContent = "✓ Copied";
            setTimeout(() => {
              btn.textContent = orig;
            }, 1600);
          })
          .catch(() => {});
      }

      // ── Search — live-filters the KPI row and chart grid on the Dashboard view
      // by title/label/summary text. Re-applied after every re-render (table tab
      // switches rebuild both grids from scratch).
      let currentSearch = "";

      function handleSearch(query) {
        currentSearch = query.trim().toLowerCase();
        document.getElementById("searchClear").style.display = currentSearch
          ? ""
          : "none";
        if (
          currentSearch &&
          !document.getElementById("viewDashboard").classList.contains("active")
        ) {
          showView("dashboard", document.getElementById("navDashboard"));
        }
        applySearchFilter();
      }

      function clearSearch() {
        const input = document.getElementById("searchInput");
        input.value = "";
        input.focus();
        handleSearch("");
      }

      function applySearchFilter() {
        const q = currentSearch;

        document.querySelectorAll("#kpiGrid .kpi-card").forEach((card) => {
          const label =
            card.querySelector(".kpi-label")?.textContent.toLowerCase() || "";
          card.style.display = !q || label.includes(q) ? "" : "none";
        });

        const grid = document.getElementById("chartsGrid");
        let chartMatches = 0;
        grid.querySelectorAll(".chart-card").forEach((card) => {
          const title =
            card
              .querySelector(".chart-title-text")
              ?.textContent.toLowerCase() || "";
          const summary =
            card
              .querySelector(".chart-summary-text")
              ?.textContent.toLowerCase() || "";
          const match = !q || title.includes(q) || summary.includes(q);
          card.style.display = match ? "" : "none";
          if (match) chartMatches++;
        });

        let noResults = grid.querySelector(".search-no-results");
        if (q && chartMatches === 0) {
          if (!noResults) {
            noResults = document.createElement("div");
            noResults.className = "card c-12 search-no-results";
            grid.appendChild(noResults);
          }
          noResults.textContent = `No charts match "${q}"`;
        } else if (noResults) {
          noResults.remove();
        }
      }

      // ── Per-theme chart palette — picked once, colors every chart/KPI dot ─────
      const THEME_PALETTES = {
        shopeers: [
          "#4F6EF7",
          "#1FA971",
          "#F59E0B",
          "#EC4899",
          "#06B6D4",
          "#8B5CF6",
          "#EF4444",
          "#14B8A6",
        ],
        donezo: [
          "#1B8354",
          "#2FA972",
          "#F2C94C",
          "#EB5757",
          "#56CCF2",
          "#9B51E0",
          "#F2994A",
          "#27AE60",
        ],
        stakent: [
          "#8B5CF6",
          "#22C55E",
          "#F43F5E",
          "#38BDF8",
          "#FACC15",
          "#F472B6",
          "#34D399",
          "#F97316",
        ],
        finpoint: [
          "#FF5A36",
          "#FFC542",
          "#7C5CFC",
          "#22C55E",
          "#38BDF8",
          "#F472B6",
          "#EF4444",
          "#14B8A6",
        ],
        make: [
          "#8FA33A",
          "#5C7CFA",
          "#E8895C",
          "#56CCF2",
          "#F2C94C",
          "#EB5757",
          "#7C8471",
          "#B9D94D",
        ],
      };
      const PAL = THEME_PALETTES[THEME] || THEME_PALETTES.shopeers;

      // ── Shared state ───────────────────────────────────────────────────────────
      let activeTable = null;
      const tooltip = document.getElementById("tooltip");
      const CHART_SPAN = {
        histogram: "c-6",
        bar: "c-6",
        donut: "c-4",
        scatter: "c-6",
        bubble: "c-6",
        line: "c-7",
        area: "c-7",
        heatmap: "c-8",
        box: "c-4",
        grouped_box: "c-7",
        grouped_bar: "c-6",
        stacked_bar: "c-7",
        treemap: "c-6",
        pareto: "c-7",
        missing_bar: "c-12",
      };

      function switchTable(name, btn) {
        document
          .querySelectorAll(".tab-btn")
          .forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeTable = name;
        const content = document.querySelector(".content");
        content.classList.add("fading");
        setTimeout(() => {
          renderTableData(APP_DATA.results[name]);
          content.classList.remove("fading");
        }, 160);
      }

      // Animates a KPI's numeric value counting up from 0 — parses leading digits
      // (with optional commas/decimal) and keeps any surrounding text (currency
      // symbols, %, etc.) exactly as the backend sent it.
      function animateValue(el, raw) {
        // Only animate genuine numeric-looking values (optionally with a currency
        // symbol prefix, or a K/M/B/%//100 style suffix) — NOT category labels
        // that happen to contain digits, like "City11" or "SKU-006".
        const m = String(raw).match(
          /^([\$€£¥]?)(-?[\d,]+\.?\d*)([a-zA-Z%\/][\w\/%.]*)?$/,
        );
        if (!m) {
          el.textContent = raw;
          return;
        }
        const [, prefix, numStr, suffixRaw] = m;
        const suffixText = suffixRaw || "";
        const target = parseFloat(numStr.replace(/,/g, ""));
        if (isNaN(target)) {
          el.textContent = raw;
          return;
        }
        const decimals = (numStr.split(".")[1] || "").length;
        const dur = 800,
          start = performance.now();
        function frame(now) {
          const t = Math.min(1, (now - start) / dur);
          const eased = 1 - Math.pow(1 - t, 3);
          const val = target * eased;
          el.textContent =
            prefix +
            val.toLocaleString(undefined, {
              minimumFractionDigits: decimals,
              maximumFractionDigits: decimals,
            }) +
            suffixText;
          if (t < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
      }

      // Returns 0-100 if a KPI value is percentage-like (e.g. "92.4%", "100/100"),
      // otherwise null — used to decide whether to draw a mini progress bar.
      function kpiPercent(raw) {
        const s = String(raw);
        let m = s.match(/^(\d+(?:\.\d+)?)%$/);
        if (m) return Math.max(0, Math.min(100, parseFloat(m[1])));
        m = s.match(/^(\d+(?:\.\d+)?)\/100$/);
        if (m) return Math.max(0, Math.min(100, parseFloat(m[1])));
        return null;
      }

      // Picks a simple glyph icon for a KPI card based on its label — purely
      // cosmetic, keeps the KPI row from being a flat wall of numbers.
      function kpiIcon(label) {
        const l = label.toLowerCase();
        if (l.includes("row")) return "▤";
        if (l.includes("column")) return "▥";
        if (l.includes("complete")) return "✓";
        if (l.includes("quality")) return "◈";
        if (l.includes("missing")) return "⚠";
        if (l.includes("duplicate")) return "⧉";
        if (l.includes("sum") || l.includes("revenue") || l.includes("total"))
          return "∑";
        if (l.includes("mean") || l.includes("average")) return "~";
        if (l.includes("median")) return "≈";
        if (l.includes("std") || l.includes("deviation")) return "σ";
        if (l.includes("top")) return "★";
        if (l.includes("unique")) return "◆";
        if (l.includes("correlation")) return "⇄";
        if (l.includes("min")) return "↓";
        if (l.includes("max")) return "↑";
        return "●";
      }

      // Builds the Reports view: a row of quick-glance badges plus collapsible,
      // highlighted sections — composed entirely from stats the backend already
      // computed (no new analysis happens here), so it always matches the charts.
      function hl(text, cls) {
        return `<span class="hl${cls ? " " + cls : ""}">${text}</span>`;
      }

      function generateReport(an, cr, filename, table) {
        const s = an.summary || {};
        const kpis = an.kpis || [];
        const scoreKpi = kpis.find((k) => k.label === "Quality Score");
        const score = scoreKpi ? parseInt(scoreKpi.value) : null;
        const scoreCls =
          score === null
            ? ""
            : score >= 90
              ? "hl-good"
              : score >= 70
                ? ""
                : "hl-warn";

        // Badges
        const badges = [
          `<span class="report-badge">📄 <b>${filename}</b> · ${table}</span>`,
          `<span class="report-badge">${(s.total_rows || 0).toLocaleString()} rows × ${s.total_cols || 0} cols</span>`,
        ];
        if (score !== null)
          badges.push(
            `<span class="report-badge">Quality ${hl(score + "/100", scoreCls)}</span>`,
          );
        document.getElementById("reportBadges").innerHTML = badges.join("");

        const sections = [];

        // ── Overview ─────────────────────────────────────────────────────────────
        sections.push({
          icon: "📊",
          title: "Overview",
          body:
            `<p>This table has ${hl((s.total_rows || 0).toLocaleString())} rows and ${hl(s.total_cols || 0)} columns — ` +
            `<u>${s.numeric_cols || 0} numeric</u>, <u>${s.categorical_cols || 0} categorical</u>` +
            `${s.datetime_cols ? `, <u>${s.datetime_cols} date/time</u>` : ""} field(s). ` +
            `The analysis produced ${hl(an.charts?.length || 0)} charts and ${hl(kpis.length)} key metrics below.</p>`,
        });

        // ── Data Quality ─────────────────────────────────────────────────────────
        const missing = s.total_missing || 0;
        let qualityBody =
          missing > 0
            ? `<p>Completeness is ${hl(s.completeness_pct + "%", s.completeness_pct >= 95 ? "hl-good" : "hl-warn")}, with ${hl(missing.toLocaleString(), "hl-warn")} missing value(s)` +
              `${s.duplicate_rows ? ` and ${hl(s.duplicate_rows, "hl-warn")} duplicate row(s)` : ""} found — ` +
              `${(cr.steps || []).length ? `<u>automatically cleaned</u> before analysis (${cr.steps.length} step(s))` : "left as-is"}.</p>`
            : `<p>The data is ${hl("fully complete", "hl-good")} — no missing values were found.</p>`;
        const issues = an.quality?.issues || [];
        if (issues.length) {
          qualityBody +=
            `<ul>` +
            issues
              .slice(0, 6)
              .map(
                (i) =>
                  `<li><span class="report-bullet">${i.severity === "high" ? "🔴" : i.severity === "medium" ? "🟡" : "🟢"}</span>` +
                  `<span>${i.col === "_dataset" ? "" : `<u>${i.col}</u>: `}${i.issue}</span></li>`,
              )
              .join("") +
            `</ul>`;
        }
        sections.push({ icon: "🧹", title: "Data Quality", body: qualityBody });

        // ── Key Insights (reuses real chart summaries — no re-analysis) ──────────
        const insightCharts = (an.charts || [])
          .filter(
            (c) =>
              ["donut", "bar", "heatmap", "box"].includes(c.type) ||
              (c.type === "line" && c.date_col),
          )
          .slice(0, 6);
        if (insightCharts.length) {
          sections.push({
            icon: "🔍",
            title: "Key Insights",
            body:
              `<ul>` +
              insightCharts
                .map((c) => {
                  // Highlight the first quoted phrase or number in the summary for scannability
                  let txt = c.summary || c.title;
                  txt = txt.replace(/"([^"]+)"/, (m, p1) => `"${hl(p1)}"`);
                  txt = txt.replace(/\b(r=-?[\d.]+)\b/, (m) => hl(m));
                  return `<li><span class="report-bullet">▸</span><span>${txt}</span></li>`;
                })
                .join("") +
              `</ul>`,
          });
        }

        // ── Excluded from analysis ────────────────────────────────────────────────
        const excluded = s.excluded_columns || [];
        if (excluded.length) {
          sections.push({
            icon: "🚫",
            title: `Excluded From Analysis (${excluded.length})`,
            body:
              `<p>These columns were left out because they're <u>identifiers</u> or <u>too high-cardinality</u> to mean anything as a chart category:</p><ul>` +
              excluded
                .map(
                  (e) =>
                    `<li><span class="report-bullet">•</span><span>${hl(e.column)} — ${e.reason}</span></li>`,
                )
                .join("") +
              `</ul>`,
          });
        }

        return sections
          .map(
            (sec, i) => `
    <div class="report-section enter" style="animation-delay:${i * 0.05}s">
      <div class="report-section-head" onclick="toggleReportSection(this)">
        <div class="report-section-icon">${sec.icon}</div>
        <div class="report-section-title">${sec.title}</div>
        <div class="report-chevron">▾</div>
      </div>
      <div class="report-section-body">${sec.body}</div>
    </div>`,
          )
          .join("");
      }

      function renderTableData(result) {
        if (!result || result.error) {
          document.getElementById("kpiGrid").innerHTML =
            `<div style="color:var(--negative);font-family:'DM Mono',monospace;font-size:.85rem">Error: ${result?.error || "Unknown"}</div>`;
          document.getElementById("chartsGrid").innerHTML = "";
          document.getElementById("qualityCard").style.display = "none";
          return;
        }
        const { cleaning_report: cr, analytics: an } = result;

        // KPIs — icon badge + count-up value + progress bar for percentage-like metrics
        document.getElementById("kpiGrid").innerHTML = (an.kpis || [])
          .map((k, i) => {
            const color = PAL[i % PAL.length];
            const pct = kpiPercent(k.value);
            return `<div class="kpi-card enter" style="animation-delay:${i * 0.04}s;--kpi-color:${color};--kpi-color-soft:${color}22">
       <div class="kpi-top">
         <div class="kpi-icon${pct !== null ? " pulse-icon" : ""}">${kpiIcon(k.label)}</div>
         <div class="kpi-label">${k.label}</div>
       </div>
       <div class="kpi-value"><span class="kpi-num" data-value="${k.value}">0</span>${k.suffix ? ` <span class="suffix">${k.suffix}</span>` : ""}</div>
       ${pct !== null ? `<div class="kpi-progress-track"><div class="kpi-progress-fill" data-pct="${pct}"></div></div>` : ""}
     </div>`;
          })
          .join("");
        document
          .querySelectorAll(".kpi-num")
          .forEach((el) => animateValue(el, el.dataset.value));
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            document
              .querySelectorAll(".kpi-progress-fill")
              .forEach((el) => (el.style.width = el.dataset.pct + "%"));
          }),
        );

        // Plain-language report summary — reuses stats already computed by the backend
        document.getElementById("reportContent").innerHTML = generateReport(
          an,
          cr,
          FILENAME,
          activeTable,
        );

        // Cleaning chips
        const steps = cr.steps || [];
        document.getElementById("cleanChips").innerHTML = steps.length
          ? steps.map((s) => `<span class="clean-chip">✓ ${s}</span>`).join("")
          : `<span class="no-issues">✨ Data was already clean — no steps needed</span>`;

        // Columns deliberately excluded from charts/KPIs (identifiers, too-high-cardinality text)
        const excluded = an.summary?.excluded_columns || [];
        const excBlock = document.getElementById("excludedBlock");
        if (excluded.length) {
          excBlock.style.display = "";
          document.getElementById("excludedChips").innerHTML = excluded
            .map(
              (e) =>
                `<span class="clean-chip" title="${e.reason}" style="cursor:help">${e.column}</span>`,
            )
            .join("");
        } else {
          excBlock.style.display = "none";
        }

        // Quality gauge + issues
        renderQuality(an);

        buildCharts(an.charts || []);

        // Preview
        const p = an.preview;
        document.getElementById("tableHead").innerHTML =
          `<tr>${p.columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
        document.getElementById("tableBody").innerHTML = p.rows
          .map(
            (row) =>
              `<tr>${row.map((v) => `<td>${v === null || v === "" ? '<span style="color:var(--text-dim)">—</span>' : String(v).slice(0, 80)}</td>`).join("")}</tr>`,
          )
          .join("");
        document.getElementById("previewCount").textContent =
          `${p.showing ?? p.rows.length} of ${p.total_rows ?? p.rows.length} rows`;

        applySearchFilter();
      }

      // ── Quality gauge — reads the "Quality Score" KPI (e.g. "92/100") and draws
      // a radial arc gauge, the recurring widget across the reference dashboards.
      function renderQuality(an) {
        const gaugeEl = document.getElementById("qualityGauge");
        gaugeEl.innerHTML = "";
        const scoreKpi = (an.kpis || []).find(
          (k) => k.label === "Quality Score",
        );
        let score = 0;
        if (scoreKpi) {
          const m = String(scoreKpi.value).match(/(\d+)/);
          if (m) score = +m[1];
        }

        const W = 160,
          H = 110,
          r = 64,
          cx = W / 2,
          cy = 76;
        const svg = d3
          .select(gaugeEl)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const arcBg = d3
          .arc()
          .innerRadius(r - 12)
          .outerRadius(r)
          .startAngle(-Math.PI / 2)
          .endAngle(Math.PI / 2);
        const arcFg = d3
          .arc()
          .innerRadius(r - 12)
          .outerRadius(r)
          .startAngle(-Math.PI / 2);
        const g = svg.append("g").attr("transform", `translate(${cx},${cy})`);
        g.append("path").attr("d", arcBg).attr("fill", "var(--accent-soft)");
        const fg = g.append("path").attr("fill", "var(--accent)");
        const target = -Math.PI / 2 + (score / 100) * Math.PI;
        fg.transition()
          .duration(800)
          .attrTween("d", function () {
            const i = d3.interpolate(-Math.PI / 2, target);
            return (t) => {
              arcFg.endAngle(i(t));
              return arcFg();
            };
          });
        g.append("text")
          .attr("text-anchor", "middle")
          .attr("y", -6)
          .attr("font-size", 22)
          .attr("font-weight", 800)
          .attr("fill", "var(--text)")
          .text(score + "%");
        g.append("text")
          .attr("text-anchor", "middle")
          .attr("y", 14)
          .attr("font-size", 10)
          .attr("fill", "var(--text-dim)")
          .text("quality score");

        const issues = an.quality?.issues || [];
        document.getElementById("qualityChips").innerHTML = issues.length
          ? issues
              .slice(0, 6)
              .map(
                (i) =>
                  `<span class="issue-chip issue-${i.severity}">${i.col === "_dataset" ? "" : i.col + ": "}${i.issue}</span>`,
              )
              .join("")
          : `<span class="no-issues">No data quality issues found</span>`;
      }

      // ── Chart dispatch ─────────────────────────────────────────────────────────
      const CHART_RENDERERS = {
        histogram: (el, c, color) => drawHistogram(el, c.data, color),
        bar: (el, c, color) => drawBar(el, c.data, color),
        donut: (el, c) => drawDonut(el, c.data),
        scatter: (el, c, color) =>
          drawScatter(el, c.data.points, c.x_col, c.y_col, color),
        bubble: (el, c, color) =>
          drawBubble(el, c.data, c.x_col, c.y_col, c.z_col, color),
        line: (el, c, color) =>
          drawLine(el, c.data, c.value_col || c.column, false, color),
        area: (el, c, color) => drawLine(el, c.data, c.value_col, true, color),
        heatmap: (el, c) => drawCorr(el, c.data),
        box: (el, c, color) =>
          drawBox(el, [{ group: c.column, ...c.data }], color),
        grouped_box: (el, c, color) => drawBox(el, c.data, color),
        grouped_bar: (el, c) => drawGroupedBar(el, c.data),
        stacked_bar: (el, c) => drawStackedBar(el, c.data),
        treemap: (el, c) => drawTreemap(el, c.data),
        pareto: (el, c, color) => drawPareto(el, c.data, color),
        missing_bar: (el, c) => drawMissing(el, c.data),
      };

      function buildCharts(charts) {
        const grid = document.getElementById("chartsGrid");
        grid.innerHTML = "";
        if (!charts.length) {
          grid.innerHTML = `<div class="card c-12"><div class="chart-empty">No chart data available for this dataset</div></div>`;
          return;
        }
        charts.forEach((c, i) => {
          const renderer = CHART_RENDERERS[c.type];
          if (!renderer) return;
          const color = PAL[i % PAL.length];
          const card = document.createElement("div");
          card.className = `card chart-card enter ${CHART_SPAN[c.type] || "c-6"}`;
          card.style.animationDelay = `${Math.min(i, 10) * 0.05}s`;
          card.innerHTML = `<div class="chart-head"><span class="chart-dot" style="background:${color}"></span><span class="chart-title-text">${c.title}</span>${c.summary ? '<span class="chart-info-icon" tabindex="0">i</span>' : ""}</div><div id="ch-${i}"></div>${c.summary ? `<div class="chart-summary-overlay"><div class="chart-summary-text">${c.summary}</div></div>` : ""}`;
          grid.appendChild(card);
          // Reveal the summary only when the "i" badge itself is hovered/focused —
          // not the whole card — so the chart underneath stays visible by default.
          const infoIcon = card.querySelector(".chart-info-icon");
          const overlay = card.querySelector(".chart-summary-overlay");
          if (infoIcon && overlay) {
            const show = () => overlay.classList.add("show");
            const hide = () => overlay.classList.remove("show");
            infoIcon.addEventListener("mouseenter", show);
            infoIcon.addEventListener("mouseleave", hide);
            infoIcon.addEventListener("focus", show);
            infoIcon.addEventListener("blur", hide);
          }
          try {
            renderer(document.getElementById(`ch-${i}`), c, color);
          } catch (e) {
            document.getElementById(`ch-${i}`).innerHTML =
              `<div class="chart-empty">Couldn't render this chart</div>`;
            console.error(c.type, e);
          }
        });
      }

      // ── D3 chart functions ─────────────────────────────────────────────────────
      function axisStyle(sel) {
        sel.select(".domain").remove();
        sel
          .selectAll(".tick line")
          .attr("stroke", "var(--border)")
          .attr("stroke-dasharray", "3,3");
        sel
          .selectAll("text")
          .attr("fill", "var(--text-dim)")
          .attr("font-size", 10);
      }
      function axisStyleBottom(sel) {
        sel.select(".domain").attr("stroke", "var(--border)");
        sel
          .selectAll("text")
          .attr("fill", "var(--text-dim)")
          .attr("font-size", 10);
      }

      function drawHistogram(el, data, color) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 400,
          H = 200,
          m = { top: 8, right: 14, bottom: 32, left: 44 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleLinear()
          .domain([data[0].x0, data.at(-1).x1])
          .range([0, w]);
        const y = d3
          .scaleLinear()
          .domain([0, d3.max(data, (d) => d.count)])
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("~s")))
          .call(axisStyleBottom);
        const bw = Math.max(1, x(data[0].x1) - x(data[0].x0) - 2);
        g.selectAll("rect")
          .data(data)
          .join("rect")
          .attr("x", (d) => x(d.x0))
          .attr("y", h)
          .attr("width", bw)
          .attr("height", 0)
          .attr("fill", color)
          .attr("opacity", 0.85)
          .attr("rx", 3)
          .on("mouseover", (ev, d) =>
            tip(
              ev,
              `${d.x0.toFixed(2)} – ${d.x1.toFixed(2)}<br/>Count: ${d.count}`,
            ),
          )
          .on("mouseout", untip)
          .transition()
          .duration(600)
          .delay((_, i) => i * 12)
          .attr("y", (d) => y(d.count))
          .attr("height", (d) => h - y(d.count));
      }

      function drawDonut(el, pie) {
        const W = el.offsetWidth || 260,
          H = 220,
          r = Math.min(W, H) / 2 - 16;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${W / 2},${H / 2})`);
        const arc = d3
          .arc()
          .innerRadius(r * 0.6)
          .outerRadius(r);
        const pie2 = d3
          .pie()
          .value((d) => d.value)
          .sort(null);
        g.selectAll("path")
          .data(pie2(pie.slices))
          .join("path")
          .attr("d", arc)
          .attr("fill", (_, i) => PAL[i % PAL.length])
          .attr("stroke", "var(--card-bg)")
          .attr("stroke-width", 2)
          .attr("opacity", 0)
          .on("mouseover", (ev, d) =>
            tip(ev, `${d.data.label}<br/>${d.data.value} (${d.data.pct}%)`),
          )
          .on("mouseout", untip)
          .transition()
          .duration(700)
          .delay((_, i) => i * 55)
          .attr("opacity", 1)
          .attrTween("d", function (d) {
            const i = d3.interpolate({ startAngle: 0, endAngle: 0 }, d);
            return (t) => arc(i(t));
          });
        g.append("text")
          .text(pie.slices.length)
          .attr("text-anchor", "middle")
          .attr("dy", "-.1em")
          .attr("fill", "var(--text)")
          .attr("font-size", 22)
          .attr("font-weight", 800);
        g.append("text")
          .text("groups")
          .attr("text-anchor", "middle")
          .attr("dy", "1.3em")
          .attr("fill", "var(--text-dim)")
          .attr("font-size", 9);
        const leg = document.createElement("div");
        leg.className = "legend";
        leg.innerHTML = pie.slices
          .slice(0, 6)
          .map(
            (s, i) =>
              `<div class="legend-item"><div class="legend-dot" style="background:${PAL[i % PAL.length]}"></div>${s.label} (${s.pct}%)</div>`,
          )
          .join("");
        el.appendChild(leg);
      }

      function drawBar(el, data, color) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 400,
          H = 210,
          m = { top: 8, right: 14, bottom: 56, left: 46 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleBand()
          .domain(data.map((d) => d.label))
          .range([0, w])
          .padding(0.28);
        const y = d3
          .scaleLinear()
          .domain([0, d3.max(data, (d) => d.value)])
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x))
          .call((a) => {
            axisStyleBottom(a);
            a.selectAll("text")
              .attr("transform", "rotate(-35)")
              .attr("text-anchor", "end");
          });
        g.selectAll("rect")
          .data(data)
          .join("rect")
          .attr("x", (d) => x(d.label))
          .attr("y", h)
          .attr("width", x.bandwidth())
          .attr("height", 0)
          .attr("fill", (_, i) => PAL[i % PAL.length])
          .attr("rx", 4)
          .on("mouseover", (ev, d) =>
            tip(
              ev,
              `${d.label}<br/>Count: ${d.value}${d.pct !== undefined ? ` (${d.pct}%)` : ""}`,
            ),
          )
          .on("mouseout", untip)
          .transition()
          .duration(600)
          .delay((_, i) => i * 35)
          .attr("y", (d) => y(d.value))
          .attr("height", (d) => h - y(d.value));
      }

      function drawScatter(el, pts, xCol, yCol, color) {
        if (!pts?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 400,
          H = 240,
          m = { top: 8, right: 16, bottom: 34, left: 48 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleLinear()
          .domain(d3.extent(pts, (d) => d.x))
          .nice()
          .range([0, w]);
        const y = d3
          .scaleLinear()
          .domain(d3.extent(pts, (d) => d.y))
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("~s")))
          .call(axisStyleBottom);
        if (pts.length > 2) {
          const xm = d3.mean(pts, (d) => d.x),
            ym = d3.mean(pts, (d) => d.y),
            num = pts.reduce((a, d) => a + (d.x - xm) * (d.y - ym), 0),
            den = pts.reduce((a, d) => a + (d.x - xm) ** 2, 0),
            m2 = den ? num / den : 0,
            b = ym - m2 * xm,
            [x1, x2] = x.domain();
          g.append("line")
            .attr("x1", x(x1))
            .attr("y1", y(m2 * x1 + b))
            .attr("x2", x(x2))
            .attr("y2", y(m2 * x2 + b))
            .attr("stroke", "var(--negative)")
            .attr("stroke-width", 1.5)
            .attr("stroke-dasharray", "6,4")
            .attr("opacity", 0.5);
        }
        g.selectAll("circle")
          .data(pts)
          .join("circle")
          .attr("cx", (d) => x(d.x))
          .attr("cy", (d) => y(d.y))
          .attr("r", 0)
          .attr("fill", color)
          .attr("opacity", 0.65)
          .on("mouseover", (ev, d) =>
            tip(ev, `${xCol}: ${d.x}<br/>${yCol}: ${d.y}`),
          )
          .on("mouseout", untip)
          .transition()
          .duration(500)
          .delay((_, i) => i * 2)
          .attr("r", 4);
      }

      function drawBubble(el, pts, xCol, yCol, zCol, color) {
        if (!pts?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 400,
          H = 250,
          m = { top: 8, right: 16, bottom: 34, left: 48 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleLinear()
          .domain(d3.extent(pts, (d) => d.x))
          .nice()
          .range([0, w]);
        const y = d3
          .scaleLinear()
          .domain(d3.extent(pts, (d) => d.y))
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("~s")))
          .call(axisStyleBottom);
        g.selectAll("circle")
          .data(pts)
          .join("circle")
          .attr("cx", (d) => x(d.x))
          .attr("cy", (d) => y(d.y))
          .attr("r", 0)
          .attr("fill", color)
          .attr("opacity", 0.5)
          .on("mouseover", (ev, d) =>
            tip(ev, `${xCol}: ${d.x}<br/>${yCol}: ${d.y}<br/>${zCol}: ${d.z}`),
          )
          .on("mouseout", untip)
          .transition()
          .duration(500)
          .delay((_, i) => i * 3)
          .attr("r", (d) => d.r);
      }

      function drawLine(el, data, valueLabel, area, color) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const isDate = data[0].date !== undefined;
        const pts = isDate
          ? data
              .map((d) => ({ key: new Date(d.date), value: d.value }))
              .filter((d) => !isNaN(d.key))
          : data.map((d) => ({ key: d.index, value: d.value }));
        if (pts.length < 2) {
          el.innerHTML = '<div class="chart-empty">Insufficient data</div>';
          return;
        }
        const W = el.offsetWidth || 420,
          H = 210,
          m = { top: 8, right: 16, bottom: 32, left: 48 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = isDate
          ? d3
              .scaleTime()
              .domain(d3.extent(pts, (d) => d.key))
              .range([0, w])
          : d3
              .scaleLinear()
              .domain(d3.extent(pts, (d) => d.key))
              .range([0, w]);
        const y = d3
          .scaleLinear()
          .domain(d3.extent(pts, (d) => d.value))
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x).ticks(6))
          .call(axisStyleBottom);
        if (area) {
          const gid = "ag" + Math.random().toString(36).slice(2);
          const grad = svg
            .append("defs")
            .append("linearGradient")
            .attr("id", gid)
            .attr("x1", 0)
            .attr("y1", 0)
            .attr("x2", 0)
            .attr("y2", 1);
          grad
            .append("stop")
            .attr("offset", "0%")
            .attr("stop-color", color)
            .attr("stop-opacity", 0.35);
          grad
            .append("stop")
            .attr("offset", "100%")
            .attr("stop-color", color)
            .attr("stop-opacity", 0);
          g.append("path")
            .datum(pts)
            .attr("fill", `url(#${gid})`)
            .attr(
              "d",
              d3
                .area()
                .x((d) => x(d.key))
                .y0(h)
                .y1((d) => y(d.value))
                .curve(d3.curveMonotoneX),
            );
        }
        const path = g
          .append("path")
          .datum(pts)
          .attr("fill", "none")
          .attr("stroke", color)
          .attr("stroke-width", 2.2)
          .attr(
            "d",
            d3
              .line()
              .x((d) => x(d.key))
              .y((d) => y(d.value))
              .curve(d3.curveMonotoneX),
          );
        const len = path.node().getTotalLength();
        path
          .attr("stroke-dasharray", len)
          .attr("stroke-dashoffset", len)
          .transition()
          .duration(1100)
          .attr("stroke-dashoffset", 0);
        const dot = g
          .append("circle")
          .attr("r", 5)
          .attr("fill", color)
          .attr("stroke", "var(--card-bg)")
          .attr("stroke-width", 2)
          .style("display", "none");
        const bisect = d3.bisector((d) => d.key).left;
        svg
          .on("mousemove", (ev) => {
            const [mx] = d3.pointer(ev, g.node()),
              xv = x.invert(mx),
              i = Math.min(bisect(pts, xv, 1), pts.length - 1),
              d = pts[i];
            dot
              .style("display", null)
              .attr("cx", x(d.key))
              .attr("cy", y(d.value));
            tip(
              ev,
              `${isDate ? d.key.toISOString().slice(0, 10) : d.key}<br/>${valueLabel || "value"}: ${d.value.toFixed ? d.value.toFixed(3) : d.value}`,
            );
          })
          .on("mouseleave", () => {
            dot.style("display", "none");
            untip();
          });
      }

      function drawCorr(el, corr) {
        const cols = corr.columns,
          n = cols.length,
          cs = Math.min(44, Math.floor((el.offsetWidth - 80) / n));
        const W = cs * n + 80,
          H = cs * n + 56;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg.append("g").attr("transform", "translate(64,20)");
        const color = d3
          .scaleSequential()
          .domain([-1, 1])
          .interpolator(d3.interpolateRgb("#EF4444", "#22C55E"));
        cols.forEach((col, i) => {
          corr.matrix[i].forEach((val, j) => {
            g.append("rect")
              .attr("x", j * cs)
              .attr("y", i * cs)
              .attr("width", cs - 2)
              .attr("height", cs - 2)
              .attr("rx", 3)
              .attr("fill", color(val))
              .attr("opacity", 0)
              .on("mouseover", (ev) =>
                tip(ev, `${cols[i]} × ${cols[j]}<br/>r = ${val.toFixed(3)}`),
              )
              .on("mouseout", untip)
              .transition()
              .duration(400)
              .delay((i * n + j) * 7)
              .attr("opacity", 0.85);
            if (cs >= 28)
              g.append("text")
                .text(val.toFixed(2))
                .attr("x", j * cs + cs / 2)
                .attr("y", i * cs + cs / 2 + 4)
                .attr("text-anchor", "middle")
                .attr("font-size", 9)
                .attr("fill", Math.abs(val) > 0.5 ? "#fff" : "#111");
          });
          g.append("text")
            .text(col.length > 8 ? col.slice(0, 7) + "…" : col)
            .attr("x", -6)
            .attr("y", i * cs + cs / 2 + 4)
            .attr("text-anchor", "end")
            .attr("font-size", 9)
            .attr("fill", "var(--text-dim)");
          g.append("text")
            .text(col.length > 8 ? col.slice(0, 7) + "…" : col)
            .attr("x", i * cs + cs / 2)
            .attr("y", -6)
            .attr("text-anchor", "middle")
            .attr("font-size", 9)
            .attr("fill", "var(--text-dim)")
            .attr("transform", `rotate(-35,${i * cs + cs / 2},-6)`);
        });
      }

      function drawBox(el, groups, color) {
        if (!groups?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 400,
          H = Math.max(150, groups.length * 52 + 36),
          m = { top: 10, right: 22, bottom: 20, left: 96 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const allVals = groups.flatMap((gr) => [gr.min, gr.max]);
        const x = d3
          .scaleLinear()
          .domain(d3.extent(allVals))
          .nice()
          .range([0, w]);
        const y = d3
          .scaleBand()
          .domain(groups.map((gr) => gr.group))
          .range([0, h])
          .padding(0.4);
        g.append("g")
          .call(d3.axisBottom(x).ticks(5).tickFormat(d3.format("~s")))
          .attr("transform", `translate(0,${h})`)
          .call(axisStyleBottom);
        g.selectAll(".lbl")
          .data(groups)
          .join("text")
          .attr("x", -10)
          .attr("y", (gr) => y(gr.group) + y.bandwidth() / 2 + 4)
          .attr("text-anchor", "end")
          .attr("font-size", 10)
          .attr("fill", "var(--text-dim)")
          .text((gr) => String(gr.group).slice(0, 14));
        const bh = y.bandwidth();
        groups.forEach((gr) => {
          const cy = y(gr.group) + bh / 2;
          g.append("line")
            .attr("x1", x(gr.min))
            .attr("x2", x(gr.max))
            .attr("y1", cy)
            .attr("y2", cy)
            .attr("stroke", "var(--border)")
            .attr("stroke-width", 1.5);
          g.append("rect")
            .attr("x", x(gr.q1))
            .attr("width", Math.max(1, x(gr.q3) - x(gr.q1)))
            .attr("y", cy - bh * 0.32)
            .attr("height", bh * 0.64)
            .attr("fill", color)
            .attr("opacity", 0.6)
            .attr("rx", 3)
            .on("mouseover", (ev) =>
              tip(
                ev,
                `${gr.group}<br/>Q1 ${gr.q1} · Median ${gr.median} · Q3 ${gr.q3}${gr.count ? `<br/>n=${gr.count}` : ""}`,
              ),
            )
            .on("mouseout", untip);
          g.append("line")
            .attr("x1", x(gr.median))
            .attr("x2", x(gr.median))
            .attr("y1", cy - bh * 0.32)
            .attr("y2", cy + bh * 0.32)
            .attr("stroke", "var(--text)")
            .attr("stroke-width", 2);
          (gr.outliers || [])
            .slice(0, 30)
            .forEach((o) =>
              g
                .append("circle")
                .attr("cx", x(o))
                .attr("cy", cy)
                .attr("r", 2.5)
                .attr("fill", "var(--negative)")
                .attr("opacity", 0.7),
            );
        });
      }

      function drawGroupedBar(el, data) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 420,
          H = 220,
          m = { top: 8, right: 14, bottom: 56, left: 52 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleBand()
          .domain(data.map((d) => d.label))
          .range([0, w])
          .padding(0.28);
        const y = d3
          .scaleLinear()
          .domain([0, d3.max(data, (d) => d.sum)])
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x))
          .call((a) => {
            axisStyleBottom(a);
            a.selectAll("text")
              .attr("transform", "rotate(-35)")
              .attr("text-anchor", "end");
          });
        g.selectAll("rect")
          .data(data)
          .join("rect")
          .attr("x", (d) => x(d.label))
          .attr("y", h)
          .attr("width", x.bandwidth())
          .attr("height", 0)
          .attr("fill", (_, i) => PAL[i % PAL.length])
          .attr("rx", 4)
          .on("mouseover", (ev, d) =>
            tip(
              ev,
              `${d.label}<br/>Sum: ${d.sum}<br/>Mean: ${d.mean}<br/>n=${d.count}`,
            ),
          )
          .on("mouseout", untip)
          .transition()
          .duration(600)
          .delay((_, i) => i * 35)
          .attr("y", (d) => y(d.sum))
          .attr("height", (d) => h - y(d.sum));
      }

      function drawStackedBar(el, sb) {
        if (!sb?.rows?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const labels = sb.labels,
          W = el.offsetWidth || 460,
          H = 240,
          m = { top: 8, right: 14, bottom: 56, left: 48 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleBand()
          .domain(sb.rows.map((r) => r.label))
          .range([0, w])
          .padding(0.28);
        const totals = sb.rows.map((r) =>
          labels.reduce((a, l) => a + (r[l] || 0), 0),
        );
        const y = d3
          .scaleLinear()
          .domain([0, d3.max(totals)])
          .nice()
          .range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x))
          .call((a) => {
            axisStyleBottom(a);
            a.selectAll("text")
              .attr("transform", "rotate(-35)")
              .attr("text-anchor", "end");
          });
        sb.rows.forEach((r) => {
          let acc = 0;
          labels.forEach((l, li) => {
            const v = r[l] || 0;
            g.append("rect")
              .attr("x", x(r.label))
              .attr("width", x.bandwidth())
              .attr("y", y(acc))
              .attr("height", 0)
              .attr("fill", PAL[li % PAL.length])
              .attr("opacity", 0.85)
              .on("mouseover", (ev) => tip(ev, `${r.label}<br/>${l}: ${v}`))
              .on("mouseout", untip)
              .transition()
              .duration(600)
              .delay(li * 40)
              .attr("y", y(acc + v))
              .attr("height", Math.max(0, y(acc) - y(acc + v)));
            acc += v;
          });
        });
        const leg = document.createElement("div");
        leg.className = "legend";
        leg.innerHTML = labels
          .map(
            (l, i) =>
              `<div class="legend-item"><div class="legend-dot" style="background:${PAL[i % PAL.length]}"></div>${l}</div>`,
          )
          .join("");
        el.appendChild(leg);
      }

      function drawTreemap(el, data) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 460,
          H = 250;
        const root = d3.hierarchy({ children: data }).sum((d) => d.value);
        d3.treemap().size([W, H]).padding(2)(root);
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const nodes = svg
          .selectAll("g")
          .data(root.leaves())
          .join("g")
          .attr("transform", (d) => `translate(${d.x0},${d.y0})`);
        nodes
          .append("rect")
          .attr("width", (d) => d.x1 - d.x0)
          .attr("height", (d) => d.y1 - d.y0)
          .attr("fill", (_, i) => PAL[i % PAL.length])
          .attr("opacity", 0.85)
          .attr("rx", 4)
          .on("mouseover", (ev, d) =>
            tip(ev, `${d.data.label}<br/>${d.data.value} (${d.data.pct}%)`),
          )
          .on("mouseout", untip);
        nodes
          .filter((d) => d.x1 - d.x0 > 50 && d.y1 - d.y0 > 22)
          .append("text")
          .attr("x", 6)
          .attr("y", 18)
          .attr("font-size", 11)
          .attr("fill", "#fff")
          .text((d) =>
            d.data.label.length > 16
              ? d.data.label.slice(0, 15) + "…"
              : d.data.label,
          );
      }

      function drawPareto(el, data, color) {
        if (!data?.length) {
          el.innerHTML = '<div class="chart-empty">No data</div>';
          return;
        }
        const W = el.offsetWidth || 460,
          H = 230,
          m = { top: 8, right: 44, bottom: 56, left: 48 };
        const w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3
          .scaleBand()
          .domain(data.map((d) => d.label))
          .range([0, w])
          .padding(0.25);
        const y = d3
          .scaleLinear()
          .domain([0, d3.max(data, (d) => d.value)])
          .nice()
          .range([h, 0]);
        const y2 = d3.scaleLinear().domain([0, 100]).range([h, 0]);
        g.append("g")
          .call(
            d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(d3.format("~s")),
          )
          .call(axisStyle);
        g.append("g")
          .attr("transform", `translate(${w},0)`)
          .call(
            d3
              .axisRight(y2)
              .ticks(5)
              .tickFormat((d) => d + "%"),
          )
          .call(axisStyleBottom);
        g.append("g")
          .attr("transform", `translate(0,${h})`)
          .call(d3.axisBottom(x))
          .call((a) => {
            axisStyleBottom(a);
            a.selectAll("text")
              .attr("transform", "rotate(-35)")
              .attr("text-anchor", "end");
          });
        g.selectAll("rect")
          .data(data)
          .join("rect")
          .attr("x", (d) => x(d.label))
          .attr("width", x.bandwidth())
          .attr("y", h)
          .attr("height", 0)
          .attr("fill", color)
          .attr("opacity", 0.75)
          .attr("rx", 3)
          .on("mouseover", (ev, d) =>
            tip(
              ev,
              `${d.label}<br/>Count: ${d.value}<br/>Cumulative: ${d.cumulative_pct}%`,
            ),
          )
          .on("mouseout", untip)
          .transition()
          .duration(600)
          .delay((_, i) => i * 35)
          .attr("y", (d) => y(d.value))
          .attr("height", (d) => h - y(d.value));
        const line = d3
          .line()
          .x((d) => x(d.label) + x.bandwidth() / 2)
          .y((d) => y2(d.cumulative_pct))
          .curve(d3.curveMonotoneX);
        g.append("path")
          .datum(data)
          .attr("fill", "none")
          .attr("stroke", "var(--text)")
          .attr("stroke-width", 2)
          .attr("d", line);
        g.selectAll(".cumdot")
          .data(data)
          .join("circle")
          .attr("cx", (d) => x(d.label) + x.bandwidth() / 2)
          .attr("cy", (d) => y2(d.cumulative_pct))
          .attr("r", 3)
          .attr("fill", "var(--text)");
      }

      function drawMissing(el, missing) {
        const W = el.offsetWidth || 600,
          H = Math.max(80, missing.length * 32 + 36);
        const m = { top: 10, right: 60, bottom: 16, left: 150 },
          w = W - m.left - m.right,
          h = H - m.top - m.bottom;
        const svg = d3
          .select(el)
          .append("svg")
          .attr("width", W)
          .attr("height", H);
        const g = svg
          .append("g")
          .attr("transform", `translate(${m.left},${m.top})`);
        const x = d3.scaleLinear().domain([0, 100]).range([0, w]);
        const y = d3
          .scaleBand()
          .domain(missing.map((d) => d.column))
          .range([0, h])
          .padding(0.35);
        g.selectAll(".lbl")
          .data(missing)
          .join("text")
          .attr("x", -8)
          .attr("y", (d) => y(d.column) + y.bandwidth() / 2 + 4)
          .attr("text-anchor", "end")
          .attr("font-size", 11)
          .attr("fill", "var(--text-dim)")
          .text((d) => d.column);
        g.selectAll(".bg")
          .data(missing)
          .join("rect")
          .attr("x", 0)
          .attr("y", (d) => y(d.column))
          .attr("width", w)
          .attr("height", y.bandwidth())
          .attr("fill", "var(--accent-soft)")
          .attr("rx", 4);
        g.selectAll(".fill")
          .data(missing)
          .join("rect")
          .attr("x", 0)
          .attr("y", (d) => y(d.column))
          .attr("height", y.bandwidth())
          .attr("rx", 4)
          .attr("fill", "var(--negative)")
          .attr("opacity", 0.75)
          .attr("width", 0)
          .on("mouseover", (ev, d) =>
            tip(ev, `${d.column}: ${d.missing} missing (${d.pct}%)`),
          )
          .on("mouseout", untip)
          .transition()
          .duration(700)
          .delay((_, i) => i * 70)
          .attr("width", (d) => x(d.pct));
        g.selectAll(".pct")
          .data(missing)
          .join("text")
          .attr("y", (d) => y(d.column) + y.bandwidth() / 2 + 4)
          .attr("font-size", 10)
          .attr("fill", "var(--text)")
          .attr("x", 0)
          .attr("opacity", 0)
          .transition()
          .duration(700)
          .delay((_, i) => i * 70 + 250)
          .attr("x", (d) => x(d.pct) + 8)
          .attr("opacity", 1)
          .text((d) => `${d.pct}%`);
      }

      // ── Tooltip ────────────────────────────────────────────────────────────────
      function tip(ev, html) {
        tooltip.innerHTML = html;
        tooltip.classList.add("active");
        moveTip(ev);
      }
      function moveTip(ev) {
        tooltip.style.left = `${Math.min(ev.clientX + 14, window.innerWidth - 180)}px`;
        tooltip.style.top = `${ev.clientY - 10}px`;
      }
      function untip() {
        tooltip.classList.remove("active");
      }
      document.addEventListener("mousemove", (ev) => {
        if (tooltip.classList.contains("active")) moveTip(ev);
      });

      // ── Init ─────────────────────────────────────────────────────────────────
      (function init() {
        const tables = APP_DATA.tables || [];
        if (!tables.length) return;

        document.getElementById("tableTabs").innerHTML = tables
          .map(
            (t, i) =>
              `<button class="tab-btn ${i === 0 ? "active" : ""}" onclick="switchTable('${t}',this)">${t}</button>`,
          )
          .join("");

        activeTable = tables[0];
        renderTableData(APP_DATA.results[activeTable]);
      })();
