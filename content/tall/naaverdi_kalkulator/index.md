---
title: "Nåverdi kalkulator"

draft: false
hideAuthor: true
wide: true
---

Dette er en enkel kalkulator for å beregne nåverdi (typisk brukt i samferdsel), med en
rente for år 0-40 og en annen rente fra 40 til 75 år.

## Hvorfor to renter? Analyseperiode og kalkulasjonsrente

Rundskriv **R-109/2021** og DFØ-veilederen (bygget på NOU 2012:16, Hagen-utvalget)
fastsetter en **fallende, tidsavhengig kalkulasjonsrente** for statlige tiltak med
systematisk risiko på linje med et gjennomsnittlig statlig prosjekt:

| Periode  | Reell kalkulasjonsrente |
| -------- | ----------------------- |
| År 0–40  | **4 %**                 |
| År 40–75 | **3 %**                 |

Renten faller fordi risikopåslaget gjelder de første 40 årene, mens usikkerhet om
«riktig» langsiktig rente trekker den ned lenger fram i tid. Standard **analyseperiode
er 40 år**, men for tiltak med svært lang levetid – som store samferdselsinvesteringer
(veier, bruer, tunneler) – åpnes det for **opp mot 75 år**, eller 40 år + en beregnet
**restverdi**. Valget skal begrunnes og testes i sensitivitetsanalyse.

## Interaktiv kalkulator

{{< rawhtml >}}

<iframe
    src="https://jcrivenaes.github.io/bomfasttools/naaverdi_calc/index.html"
    title="Kalkulator for nåverdi"
    width="120%"
    height="1100"
    style="border: 0;"
    sandbox="allow-scripts allow-same-origin"
    referrerpolicy="no-referrer"
    loading="lazy"
></iframe>
{{< /rawhtml >}}

## Tilleggsinformasjon om samfunnsøkonomiske analyser

- [Samfunnsøkonomiske analyser, veileder](https://www.regjeringen.no/no/tema/okonomi-og-budsjett/statlig-okonomistyring/samfunnsokonomiske-analyser/id438830/)
- [DFØ veileder](https://www.dfo.no/nyhetsarkiv/ny-veileder-i-samfunnsokonomiske-analyser)
- [Statens prosjektmodell](https://www.regjeringen.no/globalassets/upload/fin/vedlegg/okstyring/rundskriv/faste/r-108_2025.pdf)

  Kort om innholdet:

- **Samfunnsøkonomiske analyser (Finansdepartementet)**: Overordnet side som forklarer
  hvorfor staten bruker samfunnsøkonomiske analyser, og som peker på rundskriv
  **R-109/2021** – prinsipper og krav ved utarbeidelse av slike analyser. Formålet er å
  sikre at nytte og kostnader ved statlige tiltak belyses systematisk, sammenlignbart og
  transparent, slik at beslutningsgrunnlaget blir så godt som mulig. Rundskrivet ble
  oppdatert i 2021 med regler for hvordan klimagassutslipp skal verdsettes.
- **DFØ-veilederen**: Den praktiske «kokeboken» for hvordan analysene faktisk skal
  gjennomføres. Beskriver metoden stegvis – problembeskrivelse og nullalternativ,
  identifisering av tiltak, vurdering av prissatte og ikke-prissatte virkninger,
  usikkerhet, og samlet vurdering. Retter seg mot utredere, bestillere og
  beslutningstakere, og gir eksempler og fallgruver.
- **Statens prosjektmodell (R-108/2025)**: Finansdepartementets rundskriv med krav til
  kvalitetssikring av store statlige investeringsprosjekter (over en gitt terskelverdi).
  Setter opp KS1 (kvalitetssikring av konseptvalg, før regjeringen velger konsept) og
  KS2 (kvalitetssikring av kostnad og styring før Stortinget vedtar investeringen).
  Samfunnsøkonomisk analyse etter R-109/2021 og DFØ-veilederen er en sentral del av
  grunnlaget for KS1.

I sum: **R-109/2021** setter reglene, **DFØ-veilederen** viser hvordan de brukes i
praksis, og **R-108/2025** krever at store prosjekter kvalitetssikres eksternt med
utgangspunkt i disse analysene.

## Krav til ikke-prissatte virkninger

Både R-109/2021 og DFØ-veilederen er tydelige på at virkninger som ikke lar seg
tallfeste i kroner, **ikke kan utelates** fra analysen:

- Analysen skal omfatte **alle vesentlige nytte- og kostnadsvirkninger** – både
  prissatte og ikke-prissatte – vurdert mot nullalternativet.
- Ikke-prissatte virkninger skal **beskrives, vurderes og presenteres systematisk**, og
  ikke bare listes opp som tilleggsinformasjon.
- DFØ-veilederen foreskriver **pluss/minus-metoden**: hver virkning vurderes ut fra
  - **omfang** (lite / middels / stort, positivt eller negativt), og
  - **betydning/verdi** for samfunnet (liten / middels / stor),

  som kombineres til en skala fra `----` til `++++` (eller `0` for ubetydelig).

- Metode, datagrunnlag og **usikkerhet** skal dokumenteres, og det skal komme fram hvem
  som berøres (fordelingsvirkninger).
- I den **samlede vurderingen** skal det eksplisitt drøftes om de ikke-prissatte
  virkningene er store nok til å **endre rangeringen** som følger av netto nåverdi.

For samferdselsprosjekter er dette operasjonalisert i Statens vegvesens håndbok **V712
Konsekvensanalyser**, som bygger på de samme prinsippene. Det betyr at virkninger på
**natur, landskap, kulturmiljø, friluftsliv og lokalsamfunn** skal inn i analysen på en
strukturert måte – og kan i prinsippet veie tungt nok til å snu konklusjonen fra netto
nåverdi.
