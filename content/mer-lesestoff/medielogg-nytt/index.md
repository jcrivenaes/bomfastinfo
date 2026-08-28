---
title: "Legg til oppføring"
robotsNoIndex: true
draft: false
hideMeta: true
weight: 50
_build:
  list: "never"
---

Internt skjema for å legge til en ny oppføring i
[medieloggen](/mer-lesestoff/medialogg/) eller
[rapportlisten](/mer-lesestoff/rapporter/). Nås via det låste ikonet i menyen - kun for
redaksjonen (krever passord).

{{< rawhtml >}}

<div id="medielogg-gate">
<form id="medielogg-gate-form" class="kontakt-form">
  <p>
    <label for="gate-passord">Passord for å låse opp skjema</label>
    <input type="password" id="gate-passord" name="password" autocomplete="current-password" required />
  </p>
  <button type="submit">Lås opp</button>
  <p id="medielogg-gate-status"></p>
</form>
</div>

<div id="medielogg-content" style="display:none">

<form id="medielogg-form" class="kontakt-form">
  <p class="hidden-honeypot">
    <label>Ikke fyll ut dette feltet: <input id="bot-field" /></label>
  </p>

  <p>
    <label for="hemmelig">Passord</label>
    <input type="password" id="hemmelig" required />
  </p>

  <p>
    <label for="tittel">Tittel</label>
    <input type="text" id="tittel" required />
  </p>

  <p>
    <label for="dato">Dato</label>
    <input type="date" id="dato" lang="nb-NO" required />
  </p>

  <p>
    <label>Type oppføring</label>
    <span class="medielogg-radio-group">
      <label class="medielogg-checkbox-label">
        <input type="radio" name="entrytype" id="type-medielogg" value="medielogg" checked /> Medielogg (nyhet)
      </label>
      <label class="medielogg-checkbox-label">
        <input type="radio" name="entrytype" id="type-rapporter" value="rapporter" /> Rapport
      </label>
    </span>
  </p>

  <div id="felter-medielogg">
    <p>
      <label for="kilde">Kilde (avis)</label>
      <input type="text" id="kilde" />
    </p>

    <p>
      <label for="abo" class="medielogg-checkbox-label">
        <input type="checkbox" id="abo" /> Krever abonnement (bak betalingsmur)
      </label>
    </p>

  </div>

  <div id="felter-rapporter" style="display:none">
    <p>
      <label for="institusjon">Institusjon</label>
      <input type="text" id="institusjon" />
    </p>

    <p>
      <label for="forfatter">Forfatter</label>
      <input type="text" id="forfatter" />
    </p>

  </div>

  <p>
    <label for="url">Lenke til artikkel/rapport</label>
    <input type="url" id="url" />
  </p>

  <p>
    <label for="kommentar">Kommentar</label>
    <textarea id="kommentar" rows="6" required></textarea>
  </p>

<button type="submit">Legg til</button>

  <p id="medielogg-status"></p>
</form>

</div>

<script>
  document.getElementById("medielogg-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var status = document.getElementById("medielogg-status");
    status.textContent = "Sender...";

    var entryType = document.querySelector('input[name="entrytype"]:checked').value;
    var payload = {
      secret: document.getElementById("hemmelig").value,
      type: entryType,
      title: document.getElementById("tittel").value,
      date: document.getElementById("dato").value,
      url: document.getElementById("url").value,
      comment: document.getElementById("kommentar").value,
      botField: document.getElementById("bot-field").value,
    };
    if (entryType === "rapporter") {
      payload.institusjon = document.getElementById("institusjon").value;
      payload.forfatter = document.getElementById("forfatter").value;
    } else {
      payload.source = document.getElementById("kilde").value;
      payload.abo = document.getElementById("abo").checked;
    }

    try {
      var res = await fetch("/.netlify/functions/medielogg-submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        status.textContent = "Lagt til! Nettsiden bygges på nytt om et par minutter.";
        document.getElementById("medielogg-form").reset();
        document.getElementById("dato").valueAsDate = new Date();
        updateEntryTypeFields();
      } else {
        var text = await res.text();
        status.textContent = "Feil: " + text;
      }
    } catch (err) {
      status.textContent = "Feil ved sending: " + err.message;
    }
  });

  document.getElementById("dato").valueAsDate = new Date();

  function updateEntryTypeFields() {
    var isRapport = document.getElementById("type-rapporter").checked;
    document.getElementById("felter-medielogg").style.display = isRapport ? "none" : "block";
    document.getElementById("felter-rapporter").style.display = isRapport ? "block" : "none";
  }

  document.querySelectorAll('input[name="entrytype"]').forEach(function (radio) {
    radio.addEventListener("change", updateEntryTypeFields);
  });
  updateEntryTypeFields();

  // Enkel visningssperre - KUN obfuskering, ikke ekte tilgangskontroll (koden er
  // synlig for alle som ser på sidekilden). Erstatt hashen på egen maskin med:
  //   printf '%s' 'dittPassord' | shasum -a 256
  var MEDIELOGG_GATE_HASH = "4ba89189d3ecca947a53efb9de0cfc95fdf1542728a279b0a28c18db2c5bf8af";

  function medielogsShowContent() {
    document.getElementById("medielogg-gate").style.display = "none";
    document.getElementById("medielogg-content").style.display = "block";
  }

  async function medielogsSha256Hex(text) {
    var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf))
      .map(function (b) {
        return b.toString(16).padStart(2, "0");
      })
      .join("");
  }

  if (sessionStorage.getItem("medielogg-unlocked") === "1") {
    medielogsShowContent();
  } else {
    document.getElementById("medielogg-gate-form").addEventListener("submit", async function (e) {
      e.preventDefault();
      var gateStatus = document.getElementById("medielogg-gate-status");
      var input = document.getElementById("gate-passord").value;
      var hash = await medielogsSha256Hex(input);
      if (hash === MEDIELOGG_GATE_HASH) {
        sessionStorage.setItem("medielogg-unlocked", "1");
        medielogsShowContent();
      } else {
        gateStatus.textContent = "Feil passord";
      }
    });
  }
</script>

{{< /rawhtml >}}
