# GED File Transfer

Moves files from an origin folder (`DOWNLOAD_DIR`) to a destiny folder (`DEST_DIR`).

`DB_LOOKUP` chooses what happens to each file:

- **`true`** — look the file up in Oracle with the SQL file you choose, rename it from the query result, then move it. Names that already start with `003` are moved as they are. This is the default when `DB_LOOKUP` is left unset.
- **`false`** — move every file and keep its current name. The database is not contacted.

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
               destiny             bind name: :file_name
               keep the name              |
                        |                 v
                        |          each file in DOWNLOAD_DIR
                        |                 |
                        |                 v
                        |          name starts with 003 ?
                        |            /              \
                        |          yes               no
                        |           |                 |
                        |           v                 v
                        |      move as-is        run the SQL file
                        |      to DEST_DIR       :file_name = this file
                        |           |                 |
                        |           |                 v
                        |           |          query returned a name ?
                        |           |            /              \
                        |           |          yes               no
                        |           |           |                 |
                        |           |           v                 v
                        |           |    rename to           leave the file
                        |           |    {query}_{file}      in DOWNLOAD_DIR
                        |           |    and move
                        |           |    to DEST_DIR
                        v           v
                      print the summary
```

`{query}` is the text returned by the SQL file. `{file}` is the original file name, extension included. Example: origin `laudo.pdf` with query result `003-12345-67890` becomes `003-12345-67890_laudo.pdf`.

## How the DB lookup works

The lookup runs only when `DB_LOOKUP` is `true`.

1. The script checks that `SQL_FILE` exists before it moves anything.
2. It lists the files in `DOWNLOAD_DIR`.
3. A file whose name starts with `003` is already in the final form. It is moved to `DEST_DIR` and the database is not asked about it.
4. For every other file, the script connects to Oracle (once per run, on the first file that needs it) and runs your SQL file.
5. The current file name is passed as the bind variable `:file_name`.
6. The first non-empty value in the first column becomes the prefix.
7. The destiny name is `{prefix}_{original file name}`. If the prefix already ends with the same extension as the file, that extra extension is removed from the prefix so it is not repeated.
8. An empty result, or a null, leaves the file in `DOWNLOAD_DIR`.
9. The connection is closed at the end of the run.

Your SQL file must be a single statement and must contain `:file_name`. A trailing semicolon is fine; the script removes one before sending the statement to Oracle. The statement below is the one in the local `ged_lookup.sql`:

```sql
select '003-'|| nvl(nr_atendimento,tasy.obter_ultimo_atendimento(cd_pessoa_fisica)) ||'-' || cd_pessoa_fisica
from tasy.ged_atendimento
where cd_pessoa_fisica is not null
and regexp_substr(ds_arquivo,'/([^/]+)\?',1,1,null,1) = :file_name;
```

That reads `tasy.ged_atendimento`, keeps rows that have a person id, and matches the file name stored in `ds_arquivo`. The selected text is `003-{attendance}-{person}`. `nvl` fills the attendance number from `tasy.obter_ultimo_atendimento` when `nr_atendimento` is null.

Changing the query means editing the local `.sql` file (or pointing `SQL_FILE` at another file in the project). The Python code does not contain a second copy of the statement.

## Behaviour

Lookup on (`DB_LOOKUP=true`):

| Origin file | Action |
|---|---|
| Name starts with `003` | Move to `DEST_DIR` |
| Anything else, query returns a name | Rename to `{query}_{original file name}`, then move to `DEST_DIR` |
| Anything else, query empty or null | Leave the file in `DOWNLOAD_DIR` |

Lookup off (`DB_LOOKUP=false`):

| Origin file | Action |
|---|---|
| Any file | Move to `DEST_DIR` and keep the name |
