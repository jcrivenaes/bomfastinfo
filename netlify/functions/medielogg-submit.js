// Netlify Function: tar imot innsending fra skjemaet på content/mer-lesestoff/medielogg-nytt/
// og oppretter en ny commit direkte i GitHub-repoet via Git Data API (blob/tre/commit),
// i én atomisk commit som inkluderer både index.md og evt. figur. Git Data API brukes i
// stedet for Contents API fordi Contents API har en lav, udokumentert grense per fil
// (rundt 1 MB) som ellers ville gjort figuropplasting upålitelig.
const OWNER = "jcrivenaes";
const REPO = "bomfastinfo";
const BRANCH = "main";

function slugify(str) {
  return str
    .toLowerCase()
    .replace(/æ/g, "ae")
    .replace(/ø/g, "o")
    .replace(/å/g, "aa")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

// Grensen her er ikke satt av GitHub (Git Data API tar blobs opp til 100 MB), men av
// Netlify sin egen synkrone funksjonsgrense for request-payload (ca 6 MB rått), som må
// romme JSON-en pluss base64 (~33 % større enn originalfilen).
const MAKS_FIGUR_BYTES = 4 * 1024 * 1024;
const FIGUR_EKSTENSJON_PER_MIME = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/avif": "avif",
  "image/svg+xml": "svg",
};

function figurFilnavn(originalName, mime) {
  var ekstensjon = FIGUR_EKSTENSJON_PER_MIME[mime];
  if (!ekstensjon) return null;
  var base = slugify((originalName || "figur").replace(/\.[^.]+$/, "")) || "figur";
  return `${base}.${ekstensjon}`;
}

async function githubRequest(token, method, path, body) {
  return fetch(`https://api.github.com/repos/${OWNER}/${REPO}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json; charset=utf-8",
      "User-Agent": "bomfastinfo-medielogg-function",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function yamlString(value) {
  return JSON.stringify(value);
}

const MD_LISTEPUNKT = /^\s*([-*+]|\d+[.)])\s+/;
const MD_STRUKTUR = /^\s*(\||#{1,6}\s|>|[-*_=]{3,}\s*$)/;

// Kodegjerder: åpner med minst tre ` eller ~ (evt. med infostreng), og lukkes først av en
// linje med samme tegn, minst like mange, og ingenting annet enn mellomrom etter. Linjer
// som ligner på gjerder inne i en kodeblokk (annet tegn, kortere, eller med infostreng)
// er vanlig kode. Returnerer ny gjerdetilstand (null = utenfor kodeblokk).
function oppdaterGjerde(linje, gjerde) {
  if (gjerde) {
    const lukk = linje.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
    return lukk && lukk[1][0] === gjerde.tegn && lukk[1].length >= gjerde.lengde ? null : gjerde;
  }
  const aapne = linje.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
  if (!aapne || (aapne[1][0] === "`" && aapne[2].includes("`"))) return gjerde;
  return { tegn: aapne[1][0], lengde: aapne[1].length };
}

// Skilletegnlinje i en tabell, med eller uten ytre rør (f.eks. "--- | ---" eller "|:-:|--:|").
const MD_TABELLSKILLE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

// Finner linjer som er del av en tabell: skilletegnlinjen, overskriftslinjen over den og
// radene under (til første tomlinje). Rør rundt tabellen er valgfrie i Markdown, så
// tabellrader kan ikke gjenkjennes på ledende rør alene.
function finnTabellinjer(linjer) {
  const tabell = new Set();
  let gjerde = null;
  for (let i = 0; i < linjer.length; i++) {
    const forrigeGjerde = gjerde;
    gjerde = oppdaterGjerde(linjer[i], gjerde);
    if (forrigeGjerde || gjerde) continue;
    if (!linjer[i].includes("|") || !MD_TABELLSKILLE.test(linjer[i])) continue;
    if (i === 0 || !linjer[i - 1].includes("|") || tabell.has(i - 1)) continue;
    tabell.add(i - 1);
    let j = i;
    while (j < linjer.length && linjer[j].trim() && oppdaterGjerde(linjer[j], null) === null) {
      tabell.add(j++);
    }
    i = j - 1;
  }
  return tabell;
}

// Tekst limt inn fra PDF-er har ofte harde linjeskift midt i avsnitt (fra PDF-ens
// tekstoppsett) og orddeling med bindestrek ved linjeslutt. Dette slår sammen slike
// linjer til løpende avsnitt, slik man ville fått ved å skrive/lime inn manuelt uten
// harde linjeskift, mens tomlinjer (avsnittsskift) bevares. Markdown-struktur (listepunkter,
// tabellrader, overskrifter, sitater og kodeblokker) beholdes linje for linje, ellers
// havner f.eks. alle listepunkter og tabellrader på én linje og rendres feil.
function reflowInnlimtTekst(text) {
  const linjer = (text || "").replace(/\r\n?/g, "\n").split("\n");
  const tabellinjer = finnTabellinjer(linjer);
  const ut = [];
  let gjerde = null;
  // Forrige linje i ut er vanlig løpende tekst (eller et listepunkt) som en vanlig
  // fortsettelseslinje kan slås sammen med.
  let kanSlaaSammen = false;
  // Innrykket kodeblokk (4+ mellomrom/tab) kan ikke avbryte et avsnitt, og innrykk etter
  // en tomlinje i en liste er listefortsettelse, ikke kode.
  let forrigeTom = true;
  let iInnrykketKode = false;
  let iListe = false;
  const komprimer = (t) => t.replace(/(\S)[ \t]{2,}/g, "$1 ");

  for (let i = 0; i < linjer.length; i++) {
    const rå = linjer[i];
    const forrigeGjerde = gjerde;
    gjerde = oppdaterGjerde(rå, gjerde);
    if (forrigeGjerde || gjerde) {
      // Gjerdelinjer og kodelinjer beholdes ordrett, inkludert innrykk.
      ut.push(forrigeGjerde ? rå : rå.replace(/\s+$/, ""));
      kanSlaaSammen = false;
      forrigeTom = false;
      iInnrykketKode = false;
      continue;
    }
    const linje = rå.trim();
    if (!linje) {
      // Tomlinjer inne i innrykket kode beholdes; ellers slås flere tomlinjer sammen til én.
      if (iInnrykketKode || ut[ut.length - 1] !== "") ut.push("");
      kanSlaaSammen = false;
      forrigeTom = true;
      continue;
    }
    const innrykk = /^( {4}|\t)/.test(rå);
    if (innrykk && !iListe && (forrigeTom || iInnrykketKode)) {
      ut.push(rå.replace(/\s+$/, ""));
      iInnrykketKode = true;
      kanSlaaSammen = false;
      forrigeTom = false;
      continue;
    }
    if (innrykk && iListe && forrigeTom) {
      ut.push(komprimer(rå.replace(/\s+$/, "")));
      kanSlaaSammen = true;
      forrigeTom = false;
      continue;
    }
    iInnrykketKode = false;
    const erListepunkt = MD_LISTEPUNKT.test(rå);
    if (erListepunkt) iListe = true;
    else if (forrigeTom && !innrykk) iListe = false;
    forrigeTom = false;
    const erStruktur = erListepunkt || MD_STRUKTUR.test(rå) || tabellinjer.has(i);
    if (!erStruktur && kanSlaaSammen) {
      const forrige = ut.length - 1;
      ut[forrige] = /[a-zA-ZæøåÆØÅ]-$/.test(ut[forrige]) && /^[a-zA-ZæøåÆØÅ]/.test(linje)
        ? ut[forrige].slice(0, -1) + komprimer(linje)
        : `${ut[forrige]} ${komprimer(linje)}`;
    } else {
      ut.push(erListepunkt ? komprimer(rå.replace(/\s+$/, "")) : komprimer(linje));
      kanSlaaSammen = erListepunkt || !erStruktur;
    }
  }

  // Fjern bare ledende tomlinjer og avsluttende blanke tegn, så innrykk på første linje består.
  return ut
    .join("\n")
    .replace(/^(\s*\n)+/, "")
    .replace(/\s+$/, "");
}

// Nordiske tegn kan komme dekomponert (f.eks. "a" + kombinerende ring i stedet for å)
// fra enkelte tastatur/nettlesere, spesielt paste fra iOS/macOS eller PDF-er. Normaliser
// til NFC (sammensatt form) før teksten lagres, slik det blir konsistent med manuelt
// skrevet tekst.
function normaliserTekst(value) {
  return (value || "").normalize("NFC");
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  let rawBody = event.body || "{}";
  if (event.isBase64Encoded) {
    // Netlify/Lambda kan base64-kode requesten avhengig av proxy-oppsett; uten dette
    // ville JSON.parse feile eller (verre) tolke UTF-8-bytes for nordiske tegn feil.
    rawBody = Buffer.from(rawBody, "base64").toString("utf-8");
  }

  let data;
  try {
    data = JSON.parse(rawBody);
  } catch {
    return { statusCode: 400, body: "Ugyldig JSON" };
  }

  // Enkel honeypot - skal alltid være tom for ekte innsendinger.
  if (data.botField) {
    return { statusCode: 200, body: "OK" };
  }

  if (!process.env.MEDIELOGG_SHARED_SECRET || data.secret !== process.env.MEDIELOGG_SHARED_SECRET) {
    return { statusCode: 401, body: "Feil passord" };
  }

  const type = data.type === "rapporter" ? "rapporter" : "medielogg";
  const title = normaliserTekst((data.title || "").trim());
  const date = (data.date || "").trim();
  const source = normaliserTekst((data.source || "").trim());
  const institusjon = normaliserTekst((data.institusjon || "").trim());
  const forfatter = normaliserTekst((data.forfatter || "").trim());
  const url = (data.url || "").trim();
  const abo = Boolean(data.abo);
  const comment = normaliserTekst((data.comment || "").replace(/^(\s*\n)+/, "").trimEnd());

  if (!title || !date || !comment) {
    return { statusCode: 400, body: "Tittel, dato og kommentar er påkrevd" };
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(new Date(`${date}T00:00:00Z`).getTime())) {
    return { statusCode: 400, body: "Dato må være en gyldig dato på formatet YYYY-MM-DD" };
  }
  if (url && !/^https?:\/\//i.test(url)) {
    return { statusCode: 400, body: "Lenke må starte med http:// eller https://" };
  }

  const figureName = (data.figureName || "").trim();
  const figureMime = (data.figureMime || "").trim();
  const figureAlt = normaliserTekst((data.figureAlt || "").trim());
  const figureData = (data.figureData || "").trim();
  let figureFileName = null;
  if (figureData) {
    figureFileName = figurFilnavn(figureName, figureMime);
    if (!figureFileName) {
      return { statusCode: 400, body: "Figuren må være PNG, JPEG, GIF, WebP, AVIF eller SVG" };
    }
    // Base64 blåser opp størrelsen med ca 33 %, så sjekk mot det innsendte tallet av bytes.
    if (Buffer.byteLength(figureData, "base64") > MAKS_FIGUR_BYTES) {
      return { statusCode: 400, body: "Figuren er for stor (maks 4 MB)" };
    }
  }

  const slug = slugify(title) || "oppforing";
  const contentType = type === "rapporter" ? "rapporter" : "medialogg";
  const path = `content/mer-lesestoff/${contentType}/${date}-${slug}/index.md`;

  const frontMatterLines = ["---", `title: ${yamlString(title)}`, `date: ${date}`, `type: "${contentType}"`];
  if (type === "rapporter") {
    if (institusjon) frontMatterLines.push(`institusjon: ${yamlString(institusjon)}`);
    if (forfatter) frontMatterLines.push(`forfatter: ${yamlString(forfatter)}`);
  } else {
    if (source) frontMatterLines.push(`source: ${yamlString(source)}`);
    if (abo) frontMatterLines.push("abo: true");
  }
  if (url) frontMatterLines.push(`external_url: ${yamlString(url)}`);
  frontMatterLines.push("---", "");
  frontMatterLines.push(reflowInnlimtTekst(comment));
  if (figureFileName) {
    frontMatterLines.push("", `![${figureAlt}](${figureFileName})`);
  }
  frontMatterLines.push("");
  const fileContent = frontMatterLines.join("\n");

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return { statusCode: 500, body: "GITHUB_TOKEN er ikke satt" };
  }

  const figurePath = figureFileName ? `content/mer-lesestoff/${contentType}/${date}-${slug}/${figureFileName}` : null;

  try {
    // Git Data API overskriver en eksisterende fil i treet uten varsel, så kollisjon
    // (dato+tittel allerede i bruk) må sjekkes eksplisitt først.
    const eksisterendeRes = await githubRequest(token, "GET", `/contents/${path}?ref=${BRANCH}`);
    if (eksisterendeRes.status === 200) {
      return {
        statusCode: 409,
        body: "Det finnes allerede en oppføring med denne datoen og tittelen. Prøv en litt annen tittel, eller velg en annen dato.",
      };
    }
    if (eksisterendeRes.status !== 404) {
      return { statusCode: 502, body: `GitHub API-feil (${eksisterendeRes.status}) ved sjekk av eksisterende fil` };
    }

    const refRes = await githubRequest(token, "GET", `/git/ref/heads/${BRANCH}`);
    if (!refRes.ok) {
      return { statusCode: 502, body: `GitHub API-feil (${refRes.status}) ved henting av branch-referanse` };
    }
    const latestCommitSha = (await refRes.json()).object.sha;

    const commitRes = await githubRequest(token, "GET", `/git/commits/${latestCommitSha}`);
    if (!commitRes.ok) {
      return { statusCode: 502, body: `GitHub API-feil (${commitRes.status}) ved henting av siste commit` };
    }
    const baseTreeSha = (await commitRes.json()).tree.sha;

    const mdBlobRes = await githubRequest(token, "POST", "/git/blobs", {
      content: Buffer.from(fileContent, "utf-8").toString("base64"),
      encoding: "base64",
    });
    if (!mdBlobRes.ok) {
      return { statusCode: 502, body: `GitHub API-feil (${mdBlobRes.status}) ved opprettelse av tekst-blob` };
    }
    const mdBlobSha = (await mdBlobRes.json()).sha;

    const treeEntries = [{ path, mode: "100644", type: "blob", sha: mdBlobSha }];
    if (figurePath) {
      const figureBlobRes = await githubRequest(token, "POST", "/git/blobs", {
        content: figureData,
        encoding: "base64",
      });
      if (!figureBlobRes.ok) {
        return { statusCode: 502, body: `GitHub API-feil (${figureBlobRes.status}) ved opprettelse av figur-blob` };
      }
      treeEntries.push({ path: figurePath, mode: "100644", type: "blob", sha: (await figureBlobRes.json()).sha });
    }

    const treeRes = await githubRequest(token, "POST", "/git/trees", { base_tree: baseTreeSha, tree: treeEntries });
    if (!treeRes.ok) {
      return { statusCode: 502, body: `GitHub API-feil (${treeRes.status}) ved opprettelse av tre` };
    }
    const newTreeSha = (await treeRes.json()).sha;

    const commitMelding = `Ny ${type === "rapporter" ? "rapport" : "medieoppføring"}${figurePath ? " (med figur)" : ""}: ${title}`;
    const newCommitRes = await githubRequest(token, "POST", "/git/commits", {
      message: commitMelding,
      tree: newTreeSha,
      parents: [latestCommitSha],
    });
    if (!newCommitRes.ok) {
      return { statusCode: 502, body: `GitHub API-feil (${newCommitRes.status}) ved opprettelse av commit` };
    }
    const newCommitSha = (await newCommitRes.json()).sha;

    const updateRefRes = await githubRequest(token, "PATCH", `/git/refs/heads/${BRANCH}`, { sha: newCommitSha });
    if (!updateRefRes.ok) {
      const errText = await updateRefRes.text();
      return {
        statusCode: 409,
        body: `Kunne ikke oppdatere branch (noen andre endret trolig repoet samtidig, prøv igjen): ${errText}`,
      };
    }
  } catch (err) {
    return { statusCode: 502, body: `Kunne ikke nå GitHub: ${err.message}` };
  }

  return {
    statusCode: 200,
    body: JSON.stringify({ ok: true, path }),
    headers: { "Content-Type": "application/json; charset=utf-8" },
  };
};
