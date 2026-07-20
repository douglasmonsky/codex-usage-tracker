# MCP-First Dashboard Transition Design

**Date:** 2026-07-19

**Status:** Revised after independent product, architecture, and release review;
implementation planning pending maintainer review

**Target:** Pre-1.0 product simplification

## Context

Codex Usage Tracker has grown into two overlapping products:

1. an increasingly capable MCP and companion-skill investigation system; and
2. a broad dashboard with many top-level workspaces, experiments, reports, and
   technical controls.

The MCP direction is the stronger differentiator. It can choose investigations,
explain evidence, recommend actions, and guide verification without requiring a
user to understand the tracker's internal report taxonomy. The dashboard remains
valuable for quick status, manual evidence browsing, configuration, and focused
drill-downs, but its current navigation presents mature and experimental surfaces
as peers. That density makes the product harder to understand and creates a
pre-1.0 quality promise the project does not need to make.

This transition makes MCP the primary analysis product and narrows the default
live React dashboard to the surfaces that are already useful and coherent. It
preserves advanced work rather than deleting it prematurely, while making maturity
explicit and maintaining a complete path for users whose MCP setup is unavailable.

## Product Decision

Dashboard policy uses three independent dimensions. They must not be collapsed
into one exposure enum:

- **Maturity:** `stable` or `experimental`.
- **Placement:** `primary`, `contextual`, or `hidden`.
- **Lifecycle:** `active`, `transitioning`, or `deprecated`.

This represents important combinations without exceptions. Diagnostics Notebook
is `experimental + primary + active`. Call Investigator is
`stable + contextual + active`. Cache And Context is
`experimental + hidden + transitioning` during the sunset window.

The live React dashboard remains a useful product, but it will no longer attempt
to expose every analytical capability. MCP owns diagnosis, orchestration,
recommendation, simulation, and most report generation. The dashboard owns quick
status, manual evidence browsing, configuration, and focused verification.

## Default Live Dashboard Contract

The default navigation of the live React dashboard contains:

1. **Overview**
2. **Calls**
3. **Threads**
4. **Limits**
5. **Diagnostics Notebook**
6. **Settings**

Call Investigator remains fully supported as a contextual route opened from
Overview, Calls, Threads, Diagnostics, Limits evidence, or MCP-produced targets.
It remains largely unchanged during this transition.

Diagnostics Notebook remains in the default navigation because it is useful for
technical exploration and support. Its page header clearly states that it is
highly experimental and may change before 1.0. This label communicates maturity
without making the workspace undiscoverable.

Limits remains a core workspace, including its statistical analysis. Remaining
usage, resets, allowance history, and evidence-backed interpretation are recurring
user questions. The statistical material may be refined later, but it is not
hidden merely because it is advanced.

The six-destination contract applies to the live React surface only. Static legacy
HTML remains a frozen compatibility product during this transition and is not
silently redefined as the simplified React dashboard.

## Feature Disposition

| Tab or area | Feature | Maturity | Placement | Lifecycle | Product treatment |
| --- | --- | --- | --- | --- | --- |
| Overview | Headline metrics | Stable | Primary | Active | Keep four or five trustworthy metrics with clear scope and timestamps. |
| Overview | Primary usage trend | Stable | Primary | Active | Keep one dominant trend visualization rather than several competing summaries. |
| Overview | High-confidence findings | Stable | Primary | Active | Show at most three findings with evidence and an MCP-oriented follow-up action. |
| Overview | Recent calls | Stable | Primary | Active | Keep a short path into Calls and Call Investigator. |
| Overview | 3D Usage Constellation | Experimental | Hidden | Transitioning | Reveal only through experimental exposure; remove before 1.0 if it does not prove a unique decision-making benefit. |
| Calls | Table, filters, sorting, and export | Stable | Primary | Active | Continue treating Calls as the principal manual evidence browser. |
| Calls | Selected-call summary rail | Stable | Primary | Active | Preserve essential accounting and access to Call Investigator. |
| Call Investigator | Aggregate call accounting and deep dive | Stable | Contextual | Active | Keep largely unchanged; do not place behind an experimental preference. |
| Call Investigator | Explicit raw/local context controls | Stable | Contextual | Active | Preserve the privacy permission and explicit local-action requirements. |
| Threads | Ranking, grouping, and call expansion | Stable | Primary | Active | Keep the conversation-level evidence workflow. |
| Threads | Secondary visualizations | Experimental | Contextual | Active | Avoid expanding them without a distinct user question. |
| Limits | Remaining usage, resets, and history | Stable | Primary | Active | Preserve the recurring allowance-status workflow. |
| Limits | Statistical analysis and evidence | Stable | Primary | Active | Keep visible; refine clarity and trust language in later work. |
| Diagnostics Notebook | Technical reports and evidence | Experimental | Primary | Active | Keep the tab and add a highly experimental page header. |
| Investigate | Agentic investigation workbench | Experimental | Hidden | Active | MCP becomes the primary interface; retain the page for opted-in users and direct links. |
| Investigate | Manual file, command, and churn exploration | Experimental | Hidden | Active | Preserve MCP/report services; stop expanding the manual UI. |
| Compression Lab | Profile, candidates, and simulation | Experimental | Hidden | Active | MCP owns orchestration; retain the dashboard as an optional visual workbench. |
| Cache And Context | Standalone lab | Experimental | Hidden | Transitioning | Preserve direct access during the compatibility window and replace each supported job explicitly. |
| Reports | Standalone report library | Experimental | Hidden | Transitioning | Preserve direct access and export behavior until job-level replacements pass. |
| Settings | Privacy, language, data scope, and status | Stable | Primary | Active | Keep as the dashboard's trust and configuration surface. |
| Settings | Experimental-feature control | Stable | Primary | Active | Place under Advanced and let users reveal hidden experimental navigation. |
| Navigation | Files, Commands, and Models aliases | Stable | Hidden | Deprecated | Remove shortcuts that redirect to unrelated destinations; preserve their destination capabilities. |
| Navigation | Search, time scope, and refresh | Stable | Primary | Active | Keep compact, broadly useful controls. |
| Navigation | Row limits and technical loading controls | Stable | Contextual | Active | Retain under an Advanced disclosure. |
| Legacy dashboard | Static compatibility surface | Stable | Contextual | Transitioning | Freeze feature work and retain through an explicit pre-1.0 removal decision. |
| Localization | Default dashboard and transition copy | Stable | Primary | Active | Maintain full locale coverage for stable navigation, maturity labels, notices, and Call Investigator. |
| Localization | Experimental page body copy | Experimental | Hidden | Active | Allow documented English fallback until a surface graduates. |

## Shipped Entry-Point Contract

The project currently ships multiple dashboard entry points. Simplification must
not pretend they are one surface.

| Entry point | Current/transition owner | Transition behavior | Removal or change gate |
| --- | --- | --- | --- |
| `codex-usage-tracker serve-dashboard --open` | Live React | Remains the recommended interactive/default command and opens `/react-dashboard.html`. | None; this is the stable live entry point. |
| `/react-dashboard.html` on an active server | Live React | Receives the six-destination default navigation and experimental preference. | Stable contract. |
| Persistent dashboard service canonical URL | Live React | Documentation and open actions must target `/react-dashboard.html`, including custom configured ports. | Service contract test and installed-package smoke must pass. |
| `/` on the localhost server | Legacy compatibility during the transition | Continues current behavior until a separately approved redirect decision. It must identify the recommended live React URL. | No redirect in the navigation simplification release. |
| `/dashboard.html` or configured legacy filename | Legacy static HTML | Frozen compatibility route with replacement notice and live React link when served. | Retained for at least two minor releases and until a 1.0 removal decision. |
| `codex-usage-tracker dashboard` | Legacy static generator | Continues generating frozen static HTML; no new dashboard features. | A static React replacement requires its own design. |
| `codex-usage-tracker open-dashboard` | Legacy static generator/opener | Continues opening frozen static HTML and clearly labels it static. First-run docs prefer `serve-dashboard`. | A static React replacement requires its own design. |
| MCP `generate_usage_dashboard()` | Legacy static generator | Remains compatibility output; it must not be described as the live simplified dashboard. | Separate MCP deprecation decision only. |
| MCP-produced evidence destination | Relative React target plus optional resolved origin | Uses the versioned destination contract below. | Must exist before any dashboard navigation is hidden. |
| Installed wheel | Both packaged surfaces | Must contain synchronized React assets and the frozen legacy surface. | Clean-build and installed-wheel checks are release blockers. |

Static mode remains useful for offline snapshots, but it does not gain the six-tab
React contract in this project. Static users receive accurate capability wording
and a documented route to the live dashboard when they need refresh, MCP bridges,
or contextual evidence loading.

## Experimental Preference And Route Catalog

Use one client-side setting named **Show experimental dashboard features** under
Settings > Advanced.

- It defaults to off for new browser origins.
- A shell-level application hook owns its in-memory state and persistence. Settings
  receives the current value and setter; Settings-local state is not the owner.
- Toggling it updates navigation immediately without a reload.
- It is stored locally per browser origin. Ad hoc ports, the persistent-service
  port, and file/static origins may therefore have independent values; the UI and
  documentation state this explicitly.
- When enabled, navigation adds Investigate and Compression Lab under a visually
  separated **Experimental** group.
- Direct links to experimental or transitioning routes continue to work while the
  preference is off. The destination shows its maturity or transition banner, but
  visiting a link does not persist the preference.
- Existing route identifiers remain valid throughout the compatibility window.

Diagnostics Notebook does not depend on this preference. It remains visible and
uses the shared experimental-banner component so its maturity is unmistakable.

Create one route catalog rather than only a visible-navigation registry. Every
route entry declares:

- route identifier and canonical label;
- `maturity`, `placement`, and `lifecycle`;
- navigation group and eligibility;
- optional banner and replacement copy;
- return-label behavior;
- refresh, export, and copy-link capabilities; and
- privacy-safe destination parameters.

Route validation and rendering remain exhaustive consumers, but a coherence test
ensures every valid route is rendered and cataloged. Visible navigation is derived
from the catalog. URL cleanup, Call Investigator return labels, exports, keyboard
shortcuts, and refresh exceptions must not infer labels only from visible items.

## MCP Readiness And Manual Fallback

MCP-first positioning is valid only when users can discover whether conversational
analysis is ready and recover when it is not.

Overview and Settings expose a stable **Conversational analysis** status with these
states:

- **Ready:** local setup/runtime checks prove the plugin and MCP launcher are
  configured. The UI must not claim that the current Codex task has loaded the MCP
  tools when that fact cannot be observed.
- **Restart required:** setup is installed, but the user still needs to restart
  Codex or open a fresh task for plugin discovery.
- **Unavailable:** a local configuration or runtime check failed.
- **Unknown:** the static dashboard or current server payload cannot prove status.

Every non-ready state provides the exact next action: run setup or doctor, restart
Codex/open a fresh task, or open Settings for details. Overview retains a visible
manual analysis path while MCP is unavailable: Calls, Threads, Limits, Diagnostics,
and one action to reveal experimental workbenches for the current browser origin.

Acceptance covers fresh install before restart, successful discovery setup,
discovery/runtime failure, unknown status, static dashboard, and unavailable live
service. The UI never claims access to OpenAI account state or a live MCP session it
cannot verify.

## Dashboard Destination And Privacy Contract

Define `codex-usage-tracker-dashboard-target-v1` before hiding any route. It is a
renderer-independent target descriptor shared by MCP recommendations and dashboard
copy-link actions.

Required fields:

- `view`;
- canonical aggregate identifiers such as `record_id`, `thread_key`, diagnostic
  fact key, or Limits evidence key;
- normalized, allowlisted filters and history scope;
- `privacy_mode`;
- `relative_url`;
- optional `absolute_url`; and
- a fallback launch/open instruction when no live origin is reachable.

Origin resolution follows this order:

1. use a configured persistent service only after its loopback health endpoint
   proves reachable, including its custom port;
2. use an explicitly known active `serve-dashboard` origin when available; or
3. return the relative target with `codex-usage-tracker serve-dashboard --open`
   guidance instead of fabricating an absolute URL.

Thread destinations use `thread_key` as the canonical identifier. Existing
display-name `thread` URLs remain compatibility inputs, but new MCP targets and
copy-link actions do not depend on mutable or privacy-transformed labels.

Every destination type has a parameter allowlist. Links and copied prompts never
include API tokens, raw/indexed text, local paths, raw-context entries, project
labels disallowed by the selected privacy mode, or unreviewed free-form search
text. Normal, redacted, and strict modes have synthetic contract tests.

**Open evidence** resolves and opens a dashboard target. **Ask Codex** means a
user-initiated **Copy investigation prompt** action until Codex provides a supported
browser-to-task invocation protocol. The clipboard payload contains only aggregate
identifiers, scope, a concise question, and the dashboard target. It never
transmits data or includes raw/indexed content automatically.

## Sunset Job-Parity Contract

No tab leaves default navigation until its supported user jobs have a documented
replacement and the replacement passes its acceptance check.

| Existing job | Replacement | Required parity before hiding/removal |
| --- | --- | --- |
| Cache trend and context-pressure summary | Overview summary plus MCP `cache_failure` investigation | Same scope, caveats, and supporting aggregate Calls must be reachable. |
| Cross-thread cache/cold-resume comparison | MCP investigation plus Threads/filtered Calls evidence | Ranking, selected-thread evidence, and methodology wording must remain available. |
| Cache heatmap | Experimental contextual viewer or intentional removal | A decision record must show that the heatmap answers a unique user question; otherwise mark it intentionally removed. |
| Selected cache/thread evidence | Threads and Call Investigator | The same canonical thread/call records must open through dashboard targets. |
| Report selection/library | MCP investigation suggestions and report pack | Users can select the same supported report intent without undocumented CLI knowledge. |
| Report explanation and caveats | MCP report/action brief | Methodology, scope, confidence, and caveats remain visible. |
| Report evidence opening | Dashboard target contract | Every included evidence row can open the matching Call Investigator or contextual view. |
| Report export/artifact | Existing MCP/CLI export contract | Export remains available and documented before the Reports route is removed. |

During the transition, Cache And Context and Reports remain directly reachable with
replacement notices. Route removal is a separate decision after at least two minor
releases, successful parity checks, and explicit maintainer approval.

## Transition Releases And Phases

Phases are grouped into release boundaries so the replacement exists before
discoverability changes.

### Release N: Foundation Only

Release N does not hide or remove any navigation item.

#### Phase 0: Lock Contracts And Baselines

- Approve this revised design and create the detailed implementation plan.
- Add the entry-point, route-catalog, destination, privacy, and sunset-parity
  contracts to repository documentation.
- Capture current route, navigation, entry-point, and generated-asset behavior in
  tests before changing it.
- Record the known-good package version and commit used for rollback.

#### Phase 1: Establish Route And Exposure Infrastructure

- Add the complete route catalog with independent maturity, placement, and
  lifecycle fields.
- Add the shell-owned experimental preference and Settings > Advanced control.
- Add shared experimental and transition banners.
- Keep existing navigation visibility unchanged in Release N.
- Cover immediate toggle behavior, reload, restricted/malformed storage,
  per-origin semantics, direct links, return labels, exports, keyboard navigation,
  and localization.

#### Phase 2: Establish Readiness And Destination Bridges

- Add the conversational-analysis readiness model and recovery card.
- Implement `codex-usage-tracker-dashboard-target-v1` with stable identifiers,
  privacy allowlists, and origin resolution.
- Add `thread_key` route selection while retaining display-name compatibility.
- Implement **Open evidence** and privacy-safe **Copy investigation prompt**.
- Update MCP verification payloads and the companion skill to use the shared
  target descriptor.
- Prove MCP-unavailable manual fallback and MCP-to-evidence completion before any
  route is hidden.

#### Phase 3: Harden Packaging And Release Gates

- Build React deterministically from a clean checkout.
- Assert no generated diff under the packaged React asset directory.
- Build the wheel and smoke both React and legacy entry points from the installed
  package.
- Make the release-candidate browser suite a required gate.
- Capture a synthetic baseline of every default, contextual, experimental, and
  transitioning route.

### Release N+1: Change Default Discoverability

Release N+1 ships only after all Release N bridge and packaging gates pass.

#### Phase 4: Simplify Navigation And Shell Density

- Reduce default React navigation to the six approved tabs.
- Hide Investigate and Compression Lab behind the experimental preference.
- Remove Files, Commands, and Models aliases.
- Move technical row-loading controls into Advanced.
- Keep search, time scope, history scope, and refresh easy to find.
- Add the highly experimental header to Diagnostics while keeping it primary.
- Remove Cache And Context and Reports from navigation only after their job-parity
  checks pass; retain direct routes and transition notices.

#### Phase 5: Refine The Stable First-Run Experience

- Simplify Overview to a small set of metrics, one main trend, bounded findings,
  readiness/recovery, and recent calls.
- Evaluate Usage Constellation behind experimental exposure.
- Keep Calls, Threads, Limits, Call Investigator, and core Settings behavior
  functionally stable.
- Improve labels and empty states only where the transition exposes confusion;
  avoid unrelated redesign work.

#### Phase 6: Reposition Documentation

- Lead README and first-run guidance with MCP and conversational analysis.
- Describe the live React dashboard as the evidence companion.
- Document MCP-unavailable fallback, experimental access, static legacy behavior,
  and sunset replacements.
- Regenerate screenshots from synthetic data using the default live React
  navigation.
- Preserve full supported-locale coverage for stable/default-shell transition copy.

### Release N+2 Or 1.0 Review: Removal And Graduation Decisions

- Run the task-based evaluation and review support/issue evidence.
- Graduate, retain, or remove each experimental surface using explicit evidence.
- Consider deleting Cache And Context or Reports routes only after two minor
  compatibility releases and maintainer approval.
- Consider redirecting or removing legacy entry points only in a separate design
  and release.
- Never combine route deletion, legacy removal, and the initial navigation change
  into one release.

## Verification And Release Gates

Every release boundary has explicit entry and exit criteria.

| Boundary | Entry criteria | Exit criteria | Rollback trigger |
| --- | --- | --- | --- |
| Release N foundation | Approved design and clean baseline | Route catalog, readiness states, target/privacy contract, package sync, and installed-wheel tests pass with navigation unchanged | Any stable route, privacy, package, or entry-point regression |
| Release N+1 discoverability | Release N shipped successfully; all replacement bridges operational | Six-tab default, experimental preference, transition notices, task evaluation, accessibility, localization, and full release gate pass | Broken Call Investigator or Limits flow; dead evidence link; failed MCP-unavailable recovery; packaged UI mismatch; serious privacy/accessibility regression |
| Release N+2/1.0 decision | At least two compatible minor releases and completed parity checks | Explicit maintainer decision for each graduation, route removal, and legacy action | Missing parity evidence, unresolved support need, or any stable contract dependency |

Required technical gates:

- dashboard lint, typecheck, unit tests, dependency/governance checks, and build;
- route-catalog coherence and all destination/privacy contract tests;
- deterministic React build followed by a clean generated-asset diff assertion;
- wheel/sdist build plus installed-package React and legacy smoke tests;
- release-candidate browser matrix for preference off/on, direct experimental and
  transitioning routes, Call Investigator returns, mobile, compact desktop,
  keyboard, focus, reduced motion, 200% zoom, and serious/critical Axe findings;
- supported-locale coverage for navigation, toggle, Diagnostics banner, maturity
  wording, readiness/recovery, and transition notices;
- synthetic documentation screenshots and privacy scan; and
- existing full Python/release checks for MCP, CLI, HTTP, schema, and packaging
  compatibility.

## Product Success Measures

Because the project does not add telemetry or hosted analytics, success is measured
with synthetic dogfood runs, documented maintainer walkthroughs, issue/support
evidence, and optional moderated usability checks.

Representative tasks:

1. determine what drove usage recently and open its evidence;
2. identify the heaviest thread and inspect one contributing call;
3. check remaining Limits and understand the statistical evidence;
4. complete a token-waste investigation with MCP available;
5. recover or complete a useful manual investigation when MCP is unavailable; and
6. open Diagnostics and correctly recognize its experimental maturity.

Release N+1 requires:

- every task to have a documented happy path and non-ready/error path;
- zero dead-end primary navigation destinations;
- exact evidence-target success for every tested MCP finding;
- no more than one navigation wrong turn in a moderated first-use walkthrough;
- no participant mistaking Diagnostics or hidden Labs for stable analysis promises;
- Call Investigator and Limits completion equal to the current baseline; and
- all privacy, accessibility, localization, and installed-package gates passing.

Rollback is triggered when any privacy or stable-contract failure occurs, when an
installed wheel contains stale navigation assets, when any evidence link resolves
to the wrong record, or when more than one representative task lacks a working
happy path or recovery path.

## Success Criteria

The transition is successful when:

- a new live React user sees exactly the six approved default destinations;
- stable and experimental maturity is obvious without external documentation;
- Call Investigator remains fully reachable and functionally unchanged;
- Limits retains status, history, and statistical analysis;
- Diagnostics remains primary and visibly labeled highly experimental;
- Investigate and Compression Lab remain available without appearing stable by
  default;
- Cache And Context, Reports, and navigation aliases no longer compete for primary
  attention after job parity is proven;
- users have an actionable path when MCP is ready, unavailable, or unknown;
- MCP answers can target the exact supporting dashboard evidence using canonical
  identifiers;
- no default/shareable link or copied prompt weakens the privacy boundary;
- static legacy behavior and live React behavior are accurately distinguished;
- packaged React assets match reviewed source;
- stable MCP, CLI, HTTP, and JSON contracts remain compatible; and
- README and first-run guidance consistently present MCP as the primary analysis
  experience.

## Non-Goals

- Deleting MCP, HTTP, CLI, or report contracts merely because a tab is hidden.
- Redesigning Call Investigator.
- Removing Limits statistical analysis.
- Hiding Diagnostics Notebook from normal navigation.
- Replacing the dashboard with a chat UI.
- Inventing a browser-to-Codex invocation protocol.
- Adding telemetry or hosted analytics to measure adoption.
- Reworking the entire visual system during the navigation transition.
- Building a static React dashboard in this project.
- Removing or redirecting the legacy dashboard in the same release as simplified
  navigation.

## Risks And Mitigations

### Hidden functionality appears deleted

Preserve direct routes for two minor releases, document experimental access, and
add transition notices with job-level replacement workflows.

### MCP is unavailable during first use

Expose conservative readiness states, exact recovery steps, and stable manual
paths. Do not claim current-task MCP discovery when it cannot be observed.

### Evidence links open the wrong data or leak private metadata

Use canonical identifiers, a versioned target schema, per-destination allowlists,
privacy-mode transformations, loopback health checks, and synthetic negative tests.

### Entry points promise different products

Maintain the explicit surface matrix and test every command/URL from the installed
wheel. First-run guidance names live React as the interactive default and static
legacy as compatibility output.

### Experimental labels become permanent excuses

Assign each experimental surface a Release N+2/1.0 graduation or removal decision
with task and parity evidence.

### Stable pages absorb all removed complexity

Move only essential summaries. Do not recreate Reports, Cache And Context, or the
Investigator workbench inside Overview.

### Experimental preference becomes another fragmented flag system

Use one shell-owned browser-local preference and document per-origin behavior. Do
not add server, CLI, environment, and database variants for the same choice.

### Published wheels contain stale dashboard assets

Rebuild from a clean checkout, assert the generated diff is clean, and smoke the
installed wheel's React and legacy entry points before release.

### Localization or accessibility degrades on hidden routes

Require stable transition copy in every supported locale and run the release-
candidate accessibility matrix in both preference states and on direct routes.

## Rollback

Release N records the known-good package version and commit. Release N+1 can be
rolled back by restoring that reviewed version or by shipping a focused metadata
reversion that restores prior navigation visibility. Routes and backend contracts
remain available, so rollback requires no data migration or contract restoration.

Any privacy regression, wrong-record evidence link, broken Call Investigator or
Limits path, stale packaged UI, or failed MCP-unavailable recovery blocks release
or triggers rollback. Direct-route deletion and legacy-dashboard removal occur only
after the separate Release N+2/1.0 decision and therefore are not part of the
initial rollback surface.
