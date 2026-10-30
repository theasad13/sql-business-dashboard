-- Tiny hand-made dataset. Every expected KPI in tests/test_kpis.py is worked out
-- by hand from these rows (see the comments there). Report date: 2025-03-31.

INSERT INTO report_params VALUES ('2025-03-31');

INSERT INTO regions VALUES (1, 'North'), (2, 'South');

INSERT INTO customers VALUES
  (1, 'Alpha Mart',  'alpha@example.com', 'Retail Store',  1, '2025-01-01'),
  (2, 'Beta Supply', 'beta@example.com',  'Corporate',     2, '2024-11-20'),
  (3, 'Gamma Goods', 'gamma@example.com', 'Online Seller', 1, '2025-02-01'),
  (4, 'Delta Depot', 'delta@example.com', 'Corporate',     2, '2025-01-15');

INSERT INTO products VALUES
  (1, 'Widget', 'Office',   6.00, 10.00),
  (2, 'Gadget', 'Cleaning', 15.00, 20.00);

--                order  cust  order_date    due_date      status       channel
INSERT INTO orders VALUES
  (100, 2, '2024-12-01', '2024-12-30', 'Completed', 'Sales Rep'),  -- 91 days past due
  (101, 1, '2025-01-10', '2025-01-25', 'Completed', 'Web'),        -- 65 days past due
  (102, 2, '2025-01-20', '2025-02-20', 'Completed', 'Sales Rep'),  -- 39 days past due
  (108, 4, '2025-01-28', '2025-02-27', 'Completed', 'Phone'),      -- paid in full
  (103, 1, '2025-02-15', '2025-03-17', 'Completed', 'Web'),        -- 14 days past due
  (104, 3, '2025-02-20', '2025-03-22', 'Completed', 'Phone'),      -- paid in full
  (105, 2, '2025-03-05', '2025-04-19', 'Completed', 'Sales Rep'),  -- not yet due
  (106, 3, '2025-03-10', '2025-04-09', 'Cancelled', 'Web');        -- excluded everywhere

--                      item order prod qty price  disc   revenue   cost
INSERT INTO order_items VALUES
  (1, 100, 1,  5, 10.00,  0),   --  50.00   30.00
  (2, 101, 1, 10, 10.00,  0),   -- 100.00   60.00
  (3, 102, 2,  5, 20.00, 10),   --  90.00   75.00
  (4, 102, 1,  2, 10.00,  0),   --  20.00   12.00
  (5, 108, 1,  1, 10.00,  0),   --  10.00    6.00
  (6, 103, 1,  3, 10.00,  0),   --  30.00   18.00
  (7, 104, 2,  2, 20.00,  0),   --  40.00   30.00
  (8, 105, 2, 10, 20.00,  5),   -- 190.00  150.00
  (9, 106, 1,  1, 10.00,  0);   --  10.00 (cancelled)

INSERT INTO payments VALUES
  (1, 100, '2025-01-15',  20.00, 'Bank Transfer'),  -- partial: 30.00 left
  (2, 102, '2025-03-01',  60.00, 'Bank Transfer'),  -- partial: 50.00 left
  (3, 104, '2025-03-20',  40.00, 'Card'),
  (4, 103, '2025-04-05',  30.00, 'Card'),           -- after report date: ignored for aging
  (5, 105, '2025-03-28', 100.00, 'Bank Transfer'),  -- partial: 90.00 left
  (6, 108, '2025-02-25',  10.00, 'Cheque');
