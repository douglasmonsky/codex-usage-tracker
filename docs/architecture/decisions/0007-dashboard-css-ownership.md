# Dashboard CSS Ownership

Status: Accepted for the dashboard redesign experiment

## Context

The current dashboard has split its original monolithic stylesheet into 14 files,
but selectors and tokens remain largely global. Feature files repeat custom
properties, stylesheet load order affects behavior, and ownership is not clear
from an importing component. Adding Sass would reduce some textual repetition
without fixing selector reach or package ownership.

## Decision

- Use native CSS custom properties for semantic runtime tokens and CSS Modules
  for component, entity, feature, and route styles.
- Use cascade layers in this order: `reset`, `tokens`, `base`, `components`,
  `utilities`, `overrides`.
- Limit global CSS to reset, semantic tokens, document defaults, focus behavior,
  reduced-motion defaults, and a small reviewed utility set.
- Keep feature styles beside their owner. Cross-feature selectors and selectors
  that reach through another component's DOM are prohibited.
- Keep selector specificity shallow. State is expressed through local classes or
  stable data/ARIA attributes, not DOM-depth coupling or `!important`.
- Use Stylelint for validity, duplicate/conflicting rules, selector complexity,
  token policy where practical, and module naming. Existing global styles are
  migrated with their owning roadmap units rather than rewritten all at once.
- Do not add Sass. Reconsider only if a later ADR demonstrates a recurring need
  that native nesting, custom properties, and modules cannot express clearly.

## Consequences

- Style ownership follows component ownership and parallel work has a smaller
  collision surface.
- Semantic tokens can support themes, chart colors, contrast fixes, and runtime
  state without recompilation.
- Existing global CSS remains transitional debt until each route migrates, so
  Stylelint configuration must identify precise legacy exceptions rather than
  ignore the stylesheet tree.
- CSS Modules and cascade layers become part of visual-contract testing.
