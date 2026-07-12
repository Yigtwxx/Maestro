## Summary

<!-- What does this change, and why? Explain the reasoning, not the diff. -->

Closes #

## Type of change

- [ ] `feat` — new feature
- [ ] `fix` — bug fix
- [ ] `refactor` — behavior unchanged, code reorganized
- [ ] `test` — tests added or updated
- [ ] `docs` — documentation only
- [ ] `chore` — build, dependencies, tooling

## Verification

Everything below runs in CI
([`ci.yml`](https://github.com/Yigtwxx/maestro/blob/main/.github/workflows/ci.yml)).
Tick what you ran locally; leave a box unticked rather than guessing.

**Backend** (skip if untouched)

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest`

**Frontend** (skip if untouched)

- [ ] `npm run lint`
- [ ] `npm run type-check`
- [ ] `npm run build`

## Checklist

- [ ] No secrets, API keys, tokens, or `.env` files are committed.
- [ ] No code path logs, stores in plaintext, or returns a user's API key.
- [ ] Any schema change ships as an Alembic migration — no hand-run SQL.
- [ ] Any new LLM provider is a **new adapter class**; existing adapters are untouched.
- [ ] New behavior has a test; a bug fix has a regression test that failed before it.
- [ ] Code, identifiers, and comments are in English.
- [ ] I agree my contribution is licensed under the [Sustainable Use License](../LICENSE) and I grant the maintainer relicensing rights (see [CONTRIBUTING.md](../CONTRIBUTING.md#licensing-of-contributions)).

## Screenshots

<!-- Required for UI changes. Before and after, if the change is visual. -->
