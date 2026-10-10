# Privacy model

This document is the contract: what may live in this repository, and where everything
else must go.

## The three layers

| Layer | Contents | Where |
| --- | --- | --- |
| **Code** | application, migrations, importer, tests, docs | this repository (public) |
| **Configuration** | app settings, DB credentials, UI token | `../deploy/config.toml`, `../deploy/.env` — **outside the git working tree** |
| **Data** | MySQL database, uploaded images, thumbnails, backups | MySQL datadir, `../deploy/media/`, `../deploy/backups/` |

`deploy/` sits beside the repository, not inside it. That is deliberate: `.gitignore`
protects against carelessness, but physical separation protects against `git add -f`,
a broken ignore rule, or a `git commit -a` in the wrong directory.

## Rules for contributors

1. **No real person's data, ever** — not in code, tests, fixtures, screenshots, commit
   messages, or issue text.
2. **Tests use synthetic fixtures only.** The canonical example is created by
   `tests/fixtures/make_fixture.py`: a fictional person and a generated colour-block
   image. If you need a new fixture, generate it.
3. **Screenshots must come from the demo dataset**, never from a real deployment.
4. **No hard-coded paths, hosts, ports or credentials.** Read them from the config /
   environment (`ARCHIVE_*`).
5. **Dates in examples are obviously fake** (`1990-01-01`), never a value copied out of
   a real archive.
6. Names of features stay generic: *person*, *partner*, *family* — never a real name, and
   not "girlfriend" either (the system is relationship-generic by design).

## Guards

- `.gitignore` — blocks secrets, databases, media, build output.
- `hooks/pre-commit` — dependency-free. Blocks private paths, and greps staged lines
  against a keyword denylist that lives **outside** the repo
  (`$ARCHIVE_DENYLIST`, default `~/.config/kinship-archive/denylist.txt`). Missing
  denylist → the content check silently skips, so CI and third-party clones are
  unaffected. Install with `bash hooks/install.sh`.
- `gitleaks` in CI — second net for credential-shaped strings.

## If something leaks

Assume the history is permanent until proven otherwise:

```bash
# 1. rotate the secret immediately (DB password, UI token)
# 2. rewrite history
git filter-repo --path <leaked-path> --invert-paths
# 3. force-push, then ask the host to purge caches / forks
```

Prevention is far cheaper than this procedure. When in doubt, put it in `deploy/`.

## Operational notes that touch privacy

- MySQL binds to `127.0.0.1` only; the app binds to the LAN interface with a token.
- `deploy/.env` should be `chmod 600`.
- Backups are plain `mysqldump` output — they contain everything, so they live in
  `deploy/backups/` and are never synced to a cloud folder.
- Keep `deploy/` out of iCloud/Dropbox/Time-Machine-network paths you don't control.
