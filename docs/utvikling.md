# Utvikling

Interne notater for vedlikehold av Bomfast Info-nettstedet.

## Mappestruktur

| Sti                                       | Innhold                                                                                |
| ----------------------------------------- | -------------------------------------------------------------------------------------- |
| `content/`                                | Innholdet (innsikt, notiser, naturen, tall, om, mer-lesestoff, kontakt)                |
| `layouts/`                                | Overstyringer av PaperMod-templates (header, cover, schema-JSON, m.m.)                 |
| `layouts/shortcodes/`                     | Egne shortcodes: `countup`, `figurecaption`, `mosaicgallery`, `rodlistebar`, `rawhtml` |
| `layouts/_markup/render-image.html`       | Render hook for markdown-bilder med zoom-lenke og figcaption                           |
| `layouts/_partials/extend_head.html`      | Egen `<head>`-tillegg — pt. GoatCounter-snippet                                        |
| `layouts/_partials/publication_note.html` | Boks med forfatter, publiseringsdato og lastmodNotes                                   |
| `layouts/_partials/post_summary.html`     | Ekspanderbar "Oppsummering"-boks, styrt av `oppsummering` i front matter (kun Innsikt) |
| `layouts/innsikt/single.html`             | Overstyrer PaperMod sin single.html for å plassere oppsummeringsboksen nær toppen      |
| `layouts/kontakt/list.html`               | Kontaktskjema (Netlify Forms)                                                          |
| `assets/css/extended/`                    | Egen CSS som lastes etter PaperMods kjerne-CSS                                         |
| `i18n/nb.yaml`                            | Norske oversettelser                                                                   |
| `static/`                                 | Filer som kopieres som de er (favicon, eventuelle `_redirects`)                        |
| `themes/PaperMod/`                        | Tema (Git-submodule — ikke modifiser direkte)                                          |

## Oppdatere PaperMod

```bash
cd themes/PaperMod
git fetch
git checkout <ny-tag-eller-commit>
cd ../..
git add themes/PaperMod
git commit -m "Oppdater PaperMod til <versjon>"
```

Test alltid lokalt etter oppdatering (`hugo server -D`) — overstyringer i `layouts/` kan
drive ut av synk med temaets endringer.

## Shortcodes

- `figurecaption` — bilde med rik caption (markdown-syntaks, lenker, formatering).
  Foretrukket alternativ: vanlig markdown-bilde, siden `render-image.html` allerede
  støtter markdown i caption via `title`-attributtet:
  ```markdown
  ![Alt-tekst](bilde.jpg "Caption med [lenke](https://...).")
  ```
- `countup` — animert tellerverdi.
- `mosaicgallery` — bildemosaikk.
- `rodlistebar` — visualisering av rødlistekategori.
- `rawhtml` — innlimt HTML når markdown ikke strekker til.

## Deploy

- Pushes til `main` deployes automatisk av Netlify.
- Konfig i `netlify.toml` (Hugo-versjon, build-kommando, tidssone).
- Forhåndsvisninger genereres for deploy previews og branch deploys.

## Kontaktskjema

Skjemaet i [layouts/kontakt/list.html](../layouts/kontakt/list.html) bruker Netlify
Forms (`data-netlify="true"`). Krever:

- Hidden input `form-name` med samme verdi som `<form name="...">`
- Honeypot-felt `bot-field`
- Egen takk-side definert i `content/kontakt/takk.md` (referert via
  `action="/kontakt/takk/"`)

Innkommende meldinger vises i Netlify-dashbordet under _Forms_.

## Besøksstatistikk (GoatCounter)

Snippet ligger i
[layouts/\_partials/extend_head.html](../layouts/_partials/extend_head.html). Dashboard:
https://bomfastinfo.goatcounter.com.

Cookieless og GDPR-trygt — ingen cookie-banner nødvendig.

For å ekskludere egne besøk per nettleser: åpne DevTools console på siden og kjør
`localStorage.setItem('skipgc', 't')`, eller bruk lenken under _Settings → Ignore
visits_ i GoatCounter.

`{{ if not hugo.IsServer }}`-guarden i snippeten sørger for at lokal `hugo server` ikke
teller med.

## SEO og indeksering

- `enableRobotsTXT = true` i `hugo.toml` gir Hugo-generert `robots.txt` som tillater
  alle crawlere.
- `baseURL = "https://bomfast.info/"` brukes i sitemap.xml, RSS og JSON-LD.
- Gamle Wix-URL-er (`/post/...`) håndteres via `aliases:` i frontmatter (meta-refresh
  redirect, behandles som 301 av Google).

## Prelaunch-modus (hvis nødvendig senere)

For å midlertidig blokkere søkemotorer:

1. Opprett `layouts/robots.txt` med:
   ```
   User-agent: *
   Disallow: /
   ```
2. Legg til i `layouts/_partials/extend_head.html`:
   ```html
   <meta name="robots" content="noindex, nofollow" />
   ```

Husk å fjerne begge før go-live igjen.
