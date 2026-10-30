# Convenience targets. Every command also works without make, e.g. `python -m sqldash demo`.
PYTHON ?= python

.PHONY: demo test screenshots sql report clean

demo:            ## build DB, print KPIs, write dashboard + Power BI CSVs, open the dashboard
	$(PYTHON) -m sqldash demo

test:            ## offline test suite
	$(PYTHON) -m pytest -q

screenshots:     ## PNGs of the dashboard (needs Edge or Chrome)
	$(PYTHON) -m sqldash screenshot

sql:             ## regenerate SQL Server / PostgreSQL scripts in sql/generated/
	$(PYTHON) -m sqldash export-sql

report:          ## KPIs + data-quality checks for build/business.db
	$(PYTHON) -m sqldash report

clean:
	$(PYTHON) -c "import shutil; shutil.rmtree('build', ignore_errors=True)"
