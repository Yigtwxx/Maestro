# Invariant rule fixtures

Test data for `.semgrep/maestro.yml`, exercised by the `Invariants (semgrep,
blocking)` job in `.github/workflows/security.yml`.

`backend/app/services/bad.py` contains one deliberate violation per rule;
`good.py` contains the shapes that must **not** be reported, including the two
spellings of a Qdrant user scope that `memory_service` actually uses.

The directory nesting is load-bearing. The rules in `maestro.yml` are anchored
to `/backend/app/**` so that they apply to the real application tree and nothing
else; reproducing that prefix under `fixtures/` is what lets the same file be
checked against the fixtures without loosening the rule's own paths.

These files are never imported, executed, linted or type-checked. They are
matched as source text by semgrep's AST patterns, so undefined names and
unresolvable imports in them are intentional and harmless.

One trap worth knowing before debugging a "the fixtures stopped matching"
failure: semgrep skips dot-directories, so scanning `.semgrep/fixtures` in place
reports zero findings and looks exactly like a broken rule set. The workflow
copies this directory to a plain path first, and asserts that two files were
actually scanned.

## Changing a rule

Update the fixture in the same commit and adjust `EXPECTED` in the workflow's
verification step. A rule whose expected count is not asserted is a rule that
can silently stop matching.
