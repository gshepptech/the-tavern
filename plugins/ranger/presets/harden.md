# Preset: harden — security & robustness

Reduce the ways this app can be broken, abused, or made to leak. Ground every finding in real code paths and, where possible, a concrete failing case. Do not add heavyweight machinery the app's threat model doesn't warrant.

Each item is `[applies when] → what good looks like`. **If the `[applies when]` condition is not true of this codebase, skip the item — do not invent the feature or propose adding it.** (Example: an SSO/session item when the app has no authentication at all → skip; do not propose building auth.)

- **Input validation** — [app accepts external input: forms, query params, request bodies, uploads] → inputs are validated/whitelisted at the boundary; malformed input is rejected cleanly, not trusted.
- **Injection** — [app builds SQL, shell, HTML, or template strings from input] → parameterised queries / proper escaping; no string-concatenated queries or `innerHTML` of untrusted data.
- **AuthN** — [app has authentication] → credentials handled safely; sessions expire and invalidate on logout; no auth secrets in client code.
- **AuthZ** — [app has multiple users or roles] → every protected action re-checks the caller's authority server-side; no relying on hidden UI; no IDOR (object access by guessable id without an ownership check).
- **Secrets** — [repo/config contains keys or connection strings] → no secrets committed; loaded from env/secret store; not logged.
- **Output & error hygiene** — [app renders user data or returns errors] → user content escaped on render; errors don't leak stack traces, queries, or internal paths to the client.
- **Dependencies** — [app has a lockfile] → no known-vulnerable pinned deps that a safe upgrade fixes; flag risky ones.
- **Transport & headers** — [app serves HTTP] → security-relevant headers set where they belong; cookies `HttpOnly`/`Secure`/`SameSite` as appropriate.
- **Rate & abuse** — [public write/auth endpoints exist] → obvious abuse (brute force, unbounded upload) has a basic guard.
- **Error handling that hides failures** — [try/catch or equivalent present] → no empty catch that swallows a real failure; no default-on-error that masks a security-relevant fault.

Prefer a small, correct fix at the true boundary over a broad framework. If a finding is only theoretical for this app's threat model, score its value honestly (often below the floor).
