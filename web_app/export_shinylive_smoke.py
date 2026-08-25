"""Construye una exportación Shinylive autocontenida del smoke test físico.

La rueda de ``pvlib`` no se guarda en Git. Este script la descarga solamente
cuando falta en ``build/wheels``, comprueba su SHA-256 y la publica como un
recurso estático separado del ``app.json`` generado por Shinylive.

Shinylive 0.10.14 no resuelve rutas HTTP relativas dentro de
``requirements.txt``. El postproceso convierte la URI especial
``site:../assets/pvlib-0.15.2-py3-none-any.whl`` en una URL absoluta del mismo
origen antes de entregarla a ``micropip``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


# =============================================================================
# 1. ARTEFACTO CIENTÍFICO FIJADO
# =============================================================================

PVLIB_WHEEL_NAME = "pvlib-0.15.2-py3-none-any.whl"
PVLIB_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/8c/fb/"
    "263271dac97e246c9640eedb52b36087445569268115ff8051dc1736e64b/"
    f"{PVLIB_WHEEL_NAME}"
)
PVLIB_WHEEL_SHA256 = (
    "42035b063cc692bc3ece9480246297ccf211c835f1151faa752acac9584f6bb5"
)


# =============================================================================
# 2. DESCARGA Y VERIFICACIÓN
# =============================================================================

def sha256_file(path: Path) -> str:
    """Calcula el SHA-256 hexadecimal de un archivo sin cargarlo completo."""

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_pvlib_wheel(path: Path) -> None:
    """Rechaza cualquier rueda ausente o distinta de la versión aprobada."""

    if not path.is_file():
        raise FileNotFoundError(f"No se encontró la rueda fijada: {path}")
    actual = sha256_file(path)
    if actual.lower() != PVLIB_WHEEL_SHA256:
        raise RuntimeError(
            "SHA-256 inesperado para la rueda de pvlib: "
            f"esperado={PVLIB_WHEEL_SHA256}, obtenido={actual}"
        )


def ensure_pvlib_wheel(path: Path) -> None:
    """Reutiliza una rueda válida o la descarga y valida antes de adoptarla."""

    if path.exists():
        verify_pvlib_wheel(path)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".download")
    try:
        with urllib.request.urlopen(PVLIB_WHEEL_URL) as response:  # noqa: S310
            with temporary.open("wb") as destination:
                shutil.copyfileobj(response, destination)
        verify_pvlib_wheel(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


# =============================================================================
# 3. DIRECTORIOS GENERADOS Y STAGING
# =============================================================================

def reset_generated_directory(path: Path, allowed_parent: Path) -> None:
    """Recrea un único subdirectorio tras comprobar su alcance absoluto."""

    resolved_parent = allowed_parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_parent or resolved_path == resolved_parent:
        raise RuntimeError(f"Directorio generado fuera del alcance permitido: {path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)
    resolved_path.mkdir(parents=True)


def prepare_staging(repo_root: Path, staging_dir: Path) -> None:
    """Copia al staging el smoke test y los módulos canónicos de cálculo."""

    reset_generated_directory(staging_dir, repo_root / "build")
    sources = {
        repo_root / "web_app" / "shinylive_smoke_app.py": staging_dir / "app.py",
        repo_root / "web_app" / "shinylive_requirements.txt": (
            staging_dir / "requirements.txt"
        ),
        repo_root / "web_app" / "physics_core.py": staging_dir / "physics_core.py",
        repo_root / "web_app" / "physics_pipeline.py": (
            staging_dir / "physics_pipeline.py"
        ),
    }
    for source, destination in sources.items():
        if not source.is_file():
            raise FileNotFoundError(f"Archivo requerido ausente: {source}")
        shutil.copy2(source, destination)


# =============================================================================
# 4. EXPORTACIÓN Y POSTPROCESO DE SHINYLIVE
# =============================================================================

def shinylive_executable() -> Path:
    """Localiza el ejecutable Shinylive perteneciente al Python activo."""

    suffix = ".exe" if os.name == "nt" else ""
    beside_python = Path(sys.executable).with_name(f"shinylive{suffix}")
    if beside_python.is_file():
        return beside_python
    discovered = shutil.which("shinylive")
    if discovered is None:
        raise FileNotFoundError("No se encontró el ejecutable shinylive")
    return Path(discovered)


def patch_runtime_text(runtime: str) -> str:
    """Convierte requisitos ``site:`` en URL absolutas del mismo servidor."""

    original = (
        "        req = req.strip()\n"
        "        extras = set()"
    )
    replacement = (
        "        req = req.strip()\n"
        '        if req.startswith("site:"):\n'
        "            from js import URL, location\n"
        '            req = str(URL.new(req[len("site:"):], location.href))\n'
        "        extras = set()"
    )
    if runtime.count(original) != 1:
        raise RuntimeError(
            "No se encontró un único bucle de requisitos compatible con "
            "Shinylive 0.10.14"
        )
    return runtime.replace(original, replacement)


def export_site(
    staging_dir: Path,
    site_dir: Path,
    repo_root: Path,
    wheel_path: Path,
    *,
    allowed_site_parent: Path | None = None,
) -> None:
    """Exporta Shinylive y añade la rueda como recurso estático verificable."""

    reset_generated_directory(
        site_dir,
        allowed_site_parent or repo_root / "_site",
    )
    # Shinylive exige crear él mismo el directorio final; conservar solo el padre.
    site_dir.rmdir()
    subprocess.run(
        [
            str(shinylive_executable()),
            "export",
            str(staging_dir),
            str(site_dir),
            "--verbose",
        ],
        check=True,
        cwd=repo_root,
    )
    runtime_path = site_dir / "shinylive" / "shinylive.js"
    runtime = runtime_path.read_text(encoding="utf-8")
    runtime_path.write_text(patch_runtime_text(runtime), encoding="utf-8")
    assets_dir = site_dir / "assets"
    assets_dir.mkdir()
    shutil.copy2(wheel_path, assets_dir / PVLIB_WHEEL_NAME)


# =============================================================================
# 5. COMANDO REPRODUCIBLE
# =============================================================================

def main() -> None:
    """Construye el sitio smoke autocontenido en directorios ignorados por Git."""

    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wheel",
        type=Path,
        default=repo_root / "build" / "wheels" / PVLIB_WHEEL_NAME,
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=repo_root / "build" / "shinylive-smoke-source",
    )
    parser.add_argument(
        "--site",
        type=Path,
        default=repo_root / "_site" / "shinylive-smoke",
    )
    args = parser.parse_args()

    wheel_path = args.wheel.resolve()
    staging_dir = args.staging.resolve()
    site_dir = args.site.resolve()
    ensure_pvlib_wheel(wheel_path)
    prepare_staging(repo_root, staging_dir)
    export_site(staging_dir, site_dir, repo_root, wheel_path)
    print(f"Export autocontenido creado en: {site_dir}")
    print(f"SHA-256 de pvlib verificado: {PVLIB_WHEEL_SHA256}")


if __name__ == "__main__":
    main()
