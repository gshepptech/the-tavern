# Preset: UI & visual polish

Make the interface look **considered, not generated**. One concrete, defensible improvement at a time. Never restyle a coherent design for its own sake — match and extend the language the app already has.

Each item is `[applies when] -> what good looks like`. If the `[applies when]` condition is not true of this codebase, **skip the item** — do not invent the feature, do not propose adding it, do not score it.

- **Visual hierarchy** — [any rendered screen] -> the most important thing on each screen looks the most important; type scale and weight are deliberate, not uniform.
- **Spacing rhythm** — [any UI] -> spacing expresses grouping; related things sit closer, unrelated things further. Not everything on one uniform gap.
- **Empty / loading / error states** — [any view that fetches or lists data] -> each has a designed empty, loading, and error state — no blank flash, no spinner-forever, no raw error string.
- **Type & font choice** — [app sets typography] -> a real scale and a deliberate pairing; not default system-stack everywhere, not the generic Inter-on-white look.
- **Colour & theme** — [app defines colours/theme] -> one or two dominant colours plus a sharp accent; sufficient contrast in every theme shipped; no evenly-distributed rainbow, no purple-gradient cliché.
- **Component consistency** — [reused components: buttons, inputs, cards] -> the same role looks the same everywhere; variants are intentional, not accidental drift.
- **Density & alignment** — [tables, forms, lists] -> aligned to a grid; nothing visually ragged; comfortable density for the content.
- **Motion** — [app already animates, or transitions feel abrupt] -> motion explains a state change (enter/exit/reorder), it does not decorate. Respects `prefers-reduced-motion`.
- **Responsive** — [app is used at more than one viewport] -> no horizontal body scroll on mobile; touch targets adequate; layout reflows rather than squashes.
- **Iconography & imagery** — [app uses icons/images] -> consistent set and weight; images have intrinsic sizing so layout doesn't jump.

When you propose a UI item, name the exact screen/component and the specific fix — never "improve the styling".
