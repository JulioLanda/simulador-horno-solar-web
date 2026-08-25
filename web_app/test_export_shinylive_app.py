"""Pruebas del empaquetado de la aplicación V2 principal."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from web_app.export_shinylive_app import WEB_MODULES, prepare_application


class MainShinyliveExportTests(unittest.TestCase):
    """Comprueba que el staging contiene una sola copia de cada fuente requerida."""

    def test_manifest_includes_complete_v2_integration(self) -> None:
        self.assertIn("physics_adapter.py", WEB_MODULES)
        self.assertIn("physics_core.py", WEB_MODULES)
        self.assertIn("physics_pipeline.py", WEB_MODULES)
        self.assertIn("shinylive_runtime_packages.py", WEB_MODULES)

    def test_prepare_application_copies_modules_assets_and_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / "web_app"
            twin = root / "digital_twin"
            www = web / "www"
            build = root / "build"
            web.mkdir()
            twin.mkdir()
            www.mkdir()
            build.mkdir()
            for name in WEB_MODULES:
                (web / name).write_text(f"# {name}\n", encoding="utf-8")
            (web / "shinylive_requirements.txt").write_text(
                "site:../assets/pvlib.whl\n",
                encoding="utf-8",
            )
            (www / "twin3d.js").write_text("// scene\n", encoding="utf-8")
            (twin / "error_model.py").write_text("# errors\n", encoding="utf-8")

            staging = build / "shinylive-app-source"
            prepare_application(root, staging)

            self.assertTrue((staging / "physics_adapter.py").is_file())
            self.assertTrue((staging / "requirements.txt").is_file())
            self.assertTrue((staging / "www" / "twin3d.js").is_file())
            self.assertTrue((staging / "digital_twin" / "error_model.py").is_file())


if __name__ == "__main__":
    unittest.main()
