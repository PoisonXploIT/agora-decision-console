/* AGORA UI - single page sin build. Habla con el servicio (por defecto :8800). */
"use strict";

const API = window.AGORA_API || "";

const $ = (id) => document.getElementById(id);

async function jsonFetch(url, opts) {
  const r = await fetch(API + url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

async function cargarBackends() {
  const body = await jsonFetch("/backends");
  $("backend").innerHTML = body.backends
    .map((b) => `<option value="${esc(b.name)}">${esc(b.name)} (${esc(b.privacy)})</option>`)
    .join("");
}

async function cargarPacks() {
  const parte = $("parte").value;
  const body = await jsonFetch("/v1/packs");
  const packs = body.packs.filter((p) => p.part === parte);
  $("pack").innerHTML = packs
    .map((p) => `<option value="${esc(p.name)}">${esc(p.title || p.name)}</option>`)
    .join("");
  if (packs.length) renderPreguntas(packByName(packs));
}

function packByName(packs) {
  const sel = $("pack").value;
  return packs.find((p) => p.name === sel) || packs[0];
}

function renderPreguntas(pack) {
  const cont = $("preguntas");
  cont.innerHTML = (pack.questions || [])
    .map(
      (q) => `
    <div class="pregunta" data-id="${esc(q.id)}">
      <h3>${esc(q.prompt)}</h3>
      <p class="tipo">${esc(q.type)} - criterios: ${q.criteria.map(esc).join(", ")}</p>
    </div>`
    )
    .join("");
}

function tarjetaDistribucion(decision) {
  const probs = decision.probabilities;
  const filas = Object.entries(probs)
    .map(([k, v]) => {
      const pct = Math.round(v * 100);
      return `
      <div class="fila-prob">
        <span class="nombre">${esc(k)}</span>
        <span class="barra"><span style="width:${pct}%"></span></span>
        <span class="valor">${v.toFixed(3)}</span>
      </div>`;
    })
    .join("");
  const extra = [];
  if (decision.expected != null) extra.push(`esperado: ${decision.expected}`);
  if (decision.action != null) extra.push(`accion: ${esc(decision.action)}`);
  return `
  <div class="tarjeta" data-q="${esc(decision.question_id)}">
    <h3>${esc(decision.question_id)}</h3>
    ${filas}
    ${extra.length ? `<p class="extra">${extra.join(" - ")}</p>` : ""}
  </div>`;
}

async function decidir() {
  const parte = $("parte").value;
  let body;
  try {
    body = JSON.parse($("estado").value || "{}");
  } catch (e) {
    $("traza").textContent = "estado no es JSON: " + e.message;
    return;
  }
  const backend = $("backend").value;
  // recuperar el pack seleccionado del servicio
  const packsBody = await jsonFetch("/v1/packs");
  const packs = packsBody.packs.filter((p) => p.part === parte);
  const pack = packs.find((p) => p.name === $("pack").value) || packs[0];
  if (!pack) {
    $("traza").textContent = "no hay packs para la parte seleccionada";
    return;
  }

  const tarjetas = [];
  let ultimaTrazas = null;
  for (const q of pack.questions) {
    const d = await jsonFetch("/v1/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, state: body, backend }),
    });
    tarjetas.push(tarjetaDistribucion(d));
    ultimaTrazas = d.trace;
  }
  $("tarjetas").innerHTML = tarjetas.join("");
  $("traza").textContent = JSON.stringify(ultimaTrazas, null, 2);
}

document.addEventListener("DOMContentLoaded", () => {
  cargarBackends().catch((e) => ($("traza").textContent = String(e)));
  cargarPacks()
    .then(() => renderPreguntas(packByName([])))
    .catch((e) => ($("traza").textContent = String(e)));
  $("parte").addEventListener("change", () => {
    cargarPacks().catch((e) => ($("traza").textContent = String(e)));
  });
  $("pack").addEventListener("change", () => {
    jsonFetch("/v1/packs")
      .then((b) => {
        const packs = b.packs.filter((p) => p.part === $("parte").value);
        renderPreguntas(packByName(packs));
      })
      .catch(() => {});
  });
  $("decidir").addEventListener("click", decidir);
});
