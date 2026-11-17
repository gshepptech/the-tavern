# Preset: performance

Make the app measurably faster or lighter, guided by evidence (a measurement, a profile, or a clear algorithmic fact), never by guesswork. Do not trade correctness or readability for a micro-optimisation that doesn't matter.

Each item is `[applies when] -> what good looks like`. If the `[applies when]` condition is not true of this codebase, **skip the item**. Do not invent it.

- **N+1 and redundant queries**: [app talks to a database or API in loops] -> batched/joined access instead of per-item round-trips.
- **Unnecessary work**: [hot paths, render loops, request handlers] -> no recomputing what can be memoised or hoisted; no work done that its result is never used.
- **Over-fetching**: [app fetches data] -> request only the fields/rows needed; paginate large sets.
- **Frontend bundle**: [app ships JS to a browser] -> no large avoidable dependency pulled in for a trivial use; code-split heavy routes; no shipping dev-only code.
- **Render performance**: [component UI with lists/updates] -> stable keys, no needless re-renders, virtualise very long lists.
- **Caching**: [expensive pure computations or static assets] -> cache what is safe to cache; set sensible cache headers on static assets.
- **Blocking work**: [request handlers / main thread] -> heavy work isn't blocking the event loop or the UI thread; offload or stream.
- **Asset weight**: [app serves images/fonts/media] -> right-sized and compressed; modern formats; lazy-loaded below the fold.
- **Startup / cold path**: [app has a measurable startup or first-load] -> the critical path isn't doing deferrable work eagerly.

State the evidence for every item: the query count, the measured time, the bundle bytes, or the complexity fact. An item you can't ground in a measurement scores low on confidence.
