set shell := ["bash", "-uc"]

scope:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_kernel_scope.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/generate_kernel_manifests.py --check

vp:
    just scope
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m ruff check \
        scripts/check_kernel_maintainability.py \
        scripts/check_kernel_scope.py \
        scripts/check_release.py \
        scripts/generate_kernel_manifests.py \
        src/codex_usage_tracker/kernel \
        tests/kernel/test_code_disposition_manifest.py \
        tests/kernel/test_cutover_control.py \
        tests/kernel/test_database_lifecycle.py \
        tests/kernel/test_development_efficiency_policy.py \
        tests/kernel/test_identity.py \
        tests/kernel/test_ingest_*.py \
        tests/kernel/test_kernel_maintainability.py \
        tests/kernel/test_kernel_scope.py \
        tests/kernel/test_repository_quality_policy.py \
        tests/kernel/test_retired_surface_manifest.py \
        tests/kernel/test_schema.py \
        tests/kernel/test_source_registry_privacy.py \
        tests/kernel/test_oracle_equivalence.py \
        tests/kernel/test_privacy_oracle.py \
        tests/kernel/test_source_lifecycle_oracle.py \
        tests/kernel/test_watcher.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m mypy
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_kernel_maintainability.py
    git diff --check

verify-precommit:
    just vp

v:
    just vp
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pytest -p no:tach \
        tests/kernel/test_kernel_scope.py \
        tests/kernel/test_code_disposition_manifest.py \
        tests/kernel/test_retired_surface_manifest.py \
        tests/kernel/test_development_efficiency_policy.py \
        tests/kernel/test_kernel_maintainability.py \
        tests/kernel/test_repository_quality_policy.py \
        tests/kernel/test_schema.py \
        tests/kernel/test_identity.py \
        tests/kernel/test_database_lifecycle.py \
        tests/kernel/test_cutover_control.py \
        tests/kernel/test_source_registry_privacy.py \
        tests/kernel/test_ingest_*.py \
        tests/kernel/test_oracle_equivalence.py \
        tests/kernel/test_privacy_oracle.py \
        tests/kernel/test_source_lifecycle_oracle.py \
        tests/kernel/test_watcher.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pyright --pythonpath "$PY"
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_release.py

verify:
    just v

vc:
    just v
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m build
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_release.py --dist

verify-ci:
    just vc

verify-manual:
    just vc
