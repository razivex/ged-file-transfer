# GED File Transfer

Moves GED files from an origin folder to a destiny folder. Files whose name already starts with `003` are moved as-is. Other files are looked up in Tasy (`tasy.ged_atendimento`); when a new name is returned they are renamed and then moved. Files with no match stay in origin.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with origin/destiny paths and Oracle credentials. Set `DOWNLOAD_DIR_USER` / `DOWNLOAD_DIR_PASSWORD` only if a UNC path needs authentication.

## Usage

```powershell
python transfer.py
```

## Behaviour

| Origin file | Action |
|---|---|
| Name starts with `003` | Move to `DEST_DIR` |
| Anything else, query returns a name | Rename to `{query}_{original_filename}`, then move to `DEST_DIR` |
| Anything else, query empty/null | Ignore (leave in `DOWNLOAD_DIR`) |

Example: origin `laudo.pdf` with query `003-12345-67890` becomes `003-12345-67890_laudo.pdf`.

The lookup binds the current file name as `:file_name`:

```sql
select '003-'|| nvl(nr_atendimento,tasy.obter_ultimo_atendimento(cd_pessoa_fisica)) ||'-' || cd_pessoa_fisica
from tasy.ged_atendimento
where cd_pessoa_fisica is not null
and regexp_substr(ds_arquivo,'/([^/]+)\?',1,1,null,1) = :file_name;
```
