# Data Platform

Project: Multi-Source Data Integration Platform with plugin architecture.

**Architecture (text diagram)**

data sources --> `plugins` (connectors) --> `PluginManager`/`PluginRegistry` --> core processing
												   |
												   v
										 `cleaning` engine (rules/loader)
												   |
												   v
										 historization (SCD2 manager)

Overview
--------
This repository provides a foundation for integrating multiple data sources via a plugin
architecture, a rules-based data cleaning engine, and an in-memory SCD Type 2 historization
manager. It includes example plugins (PostgreSQL), a set of cleaning rule types, loaders for
YAML rule specifications, and tests.

Install
-------
Requires Python 3.11 and Poetry.

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install poetry
poetry config virtualenvs.create false --local
poetry install
```

Run tests locally:

```bash
PYTHONPATH=.:src pytest -q
```

Using the Cleaning Engine
-------------------------
You can define rules as YAML and load them with the loader, or build rules programmatically.

Example (load from YAML):

```python
from data_platform.cleaning.engine import CleaningEngine

engine = CleaningEngine()
engine.load_rules_from_yaml("examples/rules/customer_crm.yaml")

record = {"customer_id": "123", "name": " alice ", "email": "alice@example.com"}
result = engine.process_record(record)
print(result.cleaned)
for r in result.rule_results:
	print(r.rule_name, r.passed, r.transformed_value)
```

Programmatic example:

```python
from data_platform.cleaning.rules.validation import ValidationRule
from data_platform.cleaning.engine import CleaningEngine

engine = CleaningEngine()
engine.add_rule(ValidationRule(name="id_int", field="customer_id", check="not_null"))

```

Using the Historization Module (SCD Type 2)
------------------------------------------
The `SCD2Manager` provides an in-memory SCD Type 2 store with hash-based change detection.

```python
from data_platform.historization.scd2 import SCD2Manager
from datetime import datetime, timezone

m = SCD2Manager(natural_key_fields=["id"]) 
rec = {"id": 1, "name": "Alice", "val": 10}
res = m.upsert(rec, timestamp=datetime.now(tz=timezone.utc))
print(res.action)
```

Modules
-------
- `data_platform.core` — plugin base classes, `PluginManager`, `PluginRegistry`.
- `data_platform.plugins` — connector plugins (e.g., PostgreSQL plugin).
- `data_platform.cleaning` — cleaning engine, rule implementations, YAML loader.
- `data_platform.historization` — in-memory SCD Type 2 manager.

Examples and rules
------------------
- Example YAML rule files are in `examples/rules/` including `customer_crm.yaml`, `financial.yaml`, and `address_standardization.yaml`.

CI
--
GitHub Actions workflow added at `.github/workflows/ci.yml` to run tests on pushes to `main`.

Contributing
------------
Please follow the CLAUDE.md guidelines for commits, documentation, and tests.

Multi-Source Data Integration Platform
