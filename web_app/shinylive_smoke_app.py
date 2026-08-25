"""Miniaplicación de diagnóstico para ejecutar el núcleo dentro de Pyodide.

Este archivo no forma parte de la interfaz del simulador. Se exporta de manera
aislada con Shinylive y muestra un informe JSON que permite verificar que las
bibliotecas científicas y la cadena física completa funcionan realmente en el
navegador.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import sys
import time
import traceback
from collections.abc import Callable
from importlib.metadata import version
from typing import Any

from shiny import App, render, ui


# =============================================================================
# 1. ESTRUCTURA DE UNA COMPROBACIÓN
# =============================================================================

def _run_check(name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Ejecuta una comprobación, mide su duración y captura cualquier error."""

    # El reloj monotónico permite medir sin depender de la hora del sistema.
    started = time.perf_counter()
    try:
        # Cada operación devuelve detalles concretos para facilitar el diagnóstico.
        details = operation()
        return {
            "name": name,
            "passed": True,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "details": details,
        }
    except Exception as error:  # noqa: BLE001 - el smoke test debe informar todo fallo
        # La excepción se convierte en datos visibles en vez de derribar la app.
        return {
            "name": name,
            "passed": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }


# =============================================================================
# 2. COMPROBACIONES DE BIBLIOTECAS
# =============================================================================

def _check_scientific_packages() -> dict[str, Any]:
    """Importa las bibliotecas y ejecuta una rotación tridimensional conocida."""

    # Los imports permanecen explícitos para que Shinylive detecte los paquetes.
    # Las dependencias transitivas también se importan expresamente. Esto hace
    # que el export reducido de Shinylive copie sus ruedas locales de Pyodide,
    # en vez de intentar buscarlas en Internet durante cada visita.
    import certifi
    import charset_normalizer
    import h5py
    import numpy as np
    import pandas as pd
    import pvlib
    import requests
    import scipy
    import urllib3
    from scipy.spatial.transform import Rotation

    # ``pkgconfig`` es auxiliar de la rueda WebAssembly de h5py. En Windows la
    # instalación binaria local no lo requiere, por lo que su ausencia allí no
    # debe convertir en fallo una prueba destinada principalmente a Pyodide.
    try:
        import pkgconfig
    except ModuleNotFoundError:
        pkgconfig = None  # type: ignore[assignment]

    # Rotar +y noventa grados en sentido horario alrededor de +z debe producir +x.
    rotated = Rotation.from_rotvec(np.array((0.0, 0.0, -np.pi / 2.0))).apply(
        np.array((0.0, 1.0, 0.0))
    )
    # La comparación numérica comprueba que SciPy no solo se importó: también operó.
    if not np.allclose(rotated, np.array((1.0, 0.0, 0.0)), atol=1.0e-12):
        raise AssertionError(f"Rotación inesperada: {rotated!r}")

    # Registrar versiones identifica con precisión el entorno que pasó la prueba.
    return {
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "pvlib": pvlib.__version__,
        "h5py": h5py.__version__,
        "requests": requests.__version__,
        "certifi": certifi.__version__,
        "charset_normalizer": charset_normalizer.__version__,
        "urllib3": urllib3.__version__,
        "pkgconfig": (
            version("pkgconfig") if pkgconfig is not None else "not_required"
        ),
        "rotation_result": [float(component) for component in rotated],
    }


# =============================================================================
# 3. COMPROBACIÓN DEL FLUJO FÍSICO
# =============================================================================

def _load_pipeline_types() -> tuple[type[Any], Callable[[Any], Any]]:
    """Carga el pipeline tanto como paquete local como en el export aplanado."""

    try:
        # Ruta usada al ejecutar las pruebas desde la raíz del repositorio.
        from .physics_pipeline import PhysicalStepInputs, simulate_physical_step
    except ImportError:
        # Ruta usada por la carpeta aislada que Shinylive convierte en app.json.
        from physics_pipeline import PhysicalStepInputs, simulate_physical_step

    return PhysicalStepInputs, simulate_physical_step


def _check_pipeline_method(method: str) -> dict[str, Any]:
    """Calcula el caso de Temixco y exige un impacto centrado para un método."""

    # Cargar el mismo archivo que después consumirá el simulador V2.
    PhysicalStepInputs, simulate_physical_step = _load_pipeline_types()

    # El caso coincide con la referencia empleada por las pruebas matemáticas.
    inputs = PhysicalStepInputs(
        when=dt.datetime(2026, 8, 6, 12, 0, 0),
        latitude_deg=18.85,
        longitude_deg=-99.233333,
        utc_offset_hours=-6.0,
        site_altitude_m=1280.0,
        pressure_pa=101325.0,
        temperature_c=25.0,
        solar_method=method,
    )
    # La llamada recorre Sol, óptica, motores, límites, reflexión y receptor.
    result = simulate_physical_step(inputs)

    # Un método compatible debe producir una solución operativa e intersección válida.
    if not result.operational or not result.valid or result.impact is None:
        raise AssertionError(
            f"El método {method} no produjo impacto válido: {result.reason}"
        )
    # La solución ideal debe cerrar en el centro salvo redondeo de punto flotante.
    radial_error_m = float(result.impact.radial_error_m)
    if radial_error_m > 1.0e-9:
        raise AssertionError(
            f"El método {method} produjo error radial {radial_error_m:.12g} m"
        )

    # Conservar datos clave permite comparar el navegador con Python local.
    return {
        "requested_method": method,
        "resolved_method": result.solar_position.method,
        "solar_altitude_deg": result.solar_position.altitude_deg,
        "solar_azimuth_deg": result.solar_position.azimuth_deg,
        "ideal_azimuth_deg": result.ideal_commands.azimuth_deg,
        "ideal_height_deg": result.ideal_commands.height_deg,
        "limit_labels": list(result.limited_commands.limit_labels),
        "impact_u_m": result.impact.u_m,
        "impact_v_m": result.impact.v_m,
        "radial_error_m": radial_error_m,
        "reason": result.reason,
    }


# =============================================================================
# 4. INFORME COMPLETO DEL SMOKE TEST
# =============================================================================

def run_smoke_checks() -> dict[str, Any]:
    """Ejecuta todas las comprobaciones y devuelve un informe serializable."""

    # Medir el conjunto permite distinguir carga de bibliotecas y cálculo físico.
    started = time.perf_counter()
    checks = [
        _run_check("scientific_packages", _check_scientific_packages),
        _run_check("pipeline_reda", lambda: _check_pipeline_method("reda")),
        _run_check("pipeline_spa", lambda: _check_pipeline_method("spa")),
        _run_check(
            "pipeline_duffie_beckman",
            lambda: _check_pipeline_method("duffie_beckman"),
        ),
    ]
    # El informe global pasa solamente si ninguna comprobación individual falló.
    passed = all(check["passed"] for check in checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": sys.platform,
        },
        "total_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "checks": checks,
    }


# =============================================================================
# 5. INTERFAZ MÍNIMA EXCLUSIVA PARA DIAGNÓSTICO
# =============================================================================

# La página es deliberadamente independiente del menú y estilos del simulador.
app_ui = ui.page_fluid(
    ui.tags.style(
        """
        body { background: #f5f7fa; color: #172033; font-family: system-ui, sans-serif; }
        .smoke-card { max-width: 980px; margin: 2rem auto; padding: 1.5rem;
                      background: white; border: 1px solid #d9e0e8;
                      border-radius: 12px; box-shadow: 0 8px 28px #17203312; }
        #smoke_status { font-size: 1.2rem; font-weight: 700; }
        pre { max-height: 70vh; white-space: pre-wrap; }
        """
    ),
    ui.tags.main(
        {"class": "smoke-card"},
        ui.h2("Compatibilidad del núcleo físico con Shinylive/Pyodide"),
        ui.p(
            "Esta página ejecuta NumPy, SciPy, pandas, pvlib y la cadena física "
            "completa directamente dentro del navegador."
        ),
        ui.output_text("smoke_status"),
        ui.output_text_verbatim("smoke_report"),
    ),
    title="Smoke test Shinylive — Minihorno IER",
)


def server(input: Any, output: Any, session: Any) -> None:
    """Calcula una vez el informe y lo publica como texto verificable."""

    # Ejecutar después de que Pyodide haya iniciado la sesión de Shiny.
    report = run_smoke_checks()

    @render.text
    def smoke_status() -> str:
        """Muestra una señal corta que la automatización puede esperar."""

        return f"RESULTADO: {report['status']}"

    @render.text
    def smoke_report() -> str:
        """Muestra todos los resultados, versiones, tiempos y errores."""

        return json.dumps(report, ensure_ascii=False, indent=2)


# Objeto que Shinylive descubre al exportar la miniaplicación.
app = App(app_ui, server)


__all__ = ["app", "run_smoke_checks"]
