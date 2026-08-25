"""Construye la aplicación principal V2 como un sitio Shinylive autocontenido."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

try:
    from .export_shinylive_smoke import (
        PVLIB_WHEEL_NAME,
        PVLIB_WHEEL_SHA256,
        ensure_pvlib_wheel,
        export_site,
        reset_generated_directory,
    )
    from .postprocess_export import postprocess
except ImportError:
    from export_shinylive_smoke import (  # type: ignore[no-redef]
        PVLIB_WHEEL_NAME,
        PVLIB_WHEEL_SHA256,
        ensure_pvlib_wheel,
        export_site,
        reset_generated_directory,
    )
    from postprocess_export import postprocess  # type: ignore[no-redef]


WEB_MODULES = (
    "app.py",
    "engine.py",
    "physics_adapter.py",
    "physics_core.py",
    "physics_pipeline.py",
    "shinylive_runtime_packages.py",
)


def prepare_application(repo_root: Path, staging_dir: Path) -> None:
    """Prepara una copia generada de la aplicación sin tocar sus fuentes."""

    reset_generated_directory(staging_dir, repo_root / "build")
    for name in WEB_MODULES:
        shutil.copy2(repo_root / "web_app" / name, staging_dir / name)
    shutil.copy2(
        repo_root / "web_app" / "shinylive_requirements.txt",
        staging_dir / "requirements.txt",
    )
    shutil.copytree(repo_root / "web_app" / "www", staging_dir / "www")
    shutil.copytree(repo_root / "digital_twin", staging_dir / "digital_twin")


def main() -> None:
    """Genera ``_site`` con la rueda científica como recurso independiente."""

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
        default=repo_root / "build" / "shinylive-app-source",
    )
    parser.add_argument(
        "--site",
        type=Path,
        default=repo_root / "_site",
    )
    parser.add_argument("--version", default="v2-local")
    args = parser.parse_args()

    wheel_path = args.wheel.resolve()
    staging_dir = args.staging.resolve()
    site_dir = args.site.resolve()
    ensure_pvlib_wheel(wheel_path)
    prepare_application(repo_root, staging_dir)
    export_site(
        staging_dir,
        site_dir,
        repo_root,
        wheel_path,
        allowed_site_parent=repo_root,
    )
    postprocess(site_dir, args.version)
    total_bytes = sum(path.stat().st_size for path in site_dir.rglob("*") if path.is_file())
    print(f"Aplicación V2 autocontenida creada en: {site_dir}")
    print(f"SHA-256 de pvlib verificado: {PVLIB_WHEEL_SHA256}")
    print(f"Tamaño estático total: {total_bytes} bytes")


if __name__ == "__main__":
    main()
