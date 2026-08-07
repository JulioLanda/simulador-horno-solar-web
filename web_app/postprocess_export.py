"""Evita que Shinylive reutilice una version anterior de la aplicacion."""

from __future__ import annotations

import argparse
from pathlib import Path


def postprocess(site_dir: Path, version: str) -> None:
    index_path = site_dir / "index.html"
    runtime_path = site_dir / "shinylive" / "shinylive.js"

    index = index_path.read_text(encoding="utf-8")
    if "<title>Shiny App</title>" not in index:
        raise RuntimeError("No se encontro el titulo generico de Shinylive")
    index = index.replace('<html lang="en">', '<html lang="es">')
    index = index.replace(
        "<title>Shiny App</title>",
        "<title>Gemelo digital del mini horno solar</title>",
    )
    index = index.replace(
        'src="./shinylive/load-shinylive-sw.js"',
        f'src="./shinylive/load-shinylive-sw.js?v={version}"',
    )
    index = index.replace(
        'from "./shinylive/shinylive.js"',
        f'from "./shinylive/shinylive.js?v={version}"',
    )
    index_path.write_text(index, encoding="utf-8")

    runtime = runtime_path.read_text(encoding="utf-8")
    original = 'fetch("./app.json")'
    replacement = 'fetch("./app.json", { cache: "no-store" })'
    if runtime.count(original) != 1:
        raise RuntimeError("No se encontro una unica carga de app.json en Shinylive")
    runtime_path.write_text(runtime.replace(original, replacement), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    postprocess(args.site_dir, args.version)


if __name__ == "__main__":
    main()
