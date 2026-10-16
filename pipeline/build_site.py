"""D24: gerador do site estático, Jinja2 → dist/.

    dist/
    ├── index.html, rankings.html, team.html, meta.html, previsoes.html, analises.html
    ├── analise-{nome}.html      uma página por pergunta (gráfico, IC, método, notebook)
    ├── assets/                  style.css, echarts-theme.js, app.js (cópia de web/assets)
    ├── lineage/                 dbt docs (make docs)
    └── data/                    JSONs do site_artifacts (D22)

O HTML sai com o texto e os números de cabeçalho já escritos, a partir dos mesmos JSONs que o
front lê: a resposta de cada pergunta não depende de JavaScript, e o gráfico sim. Cada análise
leva a resposta dos seis recortes (janela × tier); o JS mostra a do recorte escolhido, e sem JS
fica a do padrão. Cache: CSS e JS
levam `?v=` do hash do próprio conteúdo; os JSONs, `?v=` da versão do build (meta.json).

Sem servidor: tudo relativo, então funciona em `make serve` e no subcaminho do GitHub Pages.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from ingestion.config import ROOT
from pipeline.analyses import DEFAULT, SCOPES
from pipeline.site_artifacts import dist_dir
from pipeline.stats import Estimate, fmt

WEB = ROOT / "web"
REPO = os.environ.get("GITHUB_REPOSITORY", "JoaoGAlmeidaS/Meta-Scope-VAL")
REPO_URL = f"https://github.com/{REPO}"

# Previsões de confronto: a página está em desenvolvimento. Desligado, `previsoes.html` sai do
# `soon.html.j2`; o template completo (`predictions.html.j2`), o módulo `pages.predictions` do
# app.js e os `predictions/{id}.json` continuam prontos para quando voltar.
PREDICTIONS_ENABLED = False


def asset_file(name: str) -> str | None:
    """`imgs/<name>.svg|png|webp` de web/assets, se existir (logos e favicon são opcionais)."""
    for ext in ("svg", "png", "webp"):
        if (WEB / "assets" / "imgs" / f"{name}.{ext}").exists():
            return f"imgs/{name}.{ext}"
    return None


def est(d: dict | None) -> Estimate | None:
    return (
        Estimate(d["value"], d["low"], d["high"], d["n"])
        if d and d.get("value") is not None
        else None
    )


def b(text: str) -> str:
    return f"<b>{text}</b>"


def pct(e: Estimate | None) -> str:
    return e.text(percent=True) if e else "amostra insuficiente"


def strong(e: Estimate | None, **kw) -> str:
    """Valor em negrito, IC em texto normal: '<b>51,2%</b> (IC 95% 50,8%–51,5%)'."""
    if not e:
        return "amostra insuficiente"
    value, rest = e.text(**kw).split(" (", 1)
    return f"{b(value)} ({rest}"


@dataclass
class Analysis:
    slug: str
    file: str
    title: str
    question: str
    notebook: str
    day: str
    method: list[str]
    second_chart: str | None = None
    has_chart: bool = True  # composições é só tabela: sem painel de gráfico vazio
    table_title: str = "Tabela"
    has_window: bool = True  # a tese da janela é o histórico inteiro: só o tier muda
    # resposta e veredito por recorte (`Scope.key`); `answer` e `verdict` são os do padrão
    answers: dict[str, tuple[Markup, tuple[str, str]]] | None = None
    answer: Markup = Markup("")
    verdict: tuple[str, str] = ("inconclusivo", "muted")
    number: int = 0  # posição na lista (01…08), usada no índice e nas abas


ANALYSES = [
    Analysis(
        "janela",
        "drift",
        "A tese da janela",
        "O jogo muda o bastante para justificar a janela de 12 meses?",
        "00_tese_da_janela_drift.ipynb",
        "D17",
        [
            "Histórico inteiro (a única exceção à janela): coleta própria desde 2025; o período "
            "anterior virá de um dataset importado à parte.",
            "Meta: distância de variação total entre a distribuição de agentes de cada trimestre e "
            "a do trimestre mais recente com amostra, por mapa (0 = mesmo meta, 1 = nenhum agente "
            "em comum). IC por bootstrap paramétrico; o piso de ruído é a distância que só a "
            "amostragem produziria se nada tivesse mudado.",
            "Lado: rounds 1–24 vencidos pelo ataque por mapa e trimestre, com o n efetivo (rounds "
            "÷ efeito de desenho) e teste de homogeneidade por mapa com correção de Holm.",
        ],
        table_title="O lado favorecido muda entre trimestres?",
        has_window=False,
    ),
    Analysis(
        "lados",
        "sides",
        "Lados por mapa",
        "Algum mapa favorece o ataque ou a defesa?",
        "01_lados_por_mapa.ipynb",
        "D18",
        [
            "Rounds regulamentares (1–24): no overtime os lados alternam a cada round.",
            "Só mapas com histórico de lado; os demais contam no placar e no Elo, não aqui.",
            "IC por bootstrap de mapas: rounds do mesmo mapa são correlacionados, e o IC de Wilson "
            "sobre rounds seria cerca de um terço mais estreito do que deveria.",
            "Teste contra 50% com correção de Holm entre os mapas.",
        ],
    ),
    Analysis(
        "pistol",
        "pistol",
        "Pistol",
        "Quanto o pistol decide o mapa, com Elo igual?",
        "02_pistol.ipynb",
        "D18",
        [
            "Pistols: rounds 1 e 13. Uma linha por mapa, do ponto de vista de um dos times.",
            "Regressão logística: venceu o mapa ~ pistols vencidos (0, 1, 2) + diferença de Elo "
            "pré-partida ÷ 100. O win rate bruto mistura o pistol com a força do time.",
            'As probabilidades "com Elo igual" são as previstas pelo modelo para diferença zero.',
        ],
        table_title="Razões de chances",
    ),
    Analysis(
        "veto",
        "veto",
        "Veto",
        "Escolher o mapa dá vantagem?",
        "03_veto.ipynb",
        "D19",
        [
            "Desenho pareado: nas séries em que cada time escolheu um mapa, a força dos times se "
            "cancela; sem efeito de pick, quem escolhe venceria 50% dos próprios picks.",
            "Por mapa: resultado de quem escolheu menos a probabilidade de mapa pelo Elo. O Elo "
            "prevê a série; a probabilidade por mapa sai invertendo P(BO3) = p²(3 − 2p) e a "
            "da BO5.",
            "IC por bootstrap, Holm entre mapas. A matriz completa do veto está na página de meta.",
        ],
    ),
    Analysis(
        "regioes",
        "regions",
        "Regiões",
        "Alguma região rende acima ou abaixo do Elo nos confrontos internacionais?",
        "04_regioes.ipynb",
        "D19",
        [
            "Séries internacionais entre times de regiões diferentes (região do time na época).",
            "Resultado − probabilidade pré-partida do Elo, por região; IC por bootstrap, Holm.",
            "Região abaixo do Elo = Elo superestimado pela liga doméstica, que quase não cruza com "
            "as outras. Amostra pequena: poucas dezenas de séries por região.",
        ],
        table_title="Confrontos entre regiões",
    ),
    Analysis(
        "composicoes",
        "compositions",
        "Composições",
        "Alguma composição vence mais do que a força de quem a joga explica?",
        "05_meta_composicao.ipynb",
        "D20",
        [
            "Desempenho acima do esperado: vitórias − probabilidade de vencer o mapa pelo Elo "
            '(time forte joga comp "forte" e venceria de qualquer jeito).',
            "Shrinkage empírico normal–normal por mapa × versão do patch (12.x, 13.x): comp com "
            "pouca amostra é puxada para zero. Por patch exato a amostra não sustenta.",
            "A tabela mostra as 15 maiores estimativas com 5 mapas ou mais; o recorte por mapa e "
            "patch está na página de meta.",
        ],
        table_title="Maiores estimativas",
        has_chart=False,
    ),
    Analysis(
        "calibracao",
        "calibration",
        "Calibração do Elo",
        "A probabilidade do Elo é calibrada?",
        "07_previsao_calibracao.ipynb",
        "D21",
        [
            "A probabilidade avaliada é a da fórmula do Elo, sem modelo treinado; o rating usado é "
            "sempre o de antes da partida.",
            "Log loss e Brier com IC por bootstrap, contra a moeda (0,693 e 0,25). Acurácia "
            "fica de fora: premia acertar o lado, não a probabilidade.",
            "Curva de calibração por faixa de probabilidade, com IC de Wilson.",
        ],
        table_title="Métricas",
    ),
    Analysis(
        "velocidade",
        "meta-speed",
        "Velocidade do meta",
        "Quão rápido o meta de agentes se reorganiza?",
        "08_velocidade_do_meta.ipynb",
        "D20",
        [
            "Pick rate de um agente no mês: composições (time × mapa) com o agente ÷ composições.",
            "Velocidade: distância de variação total entre o meta de um mês e o do anterior, com "
            "IC por bootstrap paramétrico e o piso de ruído. Patches em dourado (X.00 em "
            "destaque).",
        ],
        second_chart="Pick rate por mês",
        table_title="Mês a mês",
    ),
]


# --- respostas (o texto de cabeçalho de cada pergunta) -------------------------------------------


def drift_summary(d) -> dict | None:
    """O meta a um trimestre e a 12 meses ou mais do atual, com o piso de ruído (D17).

    Usado na resposta da tese da janela e no destaque da home.
    """
    age = d["meta_by_age"]
    if not age:
        return None
    far = [r for r in age if r["quarters_before"] >= 4] or age[-1:]
    return {
        "near": age[0]["distance"],
        "near_floor": age[0]["noise_floor"],
        "far": sum(r["distance"] for r in far) / len(far),
        "floor": max(r["noise_floor"] for r in age),
    }


def answer_janela(d) -> tuple[str, tuple[str, str]]:
    s = drift_summary(d)
    if not s:
        return "Histórico curto demais para medir a deriva.", ("amostra insuficiente", "muted")
    changed = sum(1 for r in d["homogeneity"] if r["changes"])
    side = (
        f"a vantagem de lado muda além do acaso em {changed} de {len(d['homogeneity'])} mapas."
        if changed
        else f"a vantagem de lado não muda além do acaso em nenhum dos {len(d['homogeneity'])} "
        "mapas: nesse recorte, inconclusivo."
    )
    text = (
        f"Um trimestre atrás, o meta de agentes de um mapa já está a {b(fmt(s['near'], 2))} "
        f"do atual (piso de ruído {fmt(s['near_floor'], 2)}); a 12 meses ou mais, a "
        f"{b(fmt(s['far'], 2))}. Dado mais antigo descreve outro jogo. Já {side}"
    )
    ok = s["far"] > s["floor"]
    return text, ("sustenta a janela", "gold") if ok else ("inconclusivo", "muted")


def answer_lados(d) -> tuple[str, tuple[str, str]]:
    maps = d["maps"]
    if not maps:
        return "Sem mapas com histórico de lado na janela.", ("amostra insuficiente", "muted")
    by = {v: [m for m in maps if m["verdict"] == v] for v in ("ataque", "defesa")}

    def names(rows):
        return ", ".join(
            f"{m['map_name']} ({pct(est(m['estimate'])).split(' (')[0]})" for m in rows
        )

    parts = [f"O ataque vence {strong(est(d['overall']), percent=True)} dos rounds regulamentares."]
    if by["ataque"]:
        parts.append(f"Favorecem o ataque: {names(by['ataque'])}.")
    if by["defesa"]:
        parts.append(f"Favorecem a defesa: {names(by['defesa'])}.")
    n_inc = len(maps) - len(by["ataque"]) - len(by["defesa"])
    parts.append(f"{n_inc} de {len(maps)} mapas são inconclusivos.")
    sig = len(maps) - n_inc
    return " ".join(parts), (f"{sig} de {len(maps)} mapas", "attack" if sig else "muted")


def answer_pistol(d) -> tuple[str, tuple[str, str]]:
    eq = d.get("equal_elo")
    if not eq:
        return "Amostra insuficiente para a regressão.", ("amostra insuficiente", "muted")
    two, zero = est(eq["2"]), est(eq["0"])
    odds = est(d["odds_ratios"]["C(pistols)[T.2]"])
    text = (
        "Com Elo igual, quem vence os dois pistols vence o mapa em "
        f"{strong(two, percent=True)}; quem perde os dois, em {strong(zero, percent=True)}. "
        f"Vencer os dois multiplica as chances por {odds.text(2)} — o maior efeito isolado "
        "medido no projeto."
    )
    # recorte pequeno pode não separar o efeito de 1 (chances iguais)
    return text, ("efeito forte", "positive") if odds.low > 1 else ("inconclusivo", "muted")


def answer_veto(d) -> tuple[str, tuple[str, str]]:
    paired = est(d["paired"])
    if not paired:
        return "Sem séries com picks dos dois times.", ("amostra insuficiente", "muted")
    sig = [m for m in d["maps"] if m["verdict"] != "inconclusivo"]
    excludes = paired.excludes(0.5)
    text = (
        f"Quem escolhe vence {strong(paired, percent=True)} dos próprios picks em "
        f"{d['paired_matches']} séries pareadas{'' if excludes else ': o IC inclui 50%'}. "
        f"Por mapa, {len(sig)} de {len(d['maps'])} têm efeito depois da correção de Holm."
    )
    if not excludes and not sig:
        text += " Se a vantagem existe, é menor do que a janela consegue separar."
    return text, ("vantagem de quem escolhe", "positive") if excludes else ("inconclusivo", "muted")


def answer_regioes(d) -> tuple[str, tuple[str, str]]:
    regs = d["regions"]
    if not regs:
        return "Sem confrontos internacionais entre regiões na janela.", (
            "amostra insuficiente",
            "muted",
        )
    sig = [r for r in regs if r["verdict"] != "inconclusivo"]
    inc = [r["region"] for r in regs if r["verdict"] == "inconclusivo"]
    parts = [
        f"{r['region'].capitalize()} rende {r['verdict']} nos internacionais: "
        f"{strong(est(r['excess_over_elo']), digits=2)} em {r['matches']} séries."
        for r in sig
    ]
    if inc:
        parts.append(f"Inconclusivas: {', '.join(inc)} ({d['matches']} séries entre regiões).")
    return " ".join(parts), (f"{len(sig)} de {len(regs)} regiões", "gold" if sig else "muted")


def answer_composicoes(d) -> tuple[str, tuple[str, str]]:
    if not d["tested"]:
        return "Nenhuma composição com amostra suficiente.", ("amostra insuficiente", "muted")
    n = d["above"] + d["below"]
    text = (
        f"Depois do controle pela força do time e do shrinkage, {b(str(n))} de {d['tested']} "
        "combinações composição × mapa × patch se distinguem do esperado pelo Elo."
    )
    if not n:
        text += " O meta se mede pela popularidade, não por vantagem de desempenho detectável."
    return text, ("inconclusivo", "muted") if not n else (f"{n} composições", "positive")


def answer_calibracao(d) -> tuple[str, tuple[str, str]]:
    allm = d.get("all")
    if not allm or not allm["n"]:
        return "Sem partidas na janela.", ("amostra insuficiente", "muted")
    ll = est(allm["log_loss"])
    text = (
        f"Na janela ({allm['n']} séries), log loss {strong(ll, digits=4)} contra 0,693 da "
        f"moeda; Brier {est(allm['brier']).text(4)} contra 0,25."
    )
    vct = d.get("vct")
    if vct and vct["n"]:
        v = est(vct["log_loss"])
        same = v.high >= allm["coin_log_loss"]
        text += f" Na VCT, {v.text(4)}: " + (
            "indistinguível da moeda — no topo, os times são parecidos."
            if same
            else "melhor que a moeda."
        )
    ok = ll.high < allm["coin_log_loss"]
    return text, ("melhor que a moeda", "positive") if ok else ("inconclusivo", "muted")


def answer_velocidade(d) -> tuple[str, tuple[str, str]]:
    sp = d["speed"]
    if not sp:
        return "Janela curta demais para comparar meses.", ("amostra insuficiente", "muted")
    real = [r for r in sp if r["low"] > r["noise_floor"]]
    full = [r for r in sp if r["compositions"] >= 500] or sp
    peak = max(full, key=lambda r: r["distance"])
    text = (
        f"Em {b(f'{len(real)} de {len(sp)}')} meses o meta muda acima do piso de ruído. A maior "
        f"reorganização fora do off-season foi em {peak['month'][5:7]}/{peak['month'][:4]}: "
        f"{b(fmt(peak['distance'], 3))} do pick de agentes trocado em relação ao mês anterior."
    )
    return text, ("muda todo mês", "gold") if len(real) > len(sp) / 2 else ("inconclusivo", "muted")


ANSWERS = {a.slug: globals()[f"answer_{a.slug}"] for a in ANALYSES}


# --- geração --------------------------------------------------------------------------------------


def load(data: Path, name: str):
    return json.loads((data / name).read_text(encoding="utf-8"))


def build(dist: Path | None = None) -> list[str]:
    """Renderiza as páginas e copia os assets; devolve os arquivos HTML gerados."""
    dist = dist or dist_dir()
    data = dist / "data"
    meta = load(data, "meta.json")
    teams = load(data, "teams/index.json")

    analyses = []
    for i, a in enumerate(ANALYSES, start=1):
        a.answers = {}
        for scope in SCOPES:
            text, verdict = ANSWERS[a.slug](load(data, f"analyses/{scope.key}/{a.file}.json"))
            a.answers[scope.key] = (Markup(text), verdict)
        a.answer, a.verdict = a.answers[DEFAULT.key]
        a.number = i
        analyses.append(a)
    default = f"analyses/{DEFAULT.key}"
    hero = drift_summary(load(data, f"{default}/drift.json"))

    env = Environment(
        loader=FileSystemLoader(WEB / "templates"),
        autoescape=select_autoescape(["j2", "html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["num"] = lambda x, d=0: fmt(x, d) if x is not None else "—"
    env.filters["pct"] = lambda x, d=0: f"{fmt(x * 100, d)}%" if x is not None else "—"
    env.filters["thousands"] = lambda x: f"{x:,}".replace(",", ".")
    env.filters["date_br"] = lambda s: "/".join(reversed(s[:10].split("-"))) if s else "—"
    # Cache: o asset leva o hash do próprio conteúdo (muda o CSS, muda a URL); os JSONs levam a
    # versão do build, pelo app.js.
    # chave = caminho relativo a web/assets ("style.css", "imgs/logo.svg"); subpastas entram
    assets_dir = WEB / "assets"
    asset_v = {
        f.relative_to(assets_dir).as_posix(): hashlib.sha1(f.read_bytes()).hexdigest()[:10]
        for f in sorted(assets_dir.rglob("*"))
        if f.is_file()
    }
    common = {
        "meta": meta,
        "version": meta["version"],
        "asset_v": asset_v,
        # logo do site por tema: logoE (escuro) e logoC (claro); com um só, ele serve aos dois
        "logo_dark": asset_file("logoE") or asset_file("logoC"),
        "logo_light": asset_file("logoC") or asset_file("logoE"),
        "favicon": asset_file("favicon"),
        "predictions_enabled": PREDICTIONS_ENABLED,
        "analyses": analyses,
        "default_scope": DEFAULT.key,
        "repo_url": REPO_URL,
        "notebook_url": f"{REPO_URL}/blob/main/notebooks/",
    }
    # topo da VCT na home: sem os provisórios (poucas séries de VCT na janela, ex.: promovidos)
    vct_top = [t for t in teams if t["tier"] == "vct" and not t["provisional"]][:10]
    calibration = load(data, f"{default}/calibration.json")
    cal = {
        k: est(calibration[k]["log_loss"]).text(3) if calibration.get(k) else None
        for k in ("all", "vct")
    }
    pages = {
        "index.html": (
            "index.html.j2",
            {"page": "home", "top": vct_top, "hero": hero, "calibration": cal},
        ),
        "rankings.html": ("rankings.html.j2", {"page": "rankings"}),
        "team.html": ("team.html.j2", {"page": "team"}),
        "meta.html": ("meta.html.j2", {"page": "meta"}),
        "previsoes.html": (
            ("predictions.html.j2", {"page": "predictions", "calibration": cal})
            if PREDICTIONS_ENABLED
            else ("soon.html.j2", {"page": "predictions-soon"})
        ),
        "analises.html": ("analyses.html.j2", {"page": "analyses"}),
    }
    for a in analyses:
        pages[f"analise-{a.slug}.html"] = ("analysis.html.j2", {"page": "analysis", "a": a})

    written = []
    for out, (template, ctx) in pages.items():
        html = env.get_template(template).render(**common, **ctx)
        (dist / out).write_text(html, encoding="utf-8")
        written.append(out)

    assets = dist / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(WEB / "assets", assets)
    (dist / ".nojekyll").touch()  # o Pages serve as pastas como estão
    return written


def main() -> None:
    pages = build()
    print(f"{len(pages)} páginas em {dist_dir()}")


if __name__ == "__main__":
    main()
