<!-- Thanks for the contribution! Keep the diff focused and the local checks green. -->

## What does this change?

<!-- A short summary. What and why, not just how. -->

## Which crew member(s)?

<!-- e.g. smith, warden, marketplace-wide -->

## Related issue

Closes #

## Checklist

- [ ] `python3 .github/scripts/validate_manifests.py` passes
- [ ] `python3 .github/scripts/check_js.py` passes (if JS changed)
- [ ] The other `.github/scripts/check_*.py` checks pass (see CONTRIBUTING.md)
- [ ] `cd plugins/<name> && uv run --with pytest python -m pytest -q` passes (if the plugin has tests)
- [ ] Bumped the plugin `version` and updated its `README.md` (if behavior changed)
- [ ] Updated the root `README.md` Crew table / `CHANGELOG.md` (if user-facing)
