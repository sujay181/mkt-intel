# =============================================================================
# mkt-intel — one command per stage. `make all` runs the entire pipeline.
# =============================================================================
.PHONY: help install generate load build test docs analyse export all clean smoke ci

DB       ?= warehouse/mkt.duckdb
ACCOUNTS ?= 6000
DBT      := cd dbt_project && DBT_PROFILES_DIR=. dbt

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:   ## Install Python deps and dbt packages
	pip install -r requirements.txt
	$(DBT) deps

generate:  ## Simulate the world (override with ACCOUNTS=500 for a quick run)
	python -m generator.simulate --config config/simulation.yml \
	  --out raw --truth ground_truth --accounts $(ACCOUNTS)

load:      ## Land raw files into DuckDB
	python warehouse/load_duckdb.py --db $(DB) --raw raw

build:     ## Run seeds + all dbt models
	$(DBT) seed
	$(DBT) run

test:      ## Run all dbt tests (42 of them)
	$(DBT) test

docs:      ## Build dbt docs + validate the metric registry
	$(DBT) docs generate
	python governance/build_dictionary.py --db $(DB)

analyse:   ## Run every analysis script
	python analysis/01_funnel.py    --db $(DB)
	python analysis/02_cohorts.py   --db $(DB)
	python analysis/03_segments.py  --db $(DB) --export
	python analysis/04_markov.py    --db $(DB)
	python analysis/05_scorecard.py --db $(DB)

export:    ## Export CSVs for Tableau
	python analysis/07_export_tableau.py --db $(DB)

spark:     ## Run the PySpark sessionizer and check parity with dbt
	python spark/sessionize.py --input "raw/segment_events/*.jsonl" \
	  --output spark/output/sessions
	python analysis/06_parity_check.py --db $(DB)

all: generate load build test docs analyse export  ## Full pipeline end to end
	@echo ""
	@echo "Pipeline complete. Next: open exports/tableau/ in Tableau Public."

smoke: ## Fast end-to-end check on 300 accounts
	$(MAKE) ACCOUNTS=300 generate load build test

ci: load build test docs ## What GitHub Actions runs

clean:
	rm -rf warehouse/*.duckdb raw/segment_events raw/salesforce raw/ad_platforms \
	       ground_truth/*.csv exports/* dbt_project/target dbt_project/dbt_packages \
	       spark/output
