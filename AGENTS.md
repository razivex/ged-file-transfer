# Agent / AI instructions — GED File Transfer

## Credentials and GitHub (mandatory)

1. **Never commit real credentials** — no passwords in source, commits, PRs, or issues.
2. **Single secrets file:** `ged-file-transfer/.env` (gitignored). Do not put real passwords in `.env.example`.
3. **Before every `git push` / PR:** confirm `.env` is not staged; search diffs for secrets.
4. **Never print secrets** in logs (directory passwords, DB password).
5. **Never read `.env`.** Grok is denied `Read`/`Edit` of `.env` and `.env.local` via `.grok/config.toml`. Use `.env.example` for the key list. Do not dump, cat, grep, or open `.env`.

## Layout

```text
ged-file-transfer/          ← transfer.py, .env, requirements.txt, local *.sql
  ged_transfer/             ← package (config, paths, db, pipeline)
```

## Runtime

- Entry: `python transfer.py`
- Config always from project `.env`
- Origin: `DOWNLOAD_DIR` (required)
- Destiny: `DEST_DIR` (required)
- `DB_LOOKUP`: `true` (default when omitted) runs `SQL_FILE` for every origin file. The returned value is the full destiny file name. `false` moves every origin file and keeps its name. No database connection in that mode.
- `SQL_FILE`: project-relative lookup statement, used only when `DB_LOOKUP` is true. `.sql` is optional. Subfolders are allowed (`query\sql` or `query\sql.sql`). Defaults to `ged_lookup.sql`. `*.sql` is gitignored — do not commit the query.
- `DOWNLOAD_DIR_USER` / `DOWNLOAD_DIR_PASSWORD` only when a directory is not already accessible
- `DEST_DIR_USER` / `DEST_DIR_PASSWORD` optional; fall back to `DOWNLOAD_DIR_*`
- DB credentials are required only when a lookup actually connects

## Transfer rules

For each file in the origin directory (not recursive):

When `DB_LOOKUP` is false:

1. Move the file to destiny under the same name.

When `DB_LOOKUP` is true:

1. Run the SQL in `SQL_FILE` for every file, binding `:file_name` to the current file name.
2. If it returns a non-empty name → that string is the destiny file name. Move the file there. Do not prefix it and do not special-case any file name in Python.
3. If the query returns nothing or null → leave the file in origin.

Naming policy (keep the original name, concatenate a prefix, skip a pattern) belongs in the local SQL file. Do not hardcode a caller's rename rule in the package.

## Language

- Project code, docs, agents: **English**.
