"""Pruebas del empaquetado autocontenido del smoke test Shinylive."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from web_app.export_shinylive_smoke import (
    PVLIB_WHEEL_SHA256,
    patch_runtime_text,
    sha256_file,
)


class ShinyliveSelfContainedExportTests(unittest.TestCase):
    """Valida funciones críticas sin descargar ni exportar durante la suite."""

    def test_sha256_file_reads_binary_content(self) -> None:
        """El hash debe calcularse sobre bytes y no sobre texto transformado."""

        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "sample.bin"
            sample.write_bytes(b"Minihorno IER\x00pvlib")
            self.assertEqual(
                sha256_file(sample),
                "7480a7b8dd776cfa424689c0207fdadb2307829abfb9548a0dce667cf932eca2",
            )

    def test_runtime_patch_resolves_same_site_wheel_uri(self) -> None:
        """La adaptación debe crear una URL del mismo sitio sin cambiar cwd."""

        original = (
            "        req = req.strip()\n"
            "        extras = set()"
        )
        patched = patch_runtime_text(original)
        self.assertNotIn("os.chdir", patched)
        self.assertEqual(patched.count('req.startswith("site:")'), 1)
        self.assertIn(
            'req = str(URL.new(req[len("site:"):], location.href))',
            patched,
        )

    def test_expected_pvlib_hash_is_fixed(self) -> None:
        """El valor científico aprobado no debe quedar vacío o abreviado."""

        self.assertEqual(len(PVLIB_WHEEL_SHA256), 64)
        self.assertEqual(
            PVLIB_WHEEL_SHA256,
            "42035b063cc692bc3ece9480246297ccf211c835f1151faa752acac9584f6bb5",
        )


if __name__ == "__main__":
    unittest.main()
