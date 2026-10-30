"""The sample data is seeded: same seed, same rows, every time."""
import hashlib
import json

from sqldash import generate


def digest(ds) -> str:
    return hashlib.sha256(json.dumps(ds.tables(), sort_keys=True).encode()).hexdigest()


def test_same_seed_same_data():
    assert digest(generate.generate(seed=7)) == digest(generate.generate(seed=7))


def test_different_seed_different_data():
    assert digest(generate.generate(seed=7)) != digest(generate.generate(seed=8))


def test_shape_and_invented_only():
    ds = generate.generate(seed=42)
    assert len(ds.regions) == 5 and len(ds.products) == 25
    assert len(ds.customers) == 300 + 4          # 4 planted bad customer rows
    assert len(ds.orders) > 2000
    emails = [c[2] for c in ds.customers if c[2]]
    assert all(e.lower().endswith("@example.com") for e in emails)
    assert max(o[2] for o in ds.orders) <= generate.REPORT_DATE.isoformat()
    assert all(p[2] <= generate.REPORT_DATE.isoformat() for p in ds.payments)


def test_line_amounts_are_whole_cents():
    ds = generate.generate(seed=42, plant_issues=False)
    for _, _, _, qty, price, discount in ds.order_items:
        cents = qty * price * (100 - discount)   # revenue * 100
        assert abs(cents - round(cents)) < 1e-6
