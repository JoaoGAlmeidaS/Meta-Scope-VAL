// D25-D28 — front estatico: fetch de JSON pre-computado, nada de inferencia aqui.
//
// Contrato de cache: toda requisicao de dados carrega ?v=<version> do meta.json.

const DATA = "data/";

let META = null;

async function loadMeta() {
  if (META) return META;
  const res = await fetch(`${DATA}meta.json`, { cache: "no-cache" });
  META = await res.json();
  return META;
}

async function loadJSON(path) {
  const meta = await loadMeta();
  const res = await fetch(`${DATA}${path}?v=${meta.version}`);
  if (!res.ok) throw new Error(`falha ao carregar ${path}: ${res.status}`);
  return res.json();
}

// TODO(D28): lookup de previsoes em predictions/{id}.json + estados vazio e de erro.
