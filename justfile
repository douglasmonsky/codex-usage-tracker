set shell := ["bash", "-uc"]

scope:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_agent_kernel_contracts.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m tests.agent_kernel.fixtures.generator.cli --profile tiny --check-committed
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_kernel_scope.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/generate_kernel_manifests.py --check
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; PYTHONPATH=src "$PY" scripts/generate_kernel_interfaces.py --check
    npm run console:build:check

vp:
    just scope
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m ruff check \
        scripts/check_kernel_maintainability.py \
        scripts/benchmark_agent_outcome.py \
        scripts/benchmark_kernel.py \
        scripts/check_agent_kernel_contracts.py \
        scripts/check_kernel_scope.py \
        scripts/check_release.py \
        scripts/check_kernel_release_candidate.py \
        scripts/release_promotion_quality.py \
        scripts/smoke_installed_console.py \
        scripts/smoke_installed_catalog.py \
        scripts/smoke_installed_package.py \
        scripts/generate_kernel_interfaces.py \
        scripts/generate_kernel_manifests.py \
        src/codex_usage_tracker/kernel \
        src/codex_usage_tracker/release \
        experiments/physical-architecture/shared \
        experiments/physical-architecture/candidate_a \
        experiments/physical-architecture/candidate_c \
        experiments/physical-architecture/candidate_d \
        tests/release \
        tests/agent_kernel \
        tests/experiments/physical-architecture \
        tests/kernel/allowance \
        tests/kernel/console \
        tests/kernel/content \
        tests/kernel/evidence \
        tests/kernel/interfaces \
        tests/kernel/live \
        tests/kernel/query \
        tests/kernel/test_code_disposition_manifest.py \
        tests/kernel/test_cutover_control.py \
        tests/kernel/test_database_lifecycle.py \
        tests/kernel/test_development_efficiency_policy.py \
        tests/kernel/test_documentation_authority.py \
        tests/kernel/test_fault_recovery_scale.py \
        tests/kernel/test_identity.py \
        tests/kernel/test_ingest_*.py \
        tests/kernel/test_kernel_maintainability.py \
        tests/kernel/test_kernel_benchmark.py \
        tests/kernel/test_agent_outcome_baseline.py \
        tests/kernel/test_kernel_scope.py \
        tests/kernel/test_repository_quality_policy.py \
        tests/kernel/test_release_candidate.py \
        tests/kernel/test_release_028_qualification.py \
        tests/kernel/test_release_cutover.py \
        tests/kernel/test_retired_surface_manifest.py \
        tests/kernel/test_schema.py \
        tests/kernel/test_source_registry_privacy.py \
        tests/kernel/test_oracle_equivalence.py \
        tests/kernel/test_privacy_oracle.py \
        tests/kernel/test_r5_analytical_primitives.py \
        tests/kernel/test_source_lifecycle_oracle.py \
        tests/kernel/test_stable_contract_028.py \
        tests/kernel/test_watcher.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m mypy
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_kernel_maintainability.py
    npm run console:lint
    npm run console:typecheck
    npm run console:test
    git diff --check

verify-precommit:
    just vp

v:
    just vp
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pytest -p no:tach \
        tests/kernel/test_agent_outcome_baseline.py \
        tests/kernel/test_kernel_scope.py \
        tests/kernel/test_code_disposition_manifest.py \
        tests/kernel/test_retired_surface_manifest.py \
        tests/kernel/test_development_efficiency_policy.py \
        tests/kernel/test_documentation_authority.py \
        tests/kernel/test_fault_recovery_scale.py \
        tests/kernel/test_kernel_maintainability.py \
        tests/kernel/test_kernel_benchmark.py \
        tests/kernel/test_repository_quality_policy.py \
        tests/kernel/test_release_candidate.py \
        tests/kernel/test_release_028_qualification.py \
        tests/kernel/test_release_cutover.py \
        tests/kernel/test_schema.py \
        tests/kernel/test_identity.py \
        tests/kernel/test_database_lifecycle.py \
        tests/kernel/test_cutover_control.py \
        tests/kernel/test_source_registry_privacy.py \
        tests/kernel/test_ingest_*.py \
        tests/kernel/test_oracle_equivalence.py \
        tests/kernel/test_privacy_oracle.py \
        tests/kernel/test_r5_analytical_primitives.py \
        tests/kernel/test_source_lifecycle_oracle.py \
        tests/kernel/test_stable_contract_028.py \
        tests/kernel/test_watcher.py \
        tests/agent_kernel \
        tests/experiments/physical-architecture \
        tests/kernel/allowance \
        tests/kernel/console \
        tests/kernel/content \
        tests/kernel/evidence \
        tests/kernel/interfaces \
        tests/kernel/live \
        tests/kernel/query tests/release
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

console-e2e:
    npm run console:e2e
