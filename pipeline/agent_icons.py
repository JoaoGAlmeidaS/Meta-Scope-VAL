"""Baixa os ícones de agente que faltam em web/assets/imgs/agentsV/ (`make agent-icons`).

O vlr.gg bloqueia exibir as imagens dele dentro de outro site (403 com o Referer do site), então o
ícone que a API manda (`dim_agent.image_url`) não serve para o `<img>`: o site serve uma cópia.
Roda à mão, depois do `make build`, quando aparece agente novo. Nunca sobrescreve arquivo que já
existe: ícone posto à mão na pasta vale mais que o do vlr.gg (`site_artifacts.image`).

Não é a API (`ingestion/client.py`): são arquivos estáticos do vlr.gg, poucos e uma vez só. Vai
com o mesmo User-Agent identificável e uma pausa entre os pedidos.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from ingestion.client import USER_AGENT
from pipeline.analyses import connect
from pipeline.site_artifacts import IMG_DIR

log = logging.getLogger(__name__)
FOLDER = IMG_DIR / "agentsV"
PAUSE_S = 1.0


def missing(con) -> list[tuple[str, str]]:
    """(agente, url) dos agentes com ícone na API e sem arquivo local em nenhum formato."""
    rows = con.sql(
        "select agent, image_url from main_marts.dim_agent where image_url is not null order by 1"
    ).fetchall()
    return [
        (agent, url)
        for agent, url in rows
        if not any((FOLDER / f"{agent}.{ext}").exists() for ext in ("svg", "png", "webp"))
    ]


def download(todo: list[tuple[str, str]], folder: Path = FOLDER) -> dict[str, str]:
    """Baixa cada ícone para `{agente}.png`; devolve o resultado por agente (ok ou o motivo)."""
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as c:
        for i, (agent, url) in enumerate(todo):
            if i:
                time.sleep(PAUSE_S)
            try:
                res = c.get(url)
            except httpx.HTTPError as exc:
                result[agent] = f"falhou: {exc}"
                continue
            if res.status_code != 200 or not res.headers.get("content-type", "").startswith(
                "image/"
            ):
                result[agent] = f"ignorado: {res.status_code} {res.headers.get('content-type')}"
                continue
            tmp = folder / f".{agent}.png.tmp"
            tmp.write_bytes(res.content)
            tmp.replace(folder / f"{agent}.png")
            result[agent] = "ok"
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por pedido é ruído
    todo = missing(connect())
    if not todo:
        log.info("nenhum ícone faltando em %s", FOLDER)
        return
    for agent, status in download(todo).items():
        log.info("%-24s %s", agent, status)


if __name__ == "__main__":
    main()
