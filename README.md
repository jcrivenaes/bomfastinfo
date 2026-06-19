# Bomfast Info

Kildekode for [bomfast.info](https://bomfast.info) — alternativ innsikt om Hordfast og
E39.

Bygget med [Hugo Extended](https://gohugo.io/) og temaet
[PaperMod](https://github.com/adityatelange/hugo-PaperMod).

## Komme i gang

Klon repoet (PaperMod er en submodule):

```bash
git clone --recurse-submodules <repo-url>
```

Allerede klonet uten flagget?

```bash
git submodule update --init --recursive
```

## Bygg

Krever Hugo Extended (versjonen som brukes i produksjon står i `netlify.toml`).

```bash
hugo server -D         # utviklingsserver: http://localhost:1313
hugo --gc --minify     # produksjonsbygg til public/
```

## Deploy

Push til `main` → automatisk deploy på Netlify.

## Mer

Detaljer om mappestruktur, shortcodes, oppdatering av PaperMod, statistikk og
prelaunch-modus: se [docs/utvikling.md](docs/utvikling.md).
