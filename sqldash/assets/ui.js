// Dashboard UI: filters, KPI tiles, hand-drawn SVG charts, tooltips, CSV export.
(function () {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const money2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const num = new Intl.NumberFormat("en-US");
  const short = (v) => {
    const a = Math.abs(v);
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return "$" + (v / 1e3).toFixed(a >= 1e5 ? 0 : 1) + "k";
    return "$" + Math.round(v);
  };
  const pct = (v) => (v === null || v === undefined ? "–" : v.toFixed(1) + "%");
  const monthLabel = (key) => {
    const [y, m] = key.split("-");
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m - 1] + " " + y.slice(2);
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- tooltip ----------
  const tip = $("tip");
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 14;
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  // ---------- svg helpers ----------
  function svg(w, h) {
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", `0 0 ${w} ${h}`);
    s.setAttribute("role", "img");
    return s;
  }
  function el(parent, tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    parent.appendChild(e);
    return e;
  }
  // bar with 4px rounded data-end, square at the baseline
  function vbarPath(x, y, w, h) {
    const r = Math.min(4, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function hbarPath(x, y, w, h) {
    const r = Math.min(4, h / 2, w);
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }
  function niceMax(v) {
    if (v <= 0) return 1;
    const p = 10 ** Math.floor(Math.log10(v));
    for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  function empty(target, msg) {
    target.innerHTML = `<p class="note">${msg || "No data for these filters."}</p>`;
  }

  // ---------- charts ----------
  function trendChart(target, monthly) {
    target.innerHTML = "";
    if (!monthly.length) return empty(target);
    const W = 1000, H = 290, L = 58, R = 10, T = 10, B = 28;
    const s = svg(W, H);
    s.setAttribute("aria-label", "Monthly invoiced revenue (bars) and cash collected (line)");
    const max = niceMax(Math.max(...monthly.map((m) => Math.max(m.revenue, m.collections))));
    const y = (v) => T + (H - T - B) * (1 - Math.max(v, 0) / max);
    const band = (W - L - R) / monthly.length;
    for (let i = 0; i <= 4; i++) {
      const v = (max * i) / 4;
      el(s, "line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: i ? "grid-line" : "base-line" });
      el(s, "text", { x: L - 8, y: y(v) + 4, "text-anchor": "end" }, short(v));
    }
    const step = Math.ceil(monthly.length / 12);
    monthly.forEach((m, i) => {
      const bw = Math.max(2, band * 0.62);
      const x = L + i * band + (band - bw) / 2;
      el(s, "path", { d: vbarPath(x, y(m.revenue), bw, y(0) - y(m.revenue)), fill: "var(--series-1)" });
      if (i % step === 0) el(s, "text", { x: L + i * band + band / 2, y: H - 8, "text-anchor": "middle" }, monthLabel(m.month_key));
    });
    const pts = monthly.map((m, i) => `${L + i * band + band / 2},${y(m.collections)}`).join(" ");
    el(s, "polyline", { points: pts, fill: "none", stroke: "var(--series-2)", "stroke-width": 2, "stroke-linejoin": "round" });
    const dot = el(s, "circle", { r: 5, fill: "var(--series-2)", stroke: "var(--surface)", "stroke-width": 2, opacity: 0 });
    const cross = el(s, "line", { y1: T, y2: H - B, class: "hl" });
    monthly.forEach((m, i) => {
      const cx = L + i * band + band / 2;
      const hit = el(s, "rect", { x: L + i * band, y: T, width: band, height: H - T - B, class: "hit" });
      hit.addEventListener("mousemove", (evt) => {
        cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.classList.add("on");
        dot.setAttribute("cx", cx); dot.setAttribute("cy", y(m.collections)); dot.setAttribute("opacity", 1);
        showTip(evt, `<b>${monthLabel(m.month_key)}</b>Revenue ${money.format(m.revenue)}<br>Collections ${money.format(m.collections)}<br>Gross margin ${money.format(m.gross_margin)}<br>${num.format(m.orders)} orders &middot; ${num.format(m.active_customers)} customers`);
      });
      hit.addEventListener("mouseleave", () => { cross.classList.remove("on"); dot.setAttribute("opacity", 0); hideTip(); });
    });
    target.appendChild(s);
  }

  function hbarChart(target, items, opts) {
    target.innerHTML = "";
    if (!items.length) return empty(target);
    const W = 600, rowH = 28, L = opts.labelWidth || 170, R = 120, T = 4;
    const H = T + items.length * rowH + 4;
    const s = svg(W, H);
    s.setAttribute("aria-label", opts.aria);
    const max = Math.max(...items.map((d) => d.revenue), 1);
    items.forEach((d, i) => {
      const yy = T + i * rowH;
      const w = Math.max(0, ((W - L - R) * d.revenue) / max);
      el(s, "text", { x: L - 8, y: yy + rowH / 2 + 4, "text-anchor": "end", class: "lbl" }, opts.label(d));
      el(s, "path", { d: hbarPath(L, yy + 5, Math.max(w, 1), rowH - 10), fill: "var(--series-1)" });
      el(s, "text", { x: L + w + 6, y: yy + rowH / 2 + 4, class: "val" }, opts.value(d));
      const hit = el(s, "rect", { x: 0, y: yy, width: W, height: rowH, class: "hit" });
      hit.addEventListener("mousemove", (evt) => showTip(evt, opts.tip(d)));
      hit.addEventListener("mouseleave", hideTip);
    });
    el(s, "line", { x1: L, x2: L, y1: T, y2: H - 4, class: "base-line" });
    target.appendChild(s);
  }

  function agingChart(target, aging) {
    target.innerHTML = "";
    if (!aging.length) return empty(target, "No unpaid invoices for these filters.");
    const W = 600, H = 250, L = 10, R = 10, T = 30, B = 40;
    const s = svg(W, H);
    s.setAttribute("aria-label", "Outstanding receivables by aging bucket");
    const max = Math.max(...aging.map((a) => a.outstanding));
    const band = (W - L - R) / 5;
    el(s, "line", { x1: L, x2: W - R, y1: H - B, y2: H - B, class: "base-line" });
    aging.forEach((a) => {
      const i = a.bucket_order - 1;
      const h = ((H - T - B) * a.outstanding) / max;
      const bw = band * 0.6;
      const x = L + i * band + (band - bw) / 2;
      el(s, "path", { d: vbarPath(x, H - B - h, bw, Math.max(h, 1)), fill: `var(--age-${a.bucket_order})` });
      el(s, "text", { x: x + bw / 2, y: H - B - h - 8, "text-anchor": "middle", class: "val" }, `${short(a.outstanding)} · ${pct(a.pct_of_total)}`);
      el(s, "text", { x: x + bw / 2, y: H - B + 16, "text-anchor": "middle", class: "lbl" }, a.aging_bucket);
      el(s, "text", { x: x + bw / 2, y: H - B + 31, "text-anchor": "middle" }, `${a.open_invoices} invoices`);
      const hit = el(s, "rect", { x: L + i * band, y: T - 20, width: band, height: H - T - B + 20, class: "hit" });
      hit.addEventListener("mousemove", (evt) => showTip(evt, `<b>${a.aging_bucket}</b>${money2.format(a.outstanding)} outstanding<br>${a.open_invoices} open invoices<br>${pct(a.pct_of_total)} of receivables`));
      hit.addEventListener("mouseleave", hideTip);
    });
    target.appendChild(s);
  }

  const HEAT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
  function cohortTable(target, cohorts) {
    if (!cohorts.length) return empty(target);
    const maxK = 12;
    const byCohort = new Map();
    for (const c of cohorts) {
      if (!byCohort.has(c.cohort_month)) byCohort.set(c.cohort_month, { size: c.cohort_size, cells: {} });
      byCohort.get(c.cohort_month).cells[c.months_since_first] = c;
    }
    let html = `<table><thead><tr><th class="lab">Cohort</th><th>Size</th>`;
    for (let k = 1; k <= maxK; k++) html += `<th>+${k}</th>`;
    html += "</tr></thead><tbody>";
    for (const [month, row] of byCohort) {
      html += `<tr><td class="lab">${monthLabel(month)}</td><td class="lab" style="text-align:right">${row.size}</td>`;
      for (let k = 1; k <= maxK; k++) {
        const c = row.cells[k];
        const monthsAvailable = DATA.months.length - 1 - DATA.months.indexOf(month);
        if (k > monthsAvailable) { html += "<td></td>"; continue; }
        const v = c ? c.retention_pct : 0;
        const step = Math.min(HEAT.length - 1, Math.floor(v / 15));
        const cls = step >= 3 ? "c-dark" : "c-light";
        const title = `${monthLabel(month)} cohort: ${c ? c.active_customers : 0} of ${row.size} customers ordered ${k} month(s) later`;
        html += `<td class="${cls}" style="background:${HEAT[step]}" title="${esc(title)}">${Math.round(v)}</td>`;
      }
      html += "</tr>";
    }
    target.innerHTML = html + "</tbody></table>";
  }

  function tiles(target, h) {
    const dqFails = DQ.reduce((a, d) => a + d.failing_rows, 0);
    const dqChecks = DQ.filter((d) => d.failing_rows > 0).length;
    const items = [
      ["Revenue", money.format(h.revenue), "invoiced, completed orders"],
      ["Gross margin", pct(h.gross_margin_pct), money.format(h.gross_margin)],
      ["Orders", num.format(h.orders), ""],
      ["Active customers", num.format(h.active_customers), "placed an order"],
      ["Avg order value", h.avg_order_value === null ? "–" : money2.format(h.avg_order_value), ""],
      ["Receivables", money.format(h.ar_outstanding), "unpaid, as of " + REPORT_DATE],
      ["Overdue", pct(h.ar_overdue_pct), money.format(h.ar_overdue) + " past due date"],
      ["Data issues", num.format(dqFails), `rows failing ${dqChecks} of ${DQ.length} checks`],
    ];
    target.innerHTML = items.map(([k, v, d]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join("");
  }

  function dqTable(target) {
    let html = "<table><thead><tr><th>Check</th><th>Severity</th><th>Rows</th></tr></thead><tbody>";
    for (const d of DQ) {
      const status = d.failing_rows
        ? `<span class="bad-${d.severity}">${d.severity === "error" ? "✕" : "!"} ${d.failing_rows}</span>`
        : `<span class="ok">✓ 0</span>`;
      html += `<tr><td class="txt" title="${esc(d.check_name)}">${esc(d.description)}</td><td>${d.severity}</td><td>${status}</td></tr>`;
    }
    target.innerHTML = html + "</tbody></table>";
  }

  function monthTable(target, monthly) {
    if (!monthly.length) return empty(target);
    let html = "<table><thead><tr><th>Month</th><th>Orders</th><th>Customers</th><th>Revenue</th><th>Margin</th><th>AOV</th><th>Collected</th></tr></thead><tbody>";
    for (const m of monthly) {
      html += `<tr><td>${monthLabel(m.month_key)}</td><td>${num.format(m.orders)}</td><td>${num.format(m.active_customers)}</td><td>${money.format(m.revenue)}</td><td>${money.format(m.gross_margin)}</td><td>${money2.format(m.avg_order_value)}</td><td>${money.format(m.collections)}</td></tr>`;
    }
    target.innerHTML = html + "</tbody></table>";
  }

  // ---------- filters ----------
  function fill(select, labels, withAll) {
    select.innerHTML = (withAll ? `<option value="-1">All</option>` : "") + labels.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
  }
  fill($("f-from"), DATA.months.map(monthLabel));
  fill($("f-to"), DATA.months.map(monthLabel));
  fill($("f-region"), DATA.regions, true);
  fill($("f-segment"), DATA.segments, true);
  fill($("f-category"), DATA.categories, true);

  function reset() {
    $("f-from").value = 0;
    $("f-to").value = DATA.months.length - 1;
    for (const id of ["f-region", "f-segment", "f-category"]) $(id).value = -1;
  }

  let view;
  function render() {
    let from = +$("f-from").value, to = +$("f-to").value;
    if (from > to) { [from, to] = [to, from]; $("f-from").value = from; $("f-to").value = to; }
    view = computeView(DATA, { from, to, region: +$("f-region").value, segment: +$("f-segment").value, category: +$("f-category").value });
    tiles($("tiles"), view.headline);
    trendChart($("c-trend"), view.monthly);
    hbarChart($("c-region"), view.regions, {
      aria: "Revenue by region", labelWidth: 90,
      label: (d) => d.region_name,
      value: (d) => `${short(d.revenue)} · ${pct(d.revenue_share_pct)}`,
      tip: (d) => `<b>${esc(d.region_name)}</b>Revenue ${money.format(d.revenue)}<br>${pct(d.revenue_share_pct)} of total<br>${num.format(d.orders)} orders &middot; ${num.format(d.active_customers)} customers`,
    });
    hbarChart($("c-products"), view.products.slice(0, 10), {
      aria: "Top 10 products by revenue", labelWidth: 190,
      label: (d) => (d.product_name.length > 28 ? d.product_name.slice(0, 27) + "…" : d.product_name),
      value: (d) => `${short(d.revenue)} · ${pct(d.revenue ? (100 * d.gross_margin) / d.revenue : 0)}`,
      tip: (d) => `<b>${esc(d.product_name)}</b>${esc(d.category)}<br>Revenue ${money.format(d.revenue)}<br>Margin ${money.format(d.gross_margin)}<br>${num.format(d.units)} units`,
    });
    agingChart($("c-aging"), view.aging);
    cohortTable($("c-cohort"), view.cohorts);
    monthTable($("c-table"), view.monthly);
  }

  function download(name, rows) {
    const blob = new Blob([toCSV(rows)], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  for (const id of ["f-from", "f-to", "f-region", "f-segment", "f-category"]) $(id).addEventListener("change", render);
  $("f-reset").addEventListener("click", () => { reset(); render(); });
  document.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => {
    const kind = b.dataset.export;
    download(`${kind}.csv`, view[kind]);
  }));

  dqTable($("c-dq"));
  reset();
  render();
})();
