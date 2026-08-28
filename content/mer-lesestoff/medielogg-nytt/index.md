---
title: "Legg til medieoppføring"
robotsNoIndex: true
draft: false
hideMeta: true
weight: 50
_build:
  list: "never"
---

Internt skjema for å legge til en ny oppføring i
[medieloggen](/mer-lesestoff/medialogg/). Nås via det låste ikonet i menyen - kun for
redaksjonen (krever passord).

{{< rawhtml >}}

<div id="medielogg-gate">
  <p><button id="medielogg-unlock" type="button">Lås opp skjema</button></p>
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
    <input type="date" id="dato" required />
  </p>

  <p>
    <label for="kilde">Kilde (avis)</label>
    <input type="text" id="kilde" />
  </p>

  <p>
    <label for="url">Lenke til artikkel</label>
    <input type="url" id="url" />
  </p>

  <p>
    <label for="abo" class="medielogg-checkbox-label">
      <input type="checkbox" id="abo" /> Krever abonnement (bak betalingsmur)
    </label>
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

    var payload = {
      secret: document.getElementById("hemmelig").value,
      title: document.getElementById("tittel").value,
      date: document.getElementById("dato").value,
      source: document.getElementById("kilde").value,
      url: document.getElementById("url").value,
      abo: document.getElementById("abo").checked,
      comment: document.getElementById("kommentar").value,
      botField: document.getElementById("bot-field").value,
    };

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
      } else {
        var text = await res.text();
        status.textContent = "Feil: " + text;
      }
    } catch (err) {
      status.textContent = "Feil ved sending: " + err.message;
    }
  });

  document.getElementById("dato").valueAsDate = new Date();

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
    document.getElementById("medielogg-unlock").addEventListener("click", async function () {
      var input = prompt("Passord:");
      if (input === null) return;
      var hash = await medielogsSha256Hex(input);
      if (hash === MEDIELOGG_GATE_HASH) {
        sessionStorage.setItem("medielogg-unlocked", "1");
        medielogsShowContent();
      } else {
        alert("Feil passord");
      }
    });
  }
</script>

{{< /rawhtml >}}
