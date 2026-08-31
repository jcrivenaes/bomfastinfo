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
      "Content-Type": "application/json",
      "User-Agent": "bomfastinfo-medielogg-function",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function yamlString(value) {
  return JSON.stringify(value);
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  let data;
  try {
    data = JSON.parse(event.body || "{}");
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
  const title = (data.title || "").trim();
  const date = (data.date || "").trim();
  const source = (data.source || "").trim();
  const institusjon = (data.institusjon || "").trim();
  const forfatter = (data.forfatter || "").trim();
  const url = (data.url || "").trim();
  const abo = Boolean(data.abo);
  const comment = (data.comment || "").trim();

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
  const figureAlt = (data.figureAlt || "").trim();
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
  if (figureFileName) {
    frontMatterLines.push(`![${figureAlt}](${figureFileName})`, "");
  }
  frontMatterLines.push(comment, "");
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
    headers: { "Content-Type": "application/json" },
  };
};
