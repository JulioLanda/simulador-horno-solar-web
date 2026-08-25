"""Marcadores explícitos de paquetes que debe incluir el export Shinylive.

Shinylive crea una exportación reducida mediante análisis de imports. ``pvlib``
declara dependencias que no aparecen directamente en la interfaz principal;
esta función hace visible el conjunto probado en Pyodide sin duplicar ninguna
operación matemática.
"""

from __future__ import annotations


def preload_scientific_runtime() -> None:
    """Importa las dependencias verificadas una vez que Pyodide las precargó."""

    import certifi  # noqa: F401
    import charset_normalizer  # noqa: F401
    import h5py  # noqa: F401
    import numpy  # noqa: F401
    import pandas  # noqa: F401
    import pkgconfig  # noqa: F401
    import requests  # noqa: F401
    import scipy  # noqa: F401
    import urllib3  # noqa: F401


__all__ = ["preload_scientific_runtime"]
