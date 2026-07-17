# Threads Table Compact Redesign

**Date:** 2026-07-17
**Status:** Approved
**Scope:** React dashboard Threads table presentation

## Problem

The custom virtualized Threads grid does not inherit the dashboard's normal sortable-header styling. Native browser buttons therefore appear in the header, the disclosure chevron shifts row cells out of alignment, all twenty columns render by default, and long thread identifiers wrap across multiple lines. Summary-only API rows also show unloaded model and effort values as prominent action-like labels. Together these defects make the table read like an unfinished debug surface.

## Chosen Design

The table remains a virtualized, single-open thread accordion. Its default presentation becomes scan-first:

- show Thread, Latest, Turns, Total Tokens, Cache %, Context %, Est. Cost, Codex Credits, and Cold Resume Risk by default;
- keep every other metric available through the existing **Columns** control;
- reset sortable header buttons to the dashboard visual language, including hover and focus-visible states;
- place the disclosure chevron inside the identity cell so headers and rows share the same column boundaries;
- keep the identity column frozen while horizontally scrolling advanced columns;
- truncate long identifiers to one line and expose the full value through the title tooltip;
- render unavailable model, effort, and initiator metadata as quiet, human-readable placeholders instead of blue action-like pills;
- retain dense/roomy modes, keyboard disclosure, virtualization, URL state, and explicit call actions.

The preference storage key is versioned for this redesign so existing all-columns-visible state does not prevent the new default from taking effect. Users can still restore or customize visibility normally.

## Accessibility And Responsive Contract

Sortable headers retain specific accessible names and `aria-sort`. The frozen identity cell, disclosure state, and full thread-name tooltip do not alter keyboard order. Focus indicators remain visible, color is not the only state signal, and narrow screens continue collapsing the leaderboard to the identity column while expanded call evidence stacks vertically.

## Verification

Synthetic tests must cover the new default visibility, column sizing, humanized metadata, full-name access, and disclosure alignment structure. Browser verification must confirm that native gray controls are gone, only the scan-first columns appear initially, long IDs no longer wrap, Columns can reveal advanced metrics, expansion loads 100 calls at a time, horizontal scrolling retains identity, and the console has no errors.
