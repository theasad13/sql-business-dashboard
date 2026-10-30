"""Seeded generator for an invented B2B wholesale business.

Everything here is made up: company names are random word pairs, emails use the
reserved example.com domain, products are generic. Same seed -> same rows.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

START = date(2024, 1, 1)
REPORT_DATE = date(2025, 12, 31)

REGIONS = ["North", "South", "East", "West", "Central"]
REGION_WEIGHTS = [24, 18, 22, 16, 20]

# segment -> (share of customers, payment terms in days, quantity range, channel weights)
SEGMENTS = {
    "Retail Store": (50, 30, (2, 20), {"Sales Rep": 40, "Web": 35, "Phone": 25}),
    "Online Seller": (30, 30, (1, 12), {"Sales Rep": 10, "Web": 75, "Phone": 15}),
    "Corporate": (20, 45, (5, 40), {"Sales Rep": 70, "Web": 15, "Phone": 15}),
}

# (name, category, list price). Prices are multiples of 0.20 so 5% / 10%
# discounts always land on whole cents (no rounding drift between Python and SQL).
PRODUCTS = [
    ("Copy Paper A4 (box of 5)", "Office", "32.40"),
    ("Ballpoint Pens (50)", "Office", "14.60"),
    ("Desk Organizer", "Office", "22.80"),
    ("Heavy Duty Stapler", "Office", "27.20"),
    ("Whiteboard Markers (12)", "Office", "11.40"),
    ("Floor Cleaner 5L", "Cleaning", "18.60"),
    ("Microfiber Cloths (24)", "Cleaning", "16.20"),
    ("Hand Soap Refill 5L", "Cleaning", "21.40"),
    ("Trash Bags (100)", "Cleaning", "12.80"),
    ("Disinfectant Spray (12)", "Cleaning", "39.60"),
    ("Shipping Boxes Medium (25)", "Packaging", "28.80"),
    ("Packing Tape (36 rolls)", "Packaging", "44.20"),
    ("Bubble Wrap Roll 50m", "Packaging", "24.60"),
    ("Mailer Bags (100)", "Packaging", "19.80"),
    ("Thermal Label Rolls (4)", "Packaging", "26.40"),
    ("Coffee Beans 1kg", "Breakroom", "23.60"),
    ("Tea Assortment (100)", "Breakroom", "15.40"),
    ("Paper Cups (500)", "Breakroom", "31.80"),
    ("Bottled Water (24)", "Breakroom", "8.60"),
    ("Snack Box Assorted", "Breakroom", "36.00"),
    ("Nitrile Gloves (100)", "Safety", "13.20"),
    ("Safety Glasses", "Safety", "9.80"),
    ("Hi-Vis Vest", "Safety", "12.60"),
    ("First Aid Kit", "Safety", "48.40"),
    ("Ear Plugs (200)", "Safety", "34.20"),
]

NAME_LEFT = ["Blue", "Cedar", "North", "Silver", "Maple", "Harbor", "Summit", "River", "Oak", "Granite",
             "Pioneer", "Lakeside", "Copper", "Evergreen", "Prairie", "Coastal", "Golden", "Highland",
             "Willow", "Union"]
NAME_RIGHT = ["Traders", "Supply", "Mart", "Outfitters", "Goods", "Depot", "Store", "Co", "Wholesale",
              "Partners", "Retail", "Market", "Hardware", "Office Supply", "Distributors"]

# payment habit -> (weight, days relative to due date when paid)
PAYERS = {"prompt": (55, (-12, 4)), "late": (28, (5, 55)), "very_late": (12, (40, 150)), "partial": (5, (0, 20))}
PAYMENT_METHODS = {"Bank Transfer": 70, "Card": 20, "Cheque": 10}

# Bad rows planted on purpose so the data-quality checks have something to find.
# check name -> number of rows it must report on the generated data.
PLANTED = {
    "order_without_items": 1,
    "orphan_order_customer": 1,
    "orphan_item_product": 1,
    "bad_quantity_or_price": 2,
    "due_before_order": 1,
    "orphan_payment": 1,
    "payment_before_order": 1,
    "payment_on_cancelled_order": 1,
    "overpaid_invoice": 1,
    "duplicate_customer_email": 2,
    "missing_customer_region": 1,
    "missing_email": 1,
}

CENT = Decimal("0.01")


@dataclass
class Dataset:
    regions: list[tuple] = field(default_factory=list)
    customers: list[tuple] = field(default_factory=list)
    products: list[tuple] = field(default_factory=list)
    orders: list[tuple] = field(default_factory=list)
    order_items: list[tuple] = field(default_factory=list)
    payments: list[tuple] = field(default_factory=list)
    report_date: date = REPORT_DATE

    def tables(self) -> dict[str, list[tuple]]:
        return {
            "regions": self.regions,
            "customers": self.customers,
            "products": self.products,
            "orders": self.orders,
            "order_items": self.order_items,
            "payments": self.payments,
            "report_params": [(self.report_date.isoformat(),)],
        }


def _pick(rng: random.Random, weights: dict[str, int]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _price_for(list_price: Decimal, on: date) -> Decimal:
    """2025 price list is 5% higher, snapped to a multiple of 0.20."""
    if on.year < 2025:
        return list_price
    raised = list_price * Decimal("1.05")
    return (raised / Decimal("0.20")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("0.20")


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _days_in_month(y: int, m: int) -> int:
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return (nxt - date(y, m, 1)).days


def generate(seed: int = 42, customers: int = 300, plant_issues: bool = True) -> Dataset:
    """Build the full invented dataset. Deterministic for a given seed."""
    rng = random.Random(seed)
    ds = Dataset()
    ds.regions = [(i + 1, name) for i, name in enumerate(REGIONS)]

    for pid, (name, category, price) in enumerate(PRODUCTS, start=1):
        list_price = Decimal(price)
        margin = Decimal(rng.randint(26, 42)) / 100
        ds.products.append((pid, name, category, _money(list_price * (1 - margin)), float(list_price)))
    popularity = [rng.randint(1, 10) for _ in PRODUCTS]

    names = [f"{a} {b}" for a in NAME_LEFT for b in NAME_RIGHT]
    rng.shuffle(names)
    if customers > len(names):
        raise ValueError(f"at most {len(names)} customers")

    span_days = (date(2025, 9, 30) - START).days
    cust_info = {}
    for cid in range(1, customers + 1):
        segment = _pick(rng, {s: v[0] for s, v in SEGMENTS.items()})
        region_id = rng.choices(range(1, len(REGIONS) + 1), weights=REGION_WEIGHTS)[0]
        # 40% are customers we already had at the start, the rest join over time.
        created = START if rng.random() < 0.4 else START + timedelta(days=rng.randint(0, span_days))
        name = names[cid - 1]
        email = name.lower().replace(" ", ".") + "@example.com"
        ds.customers.append((cid, name, email, segment, region_id, created.isoformat()))
        cust_info[cid] = {
            "segment": segment,
            "created": created,
            "order_prob": rng.uniform(0.25, 0.85),
            "churn": rng.uniform(0.01, 0.07),
            "payer": _pick(rng, {k: v[0] for k, v in PAYERS.items()}),
        }

    order_id, item_id, payment_id = 1000, 1, 1
    for cid, info in cust_info.items():
        seg_share, terms, qty_range, channels = SEGMENTS[info["segment"]]
        first = info["created"] > START  # customers we already had don't all order in January
        for y, m in _months(info["created"], REPORT_DATE):
            if not first:
                if rng.random() < info["churn"]:
                    break
                if rng.random() > info["order_prob"]:
                    continue
            lo_day = info["created"].day if first and (y, m) == (info["created"].year, info["created"].month) else 1
            n_orders = 2 if rng.random() < 0.12 else 1
            for _ in range(n_orders):
                order_date = date(y, m, rng.randint(lo_day, _days_in_month(y, m)))
                due = order_date + timedelta(days=terms)
                status = "Cancelled" if rng.random() < 0.03 else "Completed"
                order_id += 1
                ds.orders.append((order_id, cid, order_date.isoformat(), due.isoformat(), status,
                                  _pick(rng, channels)))
                season = 1.25 if m in (11, 12) else 1.0
                total = Decimal(0)
                for pid in rng.sample(range(1, len(PRODUCTS) + 1), k=rng.choices([1, 2, 3, 4], [30, 35, 25, 10])[0]):
                    pid_weight = popularity[pid - 1]
                    qty = max(1, round(rng.randint(*qty_range) * season * (0.6 + pid_weight / 12)))
                    price = _price_for(Decimal(PRODUCTS[pid - 1][2]), order_date)
                    discount = Decimal(rng.choices([0, 5, 10], [60, 25, 15] if info["segment"] == "Corporate" else [80, 15, 5])[0])
                    ds.order_items.append((item_id, order_id, pid, qty, float(price), float(discount)))
                    item_id += 1
                    total += (qty * price * (100 - discount) / 100).quantize(CENT, rounding=ROUND_HALF_UP)
                if status == "Completed":
                    payment_id = _add_payments(ds, rng, payment_id, order_id, due, total, info["payer"])
            first = False

    if plant_issues:
        _plant_issues(ds, order_id, item_id, payment_id)
    return ds


def _add_payments(ds: Dataset, rng: random.Random, payment_id: int, order_id: int, due: date,
                  total: Decimal, payer: str) -> int:
    lo, hi = PAYERS[payer][1]
    order_date = date.fromisoformat(ds.orders[-1][2])
    if payer == "very_late" and rng.random() < 0.35:
        return payment_id  # never pays: ends up in the 90+ bucket
    paid_on = max(order_date, due + timedelta(days=rng.randint(lo, hi)))
    method = _pick(rng, PAYMENT_METHODS)
    if payer == "partial":
        first = (total / 2).quantize(CENT, rounding=ROUND_HALF_UP)
        parts = [(paid_on, first), (paid_on + timedelta(days=rng.randint(30, 120)), total - first)]
    else:
        parts = [(paid_on, total)]
    for when, amount in parts:
        if when <= REPORT_DATE:
            ds.payments.append((payment_id, order_id, when.isoformat(), _money(amount), method))
            payment_id += 1
    return payment_id


def _plant_issues(ds: Dataset, order_id: int, item_id: int, payment_id: int) -> None:
    """Append the bad rows counted in PLANTED. Kept explicit so tests can trust the counts."""
    def new_order(customer_id, order_date, due, status="Completed"):
        nonlocal order_id
        order_id += 1
        ds.orders.append((order_id, customer_id, order_date, due, status, "Phone"))
        return order_id

    def new_item(oid, product_id, qty, price=20.0, discount=0.0):
        nonlocal item_id
        ds.order_items.append((item_id, oid, product_id, qty, price, discount))
        item_id += 1

    def new_payment(oid, paid_on, amount):
        nonlocal payment_id
        ds.payments.append((payment_id, oid, paid_on, amount, "Bank Transfer"))
        payment_id += 1

    # order_without_items
    new_order(1, "2025-06-10", "2025-07-10")
    # orphan_order_customer: customer 99999 does not exist
    oid = new_order(99999, "2025-05-03", "2025-06-02")
    new_item(oid, 1, 4)
    new_payment(oid, "2025-06-01", 80.0)
    # orphan_item_product + bad_quantity_or_price (x2) on one paid order
    oid = new_order(2, "2025-04-14", "2025-05-14")
    new_item(oid, 999, 3)            # product 999 does not exist
    new_item(oid, 2, -5)             # a return keyed as a negative quantity
    new_item(oid, 3, 0)              # zero quantity
    new_payment(oid, "2025-05-10", -40.0)
    # due_before_order
    oid = new_order(3, "2025-08-20", "2025-07-20")
    new_item(oid, 4, 2)
    new_payment(oid, "2025-08-25", 40.0)
    # orphan_payment: order 88888 does not exist
    new_payment(88888, "2025-03-15", 125.0)
    # payment_before_order
    oid = new_order(4, "2025-09-12", "2025-10-12")
    new_item(oid, 5, 5)
    new_payment(oid, "2025-09-01", 100.0)
    # payment_on_cancelled_order
    oid = new_order(5, "2025-02-07", "2025-03-09", status="Cancelled")
    new_item(oid, 6, 1)
    new_payment(oid, "2025-03-01", 20.0)
    # overpaid_invoice: same payment keyed twice
    oid = new_order(6, "2025-10-02", "2025-11-01")
    new_item(oid, 7, 3)
    new_payment(oid, "2025-10-30", 60.0)
    new_payment(oid, "2025-10-30", 60.0)
    # duplicate_customer_email (x2), missing_customer_region, missing_email
    next_cid = max(c[0] for c in ds.customers) + 1
    ds.customers.append((next_cid, ds.customers[0][1] + " Ltd", ds.customers[0][2].upper(), "Retail Store", 1, "2025-07-01"))
    ds.customers.append((next_cid + 1, ds.customers[1][1], ds.customers[1][2], "Corporate", 2, "2025-07-02"))
    ds.customers.append((next_cid + 2, "Unplaced Account", "unplaced.account@example.com", "Online Seller", None, "2025-07-03"))
    ds.customers.append((next_cid + 3, "No Email Account", None, "Retail Store", 3, "2025-07-04"))
