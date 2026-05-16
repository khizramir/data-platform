# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Work in progress.

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
