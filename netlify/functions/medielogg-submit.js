// Netlify Function: tar imot innsending fra skjemaet på content/mer-lesestoff/medielogg-nytt/
// og oppretter en ny commit direkte i GitHub-repoet via Contents API.
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
  frontMatterLines.push("---", "", comment, "");
  const fileContent = frontMatterLines.join("\n");

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return { statusCode: 500, body: "GITHUB_TOKEN er ikke satt" };
  }

  const apiUrl = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`;
  let response;
  try {
    response = await fetch(apiUrl, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "bomfastinfo-medielogg-function",
      },
      body: JSON.stringify({
        message: `Ny ${type === "rapporter" ? "rapport" : "medieoppføring"}: ${title}`,
        content: Buffer.from(fileContent, "utf-8").toString("base64"),
        branch: BRANCH,
      }),
    });
  } catch (err) {
    return { statusCode: 502, body: `Kunne ikke nå GitHub: ${err.message}` };
  }

  if (response.status === 422) {
    // PUT uten "sha" feiler slik når filen allerede finnes - typisk dato+tittel-kollisjon.
    return {
      statusCode: 409,
      body: "Det finnes allerede en oppføring med denne datoen og tittelen. Prøv en litt annen tittel, eller velg en annen dato.",
    };
  }

  if (!response.ok) {
    const errText = await response.text();
    return { statusCode: 502, body: `GitHub API-feil (${response.status}): ${errText}` };
  }

  return {
    statusCode: 200,
    body: JSON.stringify({ ok: true, path }),
    headers: { "Content-Type": "application/json" },
  };
};
