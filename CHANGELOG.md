# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Work in progress.

## v0.1.0 - 2026-05-16

Initial release v0.1.0 containing the following phases:

- Phase 1: Core plugin architecture
	- Plugin base classes and lifecycle management (`PluginManager`, `PluginRegistry`).
	- Example PostgreSQL plugin.
	- Unit tests for registry and manager.

- Phase 2: Cleaning engine + Historization
	- Rules-based cleaning engine with validation, transformation, standardization, type coercion, masking, anomaly detection.
	- YAML loader for rule definitions and example rule sets.
	- In-memory SCD Type 2 historization manager.
	- Tests for cleaning and historization.

- Phase 3: CI/CD pipeline + Documentation
	- GitHub Actions workflow to run tests on push to `main` including caching for Poetry, pip, and `.venv`.
	- README with usage examples, and example rule YAML files.

## Phases

### Phase 1: Core plugin architecture

- Plugin base abstractions (`DataSourcePlugin`, `PluginMetadata`, `QueryResult`) under `src/data_platform/core`.
- `PluginRegistry` and `PluginManager` for discovering, registering, and managing plugin lifecycles.
- Example PostgreSQL plugin at `src/data_platform/plugins/postgresql/plugin.py`.
- Unit tests for core components under `tests/`.

### Phase 2: Cleaning engine + Historization

- Rules-based cleaning engine with rule implementations (validation, transformation, standardization, type coercion, masking, anomaly detection) under `src/data_platform/cleaning/rules`.
- Rule loader (`load_rules_from_yaml` / `load_rules_from_dict`) in `src/data_platform/cleaning/loader.py`.
- `CleaningEngine` which processes records using ordered rules in `src/data_platform/cleaning/engine.py`.
- SCD Type 2 historization manager in `src/data_platform/historization/scd2.py` with in-memory versioning.
- Example YAML rule sets in `examples/rules/` and tests for cleaning/historization.

### Phase 3: CI/CD pipeline + Documentation

- GitHub Actions CI workflow at `.github/workflows/ci.yml` (runs pytest on push to `main`).
- Caching for Poetry, pip, and virtualenv added to CI to speed builds.
- README updates with usage examples and architecture diagram.
- Example rule YAML files for various domains (customer CRM, financial, address, HR, sales, IoT).
