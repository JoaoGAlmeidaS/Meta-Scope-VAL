"""Assets — D12.

    raw_matches → raw_match_details → (dbt via dagster-dbt) → site_artifacts

⚠️ Ponto de corte do D12: se ao fim do dia nada materializar, **corte o Dagster** e siga com
o GitHub Actions chamando scripts. Migrar depois é fácil; travar aqui arruína o prazo.
"""

from __future__ import annotations

# TODO(D12): @asset particionado por split + @dbt_assets + asset site_artifacts (D22).
