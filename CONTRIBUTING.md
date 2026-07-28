# Contributing to Maestro

Thanks for taking the time to contribute. This document covers everything from getting
the stack running locally to what CI will check before your pull request can merge.

## Before you start

- **[`CLAUDE.md`](https://github.com/Yigtwxx/Maestro/blob/main/CLAUDE.md) is the single source of truth** for architecture,
  conventions, and code standards. When this file and `CLAUDE.md` disagree, `CLAUDE.md`
  wins — please open an issue so we can fix the drift.
- Participation is governed by our [Code of Conduct](https://github.com/Yigtwxx/Maestro/blob/main/CODE_OF_CONDUCT.md).
- Found a security vulnerability? **Do not open an issue.** Follow
  [`SECURITY.md`](./SECURITY.md) instead.

## Local setup

Maestro runs three databases in Docker (PostgreSQL, MongoDB, Qdrant) while the backend,
frontend, and Ollama run on the host.

### The fast path

```bash
git clone https://github.com/Yigtwxx/Maestro.git
cd maestro

./scripts/dev.sh          # macOS / Linux
.\scripts\dev.ps1         # Windows
```

The script starts the Docker infra, creates the backend virtualenv, copies
`.env.example` → `backend/.env` and `frontend/.env.local.example` → `frontend/.env.local`,
runs Alembic migrations, seeds the marketplace, and launches both dev servers.
Pass `--skip-infra` if your databases are already up, or `--skip-seed` to skip seeding.

Backend lands on <http://localhost:8000> (API docs at `/docs`), frontend on
<http://localhost:3000>.

### The manual path

```bash
docker compose up -d                       # Postgres :5433, Mongo :27018, Qdrant :6333

cd backend
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt        # NOT requirements.txt — you need the test deps
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm install
cp .env.local.example .env.local
npm run dev
```

> Note that `scripts/dev.sh` installs `requirements.txt`, which is enough to *run* the
> backend but not to test or lint it. Install `requirements-dev.txt` before you start
> writing code.

### No API key required

You do not need a paid provider key to develop. Maestro ships a free local tier — an
open-weights model served through [Ollama](https://ollama.com):

```bash
ollama pull qwen3
ollama pull nomic-embed-text
```

Google Gemini also has a free tier if you prefer a hosted model
([get a key](https://aistudio.google.com/apikey), no credit card).

## Verification before you open a pull request

CI runs on every push and pull request to `main`. Run the same commands locally first —
these are copied verbatim from [`.github/workflows/ci.yml`](https://github.com/Yigtwxx/Maestro/blob/main/.github/workflows/ci.yml):

```bash
# Backend (Python 3.11)
cd backend
ruff check .
ruff format --check .
pytest

# Frontend (Node 20)
cd frontend
npm run lint
npm run type-check
npm run build
```

**The frontend has no test runner yet.** There is no `npm test` script — do not add one
to a feature PR without discussing it in an issue first.

## Dependency management

Both stacks pin dependencies for reproducible builds.

**Backend** uses the pip-tools convention: `requirements.in` / `requirements-dev.in`
hold the human-edited version ranges; `requirements.txt` / `requirements-dev.txt` are
**generated lockfiles** (pinned, hashed, platform-independent) — never edit them by
hand. To add or change a dependency, edit the `.in` file and regenerate with
[uv](https://docs.astral.sh/uv/):

```bash
cd backend
uv pip compile requirements.in -o requirements.txt --universal --python-version 3.11 --generate-hashes
uv pip compile requirements-dev.in -o requirements-dev.txt --universal --python-version 3.11 --generate-hashes -c requirements.txt
```

Commit the `.in` and `.txt` files together — CI's "Lock freshness check" fails if they
drift apart. `--universal` keeps one lock valid on Windows, macOS, and Linux.

**Frontend** pins exact versions in `package.json` (`.npmrc` sets `save-exact=true`,
so `npm install <pkg>` does the right thing) and `package-lock.json` locks the tree.
Routine version bumps arrive as weekly Dependabot PRs; don't bump versions in a
feature PR.

## Code standards

Condensed from [`CLAUDE.md`](https://github.com/Yigtwxx/Maestro/blob/main/CLAUDE.md) §5. Read that section before your first PR.

- **English only** in code, identifiers, comments, and commit messages. User-facing UI
  strings may be localized.
- **Backend** — Python 3.11+, type annotations are mandatory, `ruff` for both lint and
  format (88 columns). All endpoints are `async`. Request/response validation goes
  through Pydantic v2.
- **Frontend** — TypeScript `strict: true`, never `any` (use `unknown`), functional
  components only, Zustand for state, Tailwind for styling.
- **Business logic lives in `services/`.** Route handlers stay thin.
- **No magic numbers or strings.** Constants belong in `constants.py` / `constants.ts`.
- **New LLM providers are added as a new adapter class** in `services/llm_service.py`.
  Existing adapters are never modified — that is the whole point of the pattern
  (`CLAUDE.md` §11 and §15).

## Tests

Backend tests use `pytest` with `pytest-asyncio` in `asyncio_mode = "auto"`, so async
tests need **no** `@pytest.mark.asyncio` decorator:

```python
async def test_something() -> None:
    ...
```

Files live flat in `backend/tests/` and are named `test_*.py`. Tests run against SQLite
via `aiosqlite`, so they need no Docker infra. New behavior needs a test; bug fixes need
a regression test that fails before the fix.

## Things that will block a merge

These are hard rules, not style preferences (`CLAUDE.md` §9 and §15):

- **Never commit secrets.** No API keys, tokens, or `.env` files. `.env.example` carries
  placeholders only.
- **Never log, store in plaintext, or return an API key** to the frontend. Keys are
  AES-256-GCM encrypted at rest and decrypted only in server memory at call time.
- **Never bypass Alembic.** Schema changes ship as a migration; no hand-run SQL.
- **Always bound agent loops.** `max_iterations`, `max_review_iterations`, and
  `task_timeout_seconds` exist because an unbounded agent drains a user's provider quota.
- **Never let one user's data reach another.** Every query in Postgres, MongoDB, and
  Qdrant is scoped by user id.

## Commits and pull requests

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body explaining WHY, not what]
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Keep the subject under 72
characters and use the imperative mood ("add", not "added").

Branch off `main`, keep one logical change per pull request, and fill in the
[pull request template](https://github.com/Yigtwxx/Maestro/blob/main/.github/pull_request_template.md). Link the issue your PR
closes.

**Your pull request will not be squashed.** Squash merging is disabled on this repository,
so the commits you push are the commits that land on `main`. Write them as you want them
read: one logical change each, no `wip` or `fix typo` noise. Clean the branch up with an
interactive rebase before you ask for review.

### Sign your commits

Signing is **strongly encouraged** and not yet enforced, so an unsigned pull request will
still be reviewed. It is what lets a reader confirm the author of a commit is who the
commit says it is — see [Commit provenance](./SECURITY.md#commit-provenance). If you have
never set it up, SSH signing takes a minute and reuses the key format you already know:

```bash
ssh-keygen -t ed25519 -C "you@example.com (git signing)" -f ~/.ssh/id_ed25519_signing

git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519_signing.pub
git config --global commit.gpgsign true
```

Then add the **public** key (`~/.ssh/id_ed25519_signing.pub`) to your GitHub account under
*Settings → SSH and GPG keys*, choosing key type **Signing key** — an authentication key
does not verify commits. Your commits will show as *Verified*.

## Licensing of contributions

Maestro is distributed under the [Sustainable Use License](https://github.com/Yigtwxx/Maestro/blob/main/LICENSE) (fair-code). By
intentionally submitting a contribution for inclusion, you agree that:

1. Your contribution is licensed to the project under the same Sustainable Use License.
2. You grant the maintainer the right to relicense your contribution as part of the
   project (for example, to offer it under a commercial license for the hosted service,
   or to adjust the project license in the future).
3. You have the right to submit the contribution (it is your own work, or you are
   authorized to contribute it).

Opening a pull request constitutes acceptance of these terms — there is no separate
signature step or DCO sign-off. In particular, the relicensing grant in point 2 lets the
maintainer offer contributed code under a commercial license as part of the hosted
Maestro service without asking again. These terms are the substance of a CLA; a formal
CLA bot is intentionally not used while external contribution volume is low, and may be
added later without changing what you agree to here.
