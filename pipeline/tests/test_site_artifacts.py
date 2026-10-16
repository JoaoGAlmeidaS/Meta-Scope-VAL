"""D22: serialização dos JSONs do site. O conteúdo é testado pelo build sobre o lake de fixtures
(`make build-fixtures`, asset `site_artifacts` com o check de tamanho)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from pipeline.site_artifacts import Writer, clean, slug
from pipeline.stats import Estimate


def test_clean_converte_tipos_para_json():
    payload = {
        "estimate": Estimate(0.51234567, 0.5, 0.52, 10),
        "nan": float("nan"),
        "na": pd.NA,
        "day": pd.Timestamp("2026-05-01"),
        "moment": pd.Timestamp("2026-05-01 18:30"),
        "plain_date": date(2026, 5, 2),
        "ints": np.array([1, 2], dtype=np.int64),
        "flag": np.bool_(True),
        1: "chave inteira",
    }
    out = clean(payload)
    assert out["estimate"] == {"value": 0.512346, "low": 0.5, "high": 0.52, "n": 10}
    assert out["nan"] is None and out["na"] is None
    assert out["day"] == "2026-05-01"
    assert out["moment"] == "2026-05-01T18:30:00"
    assert out["plain_date"] == "2026-05-02"
    assert out["ints"] == [1, 2] and out["flag"] is True
    assert out["1"] == "chave inteira"
    json.dumps(out)  # serializável sem `default=`


def test_writer_grava_compacto_e_mede(tmp_path):
    write = Writer(tmp_path)
    write("teams/1.json", {"name": "LEVIATÁN", "rating": 1784.1234564})
    text = (tmp_path / "teams" / "1.json").read_text(encoding="utf-8")
    assert text == '{"name":"LEVIATÁN","rating":1784.123456}'
    assert write.sizes == {"teams/1.json": len(text.encode("utf-8"))}


def test_slug_do_mapa():
    assert slug("Ascent") == "ascent"


def test_imagem_manual_vence_a_da_api(tmp_path, monkeypatch):
    from pipeline import site_artifacts

    monkeypatch.setattr(site_artifacts, "IMG_DIR", tmp_path)
    api = "https://www.vlr.gg/img/vlr/game/agents/omen.png"
    assert site_artifacts.image("agentsV", "omen", api) == api
    assert site_artifacts.image("agentsV", "omen", float("nan")) is None  # sem ícone na API
    (tmp_path / "agentsV").mkdir()
    (tmp_path / "agentsV" / "omen.webp").write_bytes(b"x")
    assert site_artifacts.image("agentsV", "omen", api) == "assets/imgs/agentsV/omen.webp"


def test_download_de_icones_so_grava_imagem(tmp_path, monkeypatch):
    import httpx

    from pipeline import agent_icons

    def handler(request):
        if "omen" in request.url.path:
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        return httpx.Response(403, text="forbidden", headers={"content-type": "text/html"})

    real_client = httpx.Client
    monkeypatch.setattr(
        agent_icons.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(agent_icons, "PAUSE_S", 0)
    result = agent_icons.download(
        [("omen", "https://x/agents/omen.png"), ("hash", "https://x/agents/hash.png")], tmp_path
    )
    assert result["omen"] == "ok" and result["hash"].startswith("ignorado: 403")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["omen.png"]


def test_imagem_casa_sem_diferenciar_maiusculas(tmp_path, monkeypatch):
    from pipeline import site_artifacts

    monkeypatch.setattr(site_artifacts, "IMG_DIR", tmp_path)
    (tmp_path / "maps").mkdir()
    (tmp_path / "maps" / "Haven.webp").write_bytes(b"x")
    (tmp_path / "maps" / "haven.jpg").write_bytes(b"x")  # webp tem preferência sobre jpg
    assert site_artifacts.image("maps", "haven", None) == "assets/imgs/maps/Haven.webp"
    assert site_artifacts.image("maps", "summit", None) is None
