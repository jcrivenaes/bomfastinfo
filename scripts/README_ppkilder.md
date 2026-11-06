Mål: ppkilder.py skal slå opp kilder via Paperpile i stedet for egen kopi i Drive.

- Paperpile har ingen API. Bruk BibTeX-workflowen (Settings → Workflows)
  med auto-eksport av KUN bomfast-kilder etiketten til bomfast-kilder-repoet.
- .bib-filen har `file = "All Papers/X/..."` = sti i Drive-speilet
  (Paperpile-mappen). Flere filer skilles med ";", første er hoved-PDF.
- Citekey brukes som kilde-id (kilde-shortcoden).
- De konverte tekst filene skal bruke CiteKey som filnavn, for eks hvis citekey er "regjeringen_2025--statsbudsjett_samferdsel_2025_2026" skal skal filen hete regjeringen_2025--statsbudsjett_samferdsel_2025_2026.md
- Bruk først item i "keywords" som sti til destinasjon, for eksempel
  keywords = "bomfast/001\_nasjonal\_transportplan\_ntp/stortingsmeldinger;bomfast-kilder"
  --> 001_nasjonal_transportplan_ntp/stortingsmeldinger
- Paperpile repoet finnes på det mappede gdrive på den lokal maskinen
- Skript skrives på engelsk.
- bibtetx filen er på bomfast-kilder repoet, som paperpile/bib.tex
  