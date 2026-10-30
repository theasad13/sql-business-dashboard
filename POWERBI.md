# Loading the data into Power BI

`python -m sqldash demo` (or `python -m sqldash powerbi`) writes six CSV files into
`examples/powerbi/`. They form a **star schema**: three dimension tables you filter by, three fact
tables you add up. Power BI Desktop handles this shape well, and the same files work in Excel
Power Pivot, Tableau or Looker Studio.

| File | Type | One row per | Key columns |
|---|---|---|---|
| `dim_date.csv` | dimension | calendar day | `date` |
| `dim_customer.csv` | dimension | customer (region and segment included) | `customer_key` |
| `dim_product.csv` | dimension | product | `product_key` |
| `fact_sales.csv` | fact | invoice line of a completed order | `order_date`, `customer_key`, `product_key` |
| `fact_payments.csv` | fact | payment received | `paid_on`, `customer_key` |
| `fact_open_invoices.csv` | fact | unpaid invoice as of the report date | `due_date`, `customer_key` |

Rows whose customer or product is missing in the source get key `-1` ("Unknown"), so no sales go
missing when you create the relationships.

## Steps (Power BI Desktop, about 10 minutes)

1. **Get data → Text/CSV**, pick `fact_sales.csv`, click **Load**. Repeat for the other five files.
2. In **Power Query** (Transform data), check the types: `date`, `order_date`, `paid_on`,
   `due_date` = *Date*; `revenue`, `cost`, `gross_margin`, `amount`, `outstanding` = *Fixed decimal number*.
3. **Model view** — drag to create these relationships (all *many-to-one*, single direction):

   | From (many) | To (one) |
   |---|---|
   | `fact_sales[order_date]` | `dim_date[date]` |
   | `fact_sales[customer_key]` | `dim_customer[customer_key]` |
   | `fact_sales[product_key]` | `dim_product[product_key]` |
   | `fact_payments[paid_on]` | `dim_date[date]` (set active if Power BI made it inactive) |
   | `fact_payments[customer_key]` | `dim_customer[customer_key]` |
   | `fact_open_invoices[customer_key]` | `dim_customer[customer_key]` |

   Leave `fact_open_invoices[due_date]` unrelated: aging is a snapshot as of the report date, not a
   time series.
4. Select `dim_date` → **Table tools → Mark as date table** → column `date`.
5. Sort `dim_date[month_name]` by `month_num` (Column tools → Sort by column).
6. Add the measures below (Home → New measure).

## DAX measures (match the SQL views)

```DAX
Revenue = SUM ( fact_sales[revenue] )
Gross Margin = SUM ( fact_sales[gross_margin] )
Gross Margin % = DIVIDE ( [Gross Margin], [Revenue] )
Orders = DISTINCTCOUNT ( fact_sales[order_id] )
Active Customers = DISTINCTCOUNT ( fact_sales[customer_key] )
Avg Order Value = DIVIDE ( [Revenue], [Orders] )
Collections = SUM ( fact_payments[amount] )
AR Outstanding = SUM ( fact_open_invoices[outstanding] )
AR Overdue = CALCULATE ( [AR Outstanding], fact_open_invoices[days_past_due] > 0 )
AR Overdue % = DIVIDE ( [AR Overdue], [AR Outstanding] )
```

For the aging chart, put `fact_open_invoices[aging_bucket]` on the axis (sort it by
`bucket_order`) and `[AR Outstanding]` as the value.

## Checking your numbers

With no filters, the Power BI cards should equal the SQL output of `python -m sqldash report`
(revenue, gross margin, receivables). One known, explained difference: **Orders** in Power BI
counts orders that have at least one line, while the SQL view also counts an order with no lines
(flagged by the `order_without_items` data-quality check). Fix the source row and they agree.

## Pointing Power BI at a live database instead of CSVs

If the KPI views are installed on SQL Server or PostgreSQL (see the README), use **Get data → SQL
Server** (or PostgreSQL) and load the `kpi_*` views directly, or build the star schema from
`v_order_lines`, `v_orders` and `v_open_invoices`.
