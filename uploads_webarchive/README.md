# uploads_webarchive/

Working folder for `scripts/archive_org_upload.py`.

- `config.json` (not committed) — your working list of upload jobs. Copy
  `config.example.json` to get started.
- `results.jsonl` (committed) — append-only log written by the script. One JSON object
  per line for each upload that was verified on archive.org, including the manifest
  metadata and file URL. Kept in git as an audit trail of what has been archived so far.

Run all jobs from the default config with:

```sh
python3 scripts/archive_org_upload.py --config --upload
```

Or point at a specific config file:

```sh
python3 scripts/archive_org_upload.py --config uploads_webarchive/my-batch.json --upload
```

CLI options (e.g. `--item`, `--upload`) act as defaults for any field a job in the
config does not set.

## Backfilling files uploaded before this script existed

For files already on archive.org that aren't in `results.jsonl` yet, don't delete and
re-upload them — that only churns archive.org's processing and risks breaking
already-published links. Instead, use `"backfill": true` jobs: these verify the file
already exists in the item, attach `original_url` as file-level metadata (via
`ia metadata --target=files/<name>`), and log an entry to the results file, without
downloading a source or re-running `ia upload`.

Copy `backfill.example.json` (already listing the files currently in
`bomfast-kildedokumenter`), fill in the `original_url` values you know, and run:

```sh
python3 scripts/archive_org_upload.py --config uploads_webarchive/backfill.example.json
```
