"""Asset checks — D13.

Casos que o cenário competitivo produz e que quebram análise silenciosamente:
forfeit, mapa incompleto, partida sem estatísticas, roster incompleto.

Pronto quando: `dbt test` passa e cada exceção tem justificativa escrita.
"""

from __future__ import annotations

# TODO(D13): @asset_check para completude de composição, placar e roster.
