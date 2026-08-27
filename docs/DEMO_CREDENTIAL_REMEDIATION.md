# Public Demo-credential exposure — state and exact remediation

## What is exposed

The public preview at `https://lessonforge-tw-lucas.lucas66666677.chatgpt.site`
still ships this, verbatim, inside the JavaScript bundle
`/_next/static/chunks/LessonForgeApp-7rBPsJXp.js`:

```
Demo 帳號
Owner：owner@demo.lessonforge.tw
Teacher：teacher@demo.lessonforge.tw
密碼：LessonForgeDemo!2026
```

Verified 2026-08-27 by fetching that chunk and grepping it. Of the six chunks
the page loads, it is the only one that contains any of those strings.

## What is already fixed, and what that did not fix

`main` is clean. Checked at `?ref=main`, not inferred from a PR diff:

- `app/pages/LoginPage.tsx` — form defaults are `email: ""` / `password: ""`,
  and the `demo-accounts` block is gone.
- `services/api/lessonforge/config.py` — `demo_owner_password` and
  `demo_teacher_password` both default to `""`.
- `scripts/seed.py` — raises unless both passwords are set to at least 12
  characters, and its `__main__` block skips seeding entirely when
  `APP_ENV=production`.
- `README.md` — states that the online environment offers no shared public
  admin credentials.
- `git grep LessonForgeDemo` on `main` returns nothing.

A local `npm run build` from `main` produces a `dist/` in which
`grep -ra "LessonForgeDemo\|Demo 帳號" dist/` returns **nothing**. So a rebuild
is genuinely sufficient to clear the page; there is no second source of the
string still hiding in the tree.

None of that touched the deployed artifact. The frontend is hosted on OpenAI
Sites, not on Render: `render.yaml` declares only `lessonforge-tw-api-lucas`,
so merging to `main` rebuilds the API and cannot rebuild the page carrying the
credentials. That host is still serving a pre-merge build.

Nor did it touch the database. `scripts/seed.py`'s `ensure_user` only creates a
user that is missing — it never rewrites an existing `password_hash` — so the
two Demo rows in the live database still carry the hash of the publicly
displayed password. **The credentials on that page very likely still
authenticate.** "Likely" is the honest strength: they were deliberately not
used to test this.

## Owner action 1 — republish the frontend

Nothing about this needs a secret.

```bash
git checkout main && git pull
npm ci
npm run build
```

Confirm the build is clean before publishing anything:

```bash
grep -ra "LessonForgeDemo\|Demo 帳號" dist/ ; echo "exit=$?"
```

`exit=1` with no output is the pass condition. Then publish `dist/` through the
same OpenAI Sites deploy flow that produced version 2 (recorded in
`STATUS.md`); the target app project is `appgprj_6a7b360806788191a56c6dc6ea3dc60b`,
from `.openai/hosting.json`, which `build/sites-vite-plugin.ts` copies into
`dist/.openai/hosting.json` on every build.

Verify from outside afterwards — the chunk hash changes on rebuild, so read the
hashes off the page rather than reusing the one above:

```bash
BASE=https://lessonforge-tw-lucas.lucas66666677.chatgpt.site
curl -s "$BASE/" | grep -o '/_next/static/chunks/[A-Za-z0-9._-]*\.js' | sort -u |
  while read -r chunk; do curl -s "$BASE$chunk"; done |
  grep -c 'LessonForgeDemo\|demo\.lessonforge\.tw'
```

`0` is the pass condition. Until it is `0`, the fix has had no effect on
anything a member of the public can reach.

## Owner action 2 — deactivate the seeded Demo accounts

Republishing removes the advertisement. It does not close the accounts, and the
password is now public regardless of whether the page still shows it.

`is_active` is enforced on both entry points — `lessonforge/api.py`'s login and
`lessonforge/dependencies.py`'s session lookup — so setting it false is a
complete, reversible kill switch. That is preferable to rotating the password:
the demo data stays intact for reference, and `--reactivate` undoes it if the
accounts are ever wanted back behind a private password.

`scripts/disable_demo_accounts.py` does exactly this. It is a dry run by
default and writes nothing without `--apply`:

```bash
DATABASE_URL="postgresql://..." python scripts/disable_demo_accounts.py
DATABASE_URL="postgresql://..." python scripts/disable_demo_accounts.py --apply
```

It targets `DEMO_OWNER_EMAIL` and `DEMO_TEACHER_EMAIL` — the same settings
`seed.py` uses — unless `--email` is passed, which may be repeated.

Running it against the live database is an owner action and was not performed
here.

## Order

Either order closes the hole; both are needed. Doing action 2 first is
marginally better, because it makes the credentials useless immediately rather
than waiting on a rebuild-and-publish cycle.
