// Pure KPI maths for the dashboard filters. No DOM here, so Node can run it in
// tests and prove the numbers match the SQL views exactly.
//
// data (built by sqldash/dashboard.py from the SQL views):
//   months[], regions[], segments[], categories[], products[[name, catIdx]]
//   orders[[orderId, orderDate, monthIdx, customerId, regionIdx, segmentIdx, revenue, cost]]   (completed only)
//   lines[[orderPos, productIdx, quantity, revenue, cost]]
//   payments[[monthIdx, regionIdx, segmentIdx, amount]]
//   invoices[[orderId, customerId, regionIdx, segmentIdx, dueDate, outstanding, daysPastDue]]  (open, as of report date)
// filters: {from, to, region, segment, category}; -1 means "all".

const AGING = [
  [1, "Not yet due", (d) => d <= 0],
  [2, "1-30 days", (d) => d <= 30],
  [3, "31-60 days", (d) => d <= 60],
  [4, "61-90 days", (d) => d <= 90],
  [5, "90+ days", () => true],
];

function round(x, places) {
  const f = 10 ** places;
  return Math.round((x + Number.EPSILON) * f) / f;
}

function linesByOrder(data) {
  if (!data._linesByOrder) {
    const idx = data.orders.map(() => []);
    for (const l of data.lines) idx[l[0]].push(l);
    data._linesByOrder = idx;
  }
  return data._linesByOrder;
}

function allFilters(data) {
  return { from: 0, to: data.months.length - 1, region: -1, segment: -1, category: -1 };
}

function computeView(data, filters) {
  const f = Object.assign(allFilters(data), filters || {});
  const inScope = (r, s) => (f.region < 0 || r === f.region) && (f.segment < 0 || s === f.segment);
  const byOrder = linesByOrder(data);

  // Orders in scope, with revenue/cost limited to the chosen category.
  const picked = [];
  data.orders.forEach((o, pos) => {
    const [orderId, orderDate, m, cust, r, s, rev, cost] = o;
    if (!inScope(r, s) || m < f.from || m > f.to) return;
    if (f.category < 0) {
      picked.push({ pos, orderId, orderDate, m, cust, r, s, rev, cost, lines: byOrder[pos] });
      return;
    }
    const lines = byOrder[pos].filter((l) => data.products[l[1]][1] === f.category);
    if (!lines.length) return;
    const lrev = lines.reduce((a, l) => a + l[3], 0);
    const lcost = lines.reduce((a, l) => a + l[4], 0);
    picked.push({ pos, orderId, orderDate, m, cust, r, s, rev: lrev, cost: lcost, lines });
  });

  // Monthly trend
  const months = new Map();
  for (const o of picked) {
    const row = months.get(o.m) || { m: o.m, orders: 0, customers: new Set(), revenue: 0, cost: 0, collections: 0 };
    row.orders += 1;
    row.customers.add(o.cust);
    row.revenue += o.rev;
    row.cost += o.cost;
    months.set(o.m, row);
  }
  for (const [m, r, s, amount] of data.payments) {
    if (months.has(m) && inScope(r, s)) months.get(m).collections += amount;
  }
  const monthly = [...months.values()].sort((a, b) => a.m - b.m).map((x) => ({
    month_key: data.months[x.m],
    orders: x.orders,
    active_customers: x.customers.size,
    revenue: round(x.revenue, 2),
    gross_margin: round(x.revenue - x.cost, 2),
    avg_order_value: round(x.revenue / x.orders, 2),
    collections: round(x.collections, 2),
  }));

  // Regions
  const regionAgg = new Map();
  let totalRev = 0;
  for (const o of picked) {
    const row = regionAgg.get(o.r) || { customers: new Set(), orders: 0, revenue: 0, cost: 0 };
    row.customers.add(o.cust);
    row.orders += 1;
    row.revenue += o.rev;
    row.cost += o.cost;
    regionAgg.set(o.r, row);
    totalRev += o.rev;
  }
  const regions = [...regionAgg.entries()].map(([r, x]) => ({
    region_name: data.regions[r],
    active_customers: x.customers.size,
    orders: x.orders,
    revenue: round(x.revenue, 2),
    gross_margin: round(x.revenue - x.cost, 2),
    revenue_share_pct: totalRev ? round((100 * x.revenue) / totalRev, 1) : 0,
  })).sort((a, b) => b.revenue - a.revenue);

  // Products
  const prodAgg = new Map();
  for (const o of picked) {
    for (const [, p, qty, rev, cost] of o.lines) {
      const row = prodAgg.get(p) || { units: 0, revenue: 0, cost: 0 };
      row.units += qty;
      row.revenue += rev;
      row.cost += cost;
      prodAgg.set(p, row);
    }
  }
  const products = [...prodAgg.entries()].map(([p, x]) => ({
    product_name: data.products[p][0],
    category: data.categories[data.products[p][1]],
    units: x.units,
    revenue: round(x.revenue, 2),
    gross_margin: round(x.revenue - x.cost, 2),
  })).sort((a, b) => b.revenue - a.revenue || a.product_name.localeCompare(b.product_name));

  // Receivables aging (as of report date: date and category filters do not apply)
  const openInv = data.invoices.filter((i) => inScope(i[2], i[3]));
  const buckets = AGING.map(([order, label]) => ({ bucket_order: order, aging_bucket: label, open_invoices: 0, outstanding: 0 }));
  let arTotal = 0;
  let arOverdue = 0;
  for (const inv of openInv) {
    const days = inv[6];
    const b = buckets[AGING.findIndex(([, , test]) => test(days))];
    b.open_invoices += 1;
    b.outstanding += inv[5];
    arTotal += inv[5];
    if (days > 0) arOverdue += inv[5];
  }
  const aging = buckets.filter((b) => b.open_invoices > 0).map((b) => ({
    ...b,
    outstanding: round(b.outstanding, 2),
    pct_of_total: round((100 * b.outstanding) / arTotal, 1),
  }));

  // Cohort retention (region/segment only; uses every completed order of the customer)
  const custMonths = new Map();
  for (const o of data.orders) {
    if (!inScope(o[4], o[5])) continue;
    if (!custMonths.has(o[3])) custMonths.set(o[3], new Set());
    custMonths.get(o[3]).add(o[2]);
  }
  const cohortAgg = new Map();
  for (const ms of custMonths.values()) {
    const first = Math.min(...ms);
    if (!cohortAgg.has(first)) cohortAgg.set(first, new Map());
    const row = cohortAgg.get(first);
    for (const m of ms) row.set(m - first, (row.get(m - first) || 0) + 1);
  }
  const cohorts = [];
  for (const first of [...cohortAgg.keys()].sort((a, b) => a - b)) {
    const row = cohortAgg.get(first);
    const size = row.get(0);
    for (const k of [...row.keys()].sort((a, b) => a - b)) {
      cohorts.push({
        cohort_month: data.months[first],
        months_since_first: k,
        cohort_size: size,
        active_customers: row.get(k),
        retention_pct: round((100 * row.get(k)) / size, 1),
      });
    }
  }

  // Headline tiles
  const rev = picked.reduce((a, o) => a + o.rev, 0);
  const cost = picked.reduce((a, o) => a + o.cost, 0);
  const headline = {
    orders: picked.length,
    active_customers: new Set(picked.map((o) => o.cust)).size,
    revenue: round(rev, 2),
    gross_margin: round(rev - cost, 2),
    gross_margin_pct: rev ? round((100 * (rev - cost)) / rev, 1) : null,
    avg_order_value: picked.length ? round(rev / picked.length, 2) : null,
    ar_outstanding: round(arTotal, 2),
    ar_overdue: round(arOverdue, 2),
    ar_overdue_pct: arTotal ? round((100 * arOverdue) / arTotal, 1) : null,
  };

  const orders = picked.map((o) => ({
    order_id: o.orderId,
    order_date: o.orderDate,
    customer_id: o.cust,
    region: data.regions[o.r],
    segment: data.segments[o.s],
    revenue: round(o.rev, 2),
    gross_margin: round(o.rev - o.cost, 2),
  }));
  const invoices = openInv.map((i) => ({
    order_id: i[0],
    customer_id: i[1],
    region: data.regions[i[2]],
    segment: data.segments[i[3]],
    due_date: i[4],
    outstanding: i[5],
    days_past_due: i[6],
    aging_bucket: AGING.find(([, , test]) => test(i[6]))[1],
  }));

  return { filters: f, headline, monthly, regions, products, aging, cohorts, orders, invoices };
}

function toCSV(rows) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const cell = (v) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\n") + "\n";
}

if (typeof module !== "undefined") module.exports = { computeView, toCSV, allFilters };
