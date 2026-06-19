# Bomfast Info

Hugo-basert nettsted som publiserer alternativ innsikt om Hordfast og E39. Bygget med
[Hugo Extended](https://gohugo.io/) og temaet
[PaperMod](https://github.com/adityatelange/hugo-PaperMod).

## Oppsett

PaperMod er lagt inn som en Git-submodule. Klone repoet med:

```bash
git clone --recurse-submodules <repo-url>
```

Hvis du allerede har klonet uten `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

## Bygg lokalt

Krever Hugo Extended (se `netlify.toml` for versjon brukt i produksjon).

```bash
hugo server -D    # utviklingsserver på http://localhost:1313
hugo --gc --minify    # produksjonsbygg til public/
```

## Tilpasninger

Alle egne tilpasninger ligger utenfor temaet:

- `layouts/` — overstyringer av PaperMod-templates (header, cover, schema-JSON, m.m.)
- `layouts/shortcodes/` — egne shortcodes (`countup`, `figurecaption`, `mosaicgallery`,
  `rodlistebar`, `rawhtml`)
- `layouts/_markup/render-image.html` — bilderenderer med zoom-lenke og figcaption
- `assets/css/extended/` — egen CSS som legges til etter PaperMods kjerne-CSS
- `i18n/nb.yaml` — norske oversettelser
- `content/` — innholdet (innsikt, notiser, naturen, tall, om, mer-lesestoff)

Ikke modifiser filer inni `themes/PaperMod/` direkte — bruk overstyringer i `layouts/`.

## Oppdatere PaperMod

```bash
cd themes/PaperMod
git fetch
git checkout <ny-tag-eller-commit>
cd ../..
git add themes/PaperMod
git commit -m "Oppdater PaperMod til <versjon>"
```

## Deploy

Deployes til Netlify fra `main`-branchen. Konfig i `netlify.toml`.

## Slå på indeksering igjen for søkemotorer

```bash
rm layouts/_partials/extend_head.html layouts/robots.txt
```
