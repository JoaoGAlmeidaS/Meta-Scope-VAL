"""`make serve`: o dist/ em localhost:8000, para testar o site antes do deploy.

O `python -m http.server` não manda `Cache-Control`, e o navegador reaproveita por heurística o
HTML de uma visita anterior: depois de um build, a página velha continua na tela. CSS, JS e JSON
escapam pelo `?v=`; o HTML, não. Aqui toda resposta sai com `no-cache`, que não proíbe o cache,
só obriga a revalidar: arquivo igual volta como 304 (`If-Modified-Since`), arquivo novo vem inteiro.
"""

from __future__ import annotations

import os
from contextlib import suppress
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pipeline.site_artifacts import dist_dir

PORT = int(os.environ.get("PORT", 8000))


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    root = dist_dir()
    handler = partial(NoCacheHandler, directory=str(root))
    with ThreadingHTTPServer(("", PORT), handler) as server:
        print(f"{root} em http://localhost:{PORT}/ (Ctrl+C para parar)")
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
