# GED File Transfer

Moves files from an origin folder (`DOWNLOAD_DIR`) to a destiny folder (`DEST_DIR`).

`DB_LOOKUP` chooses what happens to each file:

- **`true`** — run your SQL file for every file. The value the query returns is the full destiny file name: the script renames the file to that value and moves it. A query that returns nothing leaves the file in the origin folder. This is the default when `DB_LOOKUP` is left unset.
- **`false`** — move every file and keep its current name. The database is not contacted.

The script does not contain a naming policy. Keeping a name, skipping a name, or building a new name (for example a prefix plus the original file name) is written in the SQL file, so each person can use the script for a different case.

Only files sitting directly in the origin folder are transferred. Subfolders are left alone. A move removes the file from origin. If the destiny folder already has that name, the script appends `_1`, `_2`, and so on, and does not overwrite.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with the origin and destiny paths. Oracle credentials are required only when a lookup actually runs. Set `DOWNLOAD_DIR_USER` / `DOWNLOAD_DIR_PASSWORD` only if a UNC path needs authentication.

The lookup statement lives in a `.sql` file inside this project. `*.sql` is gitignored, so the query stays on your machine and is not pushed. Create the file locally (for example `ged_lookup.sql` in the project folder) and paste your statement into it. A fresh clone does not include that file.

## Usage

```powershell
python transfer.py
```

### Settings

| Variable | Role |
|---|---|
| `DOWNLOAD_DIR` | Origin folder |
| `DEST_DIR` | Destiny folder |
| `DB_LOOKUP` | `true` or `false`. Omitted means `true` |
| `SQL_FILE` | Query file inside this project. Used only when lookup is on. Omitted means `ged_lookup.sql` |
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SERVICE` | Oracle connection. Used only when lookup is on and a file needs a query |

`SQL_FILE` is resolved from the project folder (the folder that contains `transfer.py`):

| Value you put in `.env` | File the script opens |
|---|---|
| `SQL` | `<project>\SQL.sql` |
| `SQL.sql` | `<project>\SQL.sql` |
| `query\sql` | `<project>\query\sql.sql` |
| `query\sql.sql` | `<project>\query\sql.sql` |
| `query/sql` | `<project>\query\sql.sql` |

The extension is optional. A subfolder of the project is allowed. An absolute path, or a path that climbs out with `..`, is rejected.

Plain move, no database:

```env
DB_LOOKUP=false
```

Lookup and rename (the query in `ged_lookup.sql` at the project root):

```env
DB_LOOKUP=true
SQL_FILE=ged_lookup.sql
```

Same lookup, with the statement stored in a subfolder. Either value opens `query\ged_lookup.sql`:

```env
DB_LOOKUP=true
SQL_FILE=query\ged_lookup
```

## How a run works

```text
                         python transfer.py
                                 |
                                 v
                          read project .env
                                 |
                                 v
                           DB_LOOKUP ?
                          /            \
                      false             true
                        |                 |
                        v                 v
               move every file     open SQL_FILE
               origin -------->    inside the project
               destiny                    |
               keep the name              v
                        |          each file in DOWNLOAD_DIR
                        |                 |
                        |                 v
                        |            run the SQL
                        |            :file_name = this file
                        |                 |
                        |                 v
                        |          query returned a name ?
                        |            /              \
                        |          yes               no
                        |           |                 |
                        |           v                 v
                        |    rename to {query}   ignore the file
                        |    and move            leave it in
                        |    to DEST_DIR         DOWNLOAD_DIR
                        v           v
                      print the summary
```

`{query}` is the text the SQL file returns. That text is the whole destiny file name. If the query returns `report_laudo.pdf`, the file is saved as `report_laudo.pdf`. The script does not append the original name on its own.

## How the DB lookup works

The lookup runs only when `DB_LOOKUP` is `true`.

1. The script checks that `SQL_FILE` exists before it moves anything.
2. It lists the files in `DOWNLOAD_DIR`.
3. It connects to Oracle once for the run.
4. For every file, it runs your SQL file. The current file name is passed as `:file_name`.
5. The first non-empty value in the first column is the destiny file name. The file is renamed to that value and moved to `DEST_DIR`.
6. No row, an empty value, or null leaves the file in `DOWNLOAD_DIR`.
7. The connection is closed at the end of the run.

Characters a Windows file name cannot contain (`\ / : * ? " < > |`) are replaced with `_` so the name can be saved. If `DEST_DIR` already has that name, `_1`, `_2`, and so on are appended. The file is not overwritten.

Your SQL file must be a single statement and must contain `:file_name`. A trailing semicolon is fine; the script removes one before sending the statement to Oracle. Several rows can come back; the first non-empty value is the one that is used.

Naming rules live in that file. Typical choices:

- Return `:file_name` when the file should keep its name.
- Return a built string, such as `prefix || '_' || :file_name`, when the file should be renamed.
- Return no row when the file should stay in the origin folder.

```sql
-- The selected column is the full destiny file name.
-- :file_name is the current origin file.
-- No row leaves the file in DOWNLOAD_DIR.

select case
         when :file_name like 'KEEP%' then :file_name
         else 'PREFIX_' || :file_name
       end
from dual;
```

That example is only a shape. Point `SQL_FILE` at your own statement: another table, another prefix, or no rename at all. The local `.sql` file is gitignored, so each machine keeps its own query.

## Behaviour

Lookup on (`DB_LOOKUP=true`):

| SQL result | Action |
|---|---|
| A name | Rename to that name, then move to `DEST_DIR` |
| No row, empty, or null | Leave the file in `DOWNLOAD_DIR` |

Lookup off (`DB_LOOKUP=false`):

| Origin file | Action |
|---|---|
| Any file | Move to `DEST_DIR` and keep the name |
