<!-- cspell:disable -->

# ppkilder.py: source documents from Paperpile

`scripts/ppkilder.py` keeps the website's list of source documents in step with
Paperpile. It does four things:

- **convert:** turns each PDF into a Markdown text file.
- **Private list:** keeps a private list of all the sources (`kilder.yaml`).
- **export:** writes the public list that the `kilde` shortcode links to.
- **archive / upload:** finds or creates archive copies.

This guide covers the everyday use. For every detail, run
`python3 scripts/ppkilder.py --help`.

## Where things live

| What | Where |
|---|---|
| The sources (PDFs, titles, URLs, labels) | Paperpile: the only place you edit them |
| PDFs + `bomfast-kilder.bib` | Paperpile's mirror on Google Drive, mounted at `~/GoogleDrive/Paperpile` |
| `kilder.yaml` + `tekst/*.md` per top folder | The **private** repo `~/work/git/bomfast-kilder` |
| Public list for the website | `data/kilder/<top folder>.yaml` in this repo |

The private repo can hold paywalled articles and documents obtained via innsyn. The
script refuses to write private files inside bomfastinfo.

## One-time setup

1. **Paperpile export:** go to profile picture → *Workflows and Integrations* →
   *BibTeX export*. Auto-export **only** the `bomfast-kilder` label to Google Drive.
   Move the resulting `bomfast-kilder.bib` into the Paperpile folder. It keeps
   syncing there.
2. **Mount the mirror.** The Paperpile folder is under *Shared with me*, so it needs
   its own mount:

   ```sh
   mkdir -p ~/GoogleDrive/Paperpile
   rclone mount gdrive:Paperpile ~/GoogleDrive/Paperpile --drive-shared-with-me \
       --read-only --vfs-cache-mode=full --dir-cache-time=1h --poll-interval=15s
   ```

3. **Clone the private repo** to `~/work/git/bomfast-kilder`.
4. **Install the dependencies:**

   ```sh
   pip install pymupdf pymupdf4llm pyyaml
   sudo apt install tesseract-ocr tesseract-ocr-nor     # only for scanned PDFs
   python3 -m pip install --user internetarchive && ia configure   # only for upload
   ```

To use other locations, set `--paperpile`, `--bib` and `--sources`, or the
environment variables `BOMFAST_PAPERPILE`, `BOMFAST_BIB` and `BOMFAST_SOURCES`.

## Adding a source in Paperpile

Give the paper these labels:

- `bomfast-kilder`: includes it in the export.
- **Exactly one top folder label**, for example `101_hordfast` or
  `001_nasjonal_transportplan_ntp`. It decides which `kilder.yaml` the source goes
  into. There are no subfolders.
- Any topic labels you like (`NTP`, `Rogfast`, ...). They end up in `emneord`.
- Control labels where needed, see below.

The **citekey** becomes the source's id, which you use in articles. Use the form
`<who>_<year>--<what>`: lowercase, words joined by `_`, the year right before `--`.
Example: `regjeringen_2017--ntp_2018_2029`. Set the URL in Paperpile too.

### Control labels

| Label | Effect |
|---|---|
| `_PRIVAT` | Only id and title in the public list, no link; never archived (`offentlig: nei`, `arkiv: skip`) |
| `_INNSYN` | Same as `_PRIVAT` (documents obtained via innsyn) |
| `_ABO` | Paywalled: in the public list with its URL, but never archived |
| `_NO_URL` | No URL on purpose. `check` stops reporting it |

Sources with `_PRIVAT`, `_INNSYN` or `_NO_URL` can still be cited in articles: the
`kilde` shortcode shows their title as plain text, without a link. **The title of a
private source is public**, so give it a title in Paperpile that is fine to publish.

**Removing a label does not undo its effect.** To make a source public again, edit
`offentlig` / `arkiv` in the private `kilder.yaml` by hand.

## Everyday workflow

```sh
python3 scripts/ppkilder.py convert -n     # what would change?
python3 scripts/ppkilder.py convert        # convert new/changed PDFs, update kilder.yaml
python3 scripts/ppkilder.py check          # everything in sync? (never writes)
python3 scripts/ppkilder.py export         # write data/kilder/*.yaml for the website
```

Then commit **both** repos:

- **bomfast-kilder:** `kilder.yaml`, `tekst/` and `paperpile.bib`.
- **bomfastinfo:** `data/kilder/`.

Without folder names, every command works on all top folders. Give folder names to
limit it, for example `convert 101_hordfast`. Add `-v` to see unchanged sources too.

### Removing a source

Remove the `bomfast-kilder` label (or the paper) in Paperpile. Removing only the top
folder label is not enough: the paper stays in the `.bib` export as an unusable entry
(`WARNING ... skipped`), and `prune` keeps it. Then run:

```sh
python3 scripts/ppkilder.py prune -n       # see what would go
python3 scripts/ppkilder.py prune          # remove the entry and its text file
python3 scripts/ppkilder.py export
```

### Archive links

```sh
python3 scripts/ppkilder.py archive                  # fill empty arkiv fields from Wayback
python3 scripts/ppkilder.py archive 101_hordfast --save   # also request new captures (slow)
python3 scripts/ppkilder.py upload <citekey>         # dry run: upload the PDF to archive.org?
python3 scripts/ppkilder.py upload <citekey> --upload
```

- **archive** never overwrites an `arkiv` value you wrote yourself.
- **upload** is for PDFs that have gone, or may go, from the publisher's site. It
  refuses private, `_ABO` and changed sources. Uploads are public and permanent.
  Afterwards, commit `uploads_webarchive/results.jsonl` too.

## Citing a source in an article

```text
{{< kilde "regjeringen_2017--ntp_2018_2029" >}}
{{< kilde id="regjeringen_2017--ntp_2018_2029" side="112" >}}
```

A source without a link (private, or without a URL) is shown as plain text. If the id
is unknown, the Hugo build stops. Run `export`, or check the citekey.

## What the messages mean

| Message | What to do |
|---|---|
| `Paperpile mirror not found ... Is it mounted?` | Start the rclone mount |
| `MISSING` | The PDF hasn't synced to the mirror yet. Try again later |
| `RENAMED` | You changed a citekey: **update references in articles** |
| `MOVED` | You changed the top folder label. The entry follows on the next `convert` |
| `GONE` | No longer in the `.bib` file. `prune` removes it |
| `METADATA` | Only fields in `kilder.yaml` changed (title, URL, labels, ...) |
| `NO LABEL` | `kilder.yaml` is private/skip, but the Paperpile label is gone. It stays private on purpose |
| `CITEKEY`, `NO URL`, `DUPLICATE` | Notices only. Fix them in Paperpile if you want |
| `WARNING ... skipped` | The Paperpile entry is unusable, for example two top folder labels or a citekey used twice |

## Tests

```sh
python3 -m pytest scripts
```

The tests never touch the real mirror or the private repo.
