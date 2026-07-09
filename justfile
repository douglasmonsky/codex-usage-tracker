set shell := ["bash", "-uc"]

doctor:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer doctor

vp:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile precommit

verify-precommit:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile precommit

v:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile full

verify:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile full

vc:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile ci

verify-ci:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile ci

verify-security:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile security

verify-manual:
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3; "$PY" -m agent_maintainer verify --profile manual

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
