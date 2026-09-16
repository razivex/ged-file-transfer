# Agent / AI instructions — GED File Transfer

## Credentials and GitHub (mandatory)

1. **Never commit real credentials** — no passwords in source, commits, PRs, or issues.
2. **Single secrets file:** `ged-file-transfer/.env` (gitignored). Do not put real passwords in `.env.example`.
3. **Before every `git push` / PR:** confirm `.env` is not staged; search diffs for secrets.
4. **Never print secrets** in logs (directory passwords, DB password).
5. **Never read `.env`.** Grok is denied `Read`/`Edit` of `.env` and `.env.local` via `.grok/config.toml`. Use `.env.example` for the key list. Do not dump, cat, grep, or open `.env`.

## Layout

```text
ged-file-transfer/          ← transfer.py, .env, requirements.txt
  ged_transfer/             ← package (config, paths, db, pipeline)
```

## Runtime

- Entry: `python transfer.py`
- Config always from project `.env`
- Origin: `DOWNLOAD_DIR` (required)
- Destiny: `DEST_DIR` (required)
- `DOWNLOAD_DIR_USER` / `DOWNLOAD_DIR_PASSWORD` only when a directory is not already accessible
- `DEST_DIR_USER` / `DEST_DIR_PASSWORD` optional; fall back to `DOWNLOAD_DIR_*`

## Transfer rules

For each file in the origin directory (not recursive):

1. Name starts with `003` → move to destiny as-is.
2. Otherwise run the GED lookup. If it returns a non-empty name → rename to `{queried}_{original_filename}` and move to destiny.
3. If the query returns nothing or null → leave the file in origin.

## Language

- Project code, docs, agents: **English**.
