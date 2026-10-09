.PHONY: bootstrap test test-fast zero-cost bench golden doctor api docs lint
VENV ?= .venv
PY := $(VENV)/bin/python
APEX := $(VENV)/bin/apex-one

bootstrap:
	./scripts/bootstrap.sh

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest -m "not browser" -k "not golden and not fact_conflict"

zero-cost:
	$(PY) -m pytest tests/test_zero_cost.py -v

bench:
	$(APEX) benchmark --suite design

golden:
	$(APEX) benchmark --suite golden --quality ultra

doctor:
	$(APEX) doctor

api:
	$(APEX) api

docs:
	$(PY) scripts/gen_model_arsenal_doc.py
