# Parallel Hardening CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the hardening critical path by splitting independent checks into parallel GitHub Actions jobs and caching pinned policy-tool binaries.

**Architecture:** Replace the serial `hardening` implementation with four worker jobs grouped by toolchain and responsibility. A lightweight aggregate job retains the `Hardening gates` name and fails unless every worker succeeds.

**Tech Stack:** GitHub Actions YAML, Python 3.14, Node 22/npm, Go 1.25, Cargo, Actionlint, Gitleaks, Taplo, Zizmor, check-jsonschema.

## Global Constraints

- Preserve every existing hardening command and threshold.
- Preserve `Hardening gates` as the aggregate visible status name.
- Use only standard GitHub-hosted runners.
- Keep Actionlint at `v1.7.12`, Gitleaks at `v8.30.1`, and Taplo CLI at `0.9.0`.
- Keep the Agent Maintainer override pinned to commit `1129570a725256dcc5f04bee33cdc32c35af911d`.
- Do not add third-party installer actions.
- Treat run `29387911750` and its 6m56s hardening duration as the comparison baseline.

---

### Task 1: Split the hardening workers and add caches

**Files:**
- Modify: `.github/workflows/ci.yml:16-95`

**Interfaces:**
- Consumes: the existing npm scripts, Python benchmark command, development extra, audit requirements, and repository lint configuration.
- Produces: worker job results named `hardening_dashboard`, `hardening_routes`, `hardening_python`, and `hardening_policy`.

- [ ] **Step 1: Record the existing workflow baseline**

Run:

```bash
gh run view 29387911750 --json jobs \
  --jq '.jobs[] | select(.name == "Hardening gates") | {startedAt, completedAt, conclusion}'
```

Expected: conclusion `success`, start `2026-07-15T04:00:49Z`, and completion `2026-07-15T04:07:45Z`.

- [ ] **Step 2: Replace the serial hardening job with four worker jobs**

Replace the existing `hardening` block with the following job structure. Retain the existing commands exactly inside their assigned jobs.

```yaml
  hardening_dashboard:
    name: Hardening / Dashboard quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-node@v6.4.0
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: package-lock.json
      - name: Install dashboard tooling
        run: npm ci
      - name: Dashboard lint
        run: npm run dashboard:lint
      - name: Dashboard type check
        run: npm run dashboard:typecheck
      - name: Dashboard tests
        run: npm run dashboard:test
      - name: Dashboard build
        run: npm run dashboard:build
      - name: Dashboard governance
        run: npm run dashboard:governance
      - name: Dashboard bundle budget
        run: node scripts/check-dashboard-bundles.mjs

  hardening_routes:
    name: Hardening / Dashboard route budget
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: pyproject.toml
      - name: Install runtime dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install .
      - name: Dashboard route performance budget
        run: |
          python scripts/benchmark_dashboard_routes.py \
            --sizes 100000 \
            --iterations 3 \
            --skip-compression \
            --enforce-thresholds \
            --output-dir /tmp/dashboard-route-budget

  hardening_python:
    name: Hardening / Python quality and security
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: |
            pyproject.toml
            requirements/audit.txt
      - name: Install Python tooling
        run: |
          python -m pip install --upgrade pip
          python -m pip install ".[dev]"
          python -m pip install --force-reinstall --no-deps \
            "agent-maintainer @ git+https://github.com/douglasmonsky/agent-maintainer.git@1129570a725256dcc5f04bee33cdc32c35af911d"
      - name: Agent Maintainer guidance drift
        run: python -m agent_maintainer guidance --check
      - name: Whole-source Pyright
        run: python -m pyright --pythonpath "$(command -v python)" src
      - name: Dependency hygiene
        run: deptry .
      - name: Dead code
        run: vulture src tests config/vulture-whitelist.py
      - name: Dependency vulnerabilities
        run: pip-audit -r requirements/audit.txt
      - name: Python security
        run: python -m agent_maintainer.runners.bandit

  hardening_policy:
    name: Hardening / Repository policy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: pyproject.toml
      - uses: actions/setup-node@v6.4.0
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: package-lock.json
      - uses: actions/setup-go@v6
        with:
          go-version: "1.25"
      - name: Restore pinned policy tools
        id: policy-tools-cache
        uses: actions/cache@v6
        with:
          path: |
            ~/go/bin/actionlint
            ~/go/bin/gitleaks
            ~/.cargo/bin/taplo
          key: ${{ runner.os }}-hardening-tools-actionlint-1.7.12-gitleaks-8.30.1-taplo-0.9.0-v1
      - name: Install repository policy dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install \
            "check-jsonschema>=0.37.4" \
            "yamllint>=1.38.0" \
            "zizmor>=1.26.1"
          npm ci
      - name: Install pinned policy tools
        if: steps.policy-tools-cache.outputs.cache-hit != 'true'
        run: |
          go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12
          go install github.com/zricethezav/gitleaks/v8@v8.30.1
          cargo install taplo-cli --version 0.9.0 --locked
      - name: Workflow security
        run: zizmor --offline --no-progress .github/workflows
      - name: GitHub Actions lint
        run: actionlint .github/workflows/*.yml
      - name: Secret scan
        run: gitleaks dir --no-banner --redact=100 --report-format json --report-path /tmp/gitleaks.json .
      - name: Markdown lint
        run: npx markdownlint-cli2
      - name: YAML lint
        run: yamllint .github .yamllint
      - name: TOML format
        run: taplo fmt --check pyproject.toml tach.toml
      - name: Workflow schema validation
        run: |
          check-jsonschema \
            --builtin-schema vendor.github-workflows \
            .github/workflows/ci.yml \
            .github/workflows/pricing-compat.yml \
            .github/workflows/publish.yml
          check-jsonschema \
            --builtin-schema vendor.dependabot \
            .github/dependabot.yml
```

- [ ] **Step 3: Validate worker-job YAML and command availability**

Run:

```bash
actionlint .github/workflows/*.yml
zizmor --offline --no-progress .github/workflows
check-jsonschema --builtin-schema vendor.github-workflows \
  .github/workflows/ci.yml \
  .github/workflows/pricing-compat.yml \
  .github/workflows/publish.yml
```

Expected: all commands exit 0 with no workflow errors.

---

### Task 2: Add the stable aggregate gate and validate the branch

**Files:**
- Modify: `.github/workflows/ci.yml` immediately after the four hardening worker jobs.

**Interfaces:**
- Consumes: `needs.<worker>.result` for all four Task 1 worker jobs.
- Produces: one visible `Hardening gates` status that exits 0 only when every worker result is `success`.

- [ ] **Step 1: Add the aggregate hardening job**

Add:

```yaml
  hardening:
    name: Hardening gates
    if: ${{ always() }}
    needs:
      - hardening_dashboard
      - hardening_routes
      - hardening_python
      - hardening_policy
    runs-on: ubuntu-latest
    steps:
      - name: Verify hardening workers
        env:
          DASHBOARD_RESULT: ${{ needs.hardening_dashboard.result }}
          ROUTES_RESULT: ${{ needs.hardening_routes.result }}
          PYTHON_RESULT: ${{ needs.hardening_python.result }}
          POLICY_RESULT: ${{ needs.hardening_policy.result }}
        run: |
          test "$DASHBOARD_RESULT" = success
          test "$ROUTES_RESULT" = success
          test "$PYTHON_RESULT" = success
          test "$POLICY_RESULT" = success
```

- [ ] **Step 2: Run repository validation**

Run:

```bash
python scripts/check_release.py
git diff --check
actionlint .github/workflows/*.yml
zizmor --offline --no-progress .github/workflows
yamllint .github .yamllint
taplo fmt --check pyproject.toml tach.toml
check-jsonschema --builtin-schema vendor.github-workflows \
  .github/workflows/ci.yml \
  .github/workflows/pricing-compat.yml \
  .github/workflows/publish.yml
check-jsonschema --builtin-schema vendor.dependabot .github/dependabot.yml
```

Expected: every command exits 0. `git diff --check` prints no output.

- [ ] **Step 3: Review and commit the workflow change**

Run:

```bash
git diff --stat
git diff -- .github/workflows/ci.yml
git status --short --branch
git add -- .github/workflows/ci.yml docs/superpowers/plans/2026-07-15-parallel-hardening-ci.md
git commit -m "ci: parallelize hardening gates"
```

Expected: the commit contains only the workflow and implementation plan, with no generated benchmark output or local profiles.

---

### Task 3: Validate the real GitHub critical path

**Files:**
- No repository file changes expected.

**Interfaces:**
- Consumes: the pushed task branch and its pull-request workflow run.
- Produces: measured worker durations and aggregate-gate status for the completion report.

- [ ] **Step 1: Push the task branch and open a ready pull request**

Run:

```bash
git push -u origin chore/parallel-hardening-ci
gh pr create --base main --head chore/parallel-hardening-ci \
  --title "ci: parallelize hardening gates" \
  --body-file /tmp/codex-usage-tracker-parallel-hardening-pr.md
```

Expected: GitHub returns the new PR URL.

- [ ] **Step 2: Watch all checks to completion**

Resolve the new PR number and run the repository task wrapper:

```bash
PR_NUMBER="$(gh pr view --json number --jq .number)"
/Users/Monsky/.codex/bin/codex-task pr-checks --json -- "$PR_NUMBER"
```

Expected: all worker jobs and `Hardening gates` pass.

- [ ] **Step 3: Compare actual duration to the baseline**

Run:

```bash
PR_NUMBER="$(gh pr view --json number --jq .number)"
RUN_ID="$(gh run list --branch chore/parallel-hardening-ci --event pull_request \
  --limit 1 --json databaseId --jq '.[0].databaseId')"
gh pr checks "$PR_NUMBER"
gh run view "$RUN_ID" --json jobs
```

Expected: the four hardening worker jobs overlap in time, the aggregate job starts after them, and the measured hardening critical path is reported without claiming more improvement than the timestamps prove.
