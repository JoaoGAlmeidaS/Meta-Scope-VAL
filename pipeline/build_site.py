"""Geração do site: Jinja2 → dist/ — D22/D24.

Saída (contrato com o front):

    dist/
    ├── index.html
    ├── assets/                      style.css, app.js, echarts-theme.js
    ├── lineage/                     dbt docs
    └── data/
        ├── meta.json                versão do build, data, patches
        ├── teams/index.json         alimenta a busca
        ├── teams/{id}.json          perfil do time
        ├── predictions/{id}.json    todos os confrontos daquele time
        ├── meta/{mapa}-{patch}.json composições do recorte
        └── analyses/{nome}.json     séries das análises

O front usa `?v=` do `meta.json` nas requisições para invalidar o cache do navegador.

Pronto quando: `dist/data/` está completo e o maior arquivo cabe em poucas centenas de KB.
"""

from __future__ import annotations

from pathlib import Path

DIST = Path("dist")
TEMPLATES = Path("web/templates")
ASSETS = Path("web/assets")


def main() -> None:
    raise NotImplementedError("D22/D24")


if __name__ == "__main__":
    main()
