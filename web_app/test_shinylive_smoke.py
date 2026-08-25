"""Validación local del mismo informe que se ejecutará dentro de Pyodide."""

from __future__ import annotations

import unittest

from web_app.shinylive_smoke_app import run_smoke_checks


class ShinyliveSmokeReportTests(unittest.TestCase):
    """Impide exportar una prueba que ya falle en el entorno local."""

    def test_complete_smoke_report_passes_locally(self) -> None:
        """Todas las bibliotecas y métodos deben aprobar antes del export."""

        report = run_smoke_checks()
        failures = [check for check in report["checks"] if not check["passed"]]
        self.assertEqual(failures, [], msg=str(failures))
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
