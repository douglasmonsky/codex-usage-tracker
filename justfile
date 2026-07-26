set shell := ["bash", "-uc"]

doctor:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer doctor

vp:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m ruff check .
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m mypy
    git diff --check

verify-precommit:
    just vp

v:
    just vp
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pytest
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pyright --pythonpath "$PY" src
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m tach check
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_release.py

verify:
    just v

vc:
    just v
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m deptry .
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m vulture src tests scripts/check_product_complexity.py scripts/check_release.py config/vulture-whitelist.py
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer.runners.bandit
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_product_complexity.py --config config/product-complexity-budget.json
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" scripts/check_kernel_maintainability.py
    npm run dashboard:verify

verify-ci:
    just vc

verify-security:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer.runners.bandit
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m pip_audit -r requirements/audit.txt

verify-manual:
    just vc

wg run_id:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait github-run {{run_id}}

wait-github run_id:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait github-run {{run_id}}

wp pr_number:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait github-pr {{pr_number}}

wait-pr pr_number:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait github-pr {{pr_number}}

wv run_id:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait verifier {{run_id}}

wait-verifier run_id:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer wait verifier {{run_id}}
