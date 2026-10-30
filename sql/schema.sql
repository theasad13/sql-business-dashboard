-- Schema for an invented B2B wholesale business ("Harbor & Pine Supply", fictional).
-- Portable SQL: runs on SQLite as-is; `python -m sqldash export-sql` writes the
-- SQL Server and PostgreSQL versions into sql/generated/.
--
-- Foreign keys are documented but NOT enforced on purpose: this mirrors a
-- reporting copy of operational data, where bad rows do arrive. The data-quality
-- checks in dq_checks.sql find them instead of the database rejecting them.

CREATE TABLE regions (
    region_id    INTEGER      NOT NULL PRIMARY KEY,
    region_name  VARCHAR(50)  NOT NULL
);

CREATE TABLE customers (
    customer_id    INTEGER       NOT NULL PRIMARY KEY,
    customer_name  VARCHAR(100)  NOT NULL,
    email          VARCHAR(120),
    segment        VARCHAR(30)   NOT NULL,   -- Retail Store / Online Seller / Corporate
    region_id      INTEGER,                  -- -> regions.region_id
    created_on     DATE          NOT NULL
);

CREATE TABLE products (
    product_id    INTEGER        NOT NULL PRIMARY KEY,
    product_name  VARCHAR(100)   NOT NULL,
    category      VARCHAR(50)    NOT NULL,
    unit_cost     DECIMAL(12,2)  NOT NULL,
    list_price    DECIMAL(12,2)  NOT NULL
);

-- One order = one invoice. due_date = order_date + payment terms.
CREATE TABLE orders (
    order_id     INTEGER      NOT NULL PRIMARY KEY,
    customer_id  INTEGER      NOT NULL,      -- -> customers.customer_id
    order_date   DATE         NOT NULL,
    due_date     DATE         NOT NULL,
    status       VARCHAR(20)  NOT NULL,      -- Completed / Cancelled
    channel      VARCHAR(20)  NOT NULL       -- Sales Rep / Web / Phone
);

CREATE TABLE order_items (
    order_item_id  INTEGER        NOT NULL PRIMARY KEY,
    order_id       INTEGER        NOT NULL,  -- -> orders.order_id
    product_id     INTEGER        NOT NULL,  -- -> products.product_id
    quantity       INTEGER        NOT NULL,
    unit_price     DECIMAL(12,2)  NOT NULL,
    discount_pct   DECIMAL(5,2)   NOT NULL   -- 0..100
);

CREATE TABLE payments (
    payment_id  INTEGER        NOT NULL PRIMARY KEY,
    order_id    INTEGER        NOT NULL,     -- -> orders.order_id
    paid_on     DATE           NOT NULL,
    amount      DECIMAL(12,2)  NOT NULL,
    method      VARCHAR(20)    NOT NULL      -- Bank Transfer / Card / Cheque
);

-- One row: the "as of" date every aging and retention number is measured against.
CREATE TABLE report_params (
    report_date  DATE  NOT NULL
);
