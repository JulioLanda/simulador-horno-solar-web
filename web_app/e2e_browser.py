"""Revision automatica del simulador en un navegador Chromium real.

La prueba cubre dos superficies complementarias:

1. La exportacion Shinylive que se publica en GitHub Pages. Comprueba que la
   aplicacion, pvlib y la escena Three.js cargan sin solicitar codigo externo.
2. La aplicacion Shiny directa. Acciona los modos Home y Manual, verifica que
   los dos objetivos mecanicos sean independientes y que la arista inferior
   calculada del espejo permanezca horizontal.

Playwright es una dependencia exclusiva de desarrollo. De forma predeterminada
se utiliza el canal ``chrome`` ya instalado en Windows y en los ejecutores de
GitHub Actions; no se descarga otro navegador al dispositivo del usuario.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, Playwright, sync_playwright


TIMEOUT_MS = 180_000


def free_port() -> int:
    """Reserva brevemente un puerto local libre y devuelve su numero."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def wait_for_http(url: str, timeout_s: float = 30.0) -> None:
    """Espera hasta que un servidor local responda por HTTP."""

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception as error:  # El servidor aun puede estar arrancando.
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"El servidor no respondio en {url}: {last_error}")


@contextlib.contextmanager
def local_server(command: list[str], cwd: Path, url: str) -> Iterator[None]:
    """Inicia un servidor hijo, espera su disponibilidad y siempre lo detiene."""

    process = subprocess.Popen(  # noqa: S603 - argumentos controlados localmente.
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_http(url)
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def read_state(page: Page) -> dict[str, Any]:
    """Lee el JSON oculto que alimenta la escena tridimensional."""

    text = page.locator(".twin-state-payload").inner_text(timeout=TIMEOUT_MS)
    return dict(json.loads(text))


def wait_for_state(
    page: Page,
    predicate: Callable[[dict[str, Any]], bool],
    description: str,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """Espera una condicion fisica observable en el payload de la escena."""

    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last_state = read_state(page)
            if predicate(last_state):
                return last_state
        except (json.JSONDecodeError, KeyError):
            pass
        page.wait_for_timeout(120)
    raise AssertionError(f"No se cumplio {description}. Ultimo estado: {last_state}")


def assert_horizontal_lower_edge(state: dict[str, Any]) -> None:
    """Comprueba que la componente vertical de la arista inferior sea cero."""

    edge = state["mirror_horizontal_edge"]
    if len(edge) != 3 or abs(float(edge[2])) > 1e-10:
        raise AssertionError(f"La arista inferior no es horizontal: {edge}")


def check_static_export(browser: Browser, site_url: str, expected_version: str) -> None:
    """Valida la aplicacion Shinylive y que todos sus recursos sean locales."""

    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    external_requests: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        and not message.text.startswith("Failed to load resource:")
        else None,
    )

    def record_failed_request(request: Any) -> None:
        # Chrome solicita favicon.ico por convencion aunque la aplicacion no lo
        # declare. Su ausencia no afecta al simulador ni a sus dependencias.
        if urlparse(request.url).path.endswith("/favicon.ico"):
            return
        failed_requests.append(f"{request.url} ({request.failure or 'fallo sin detalle'})")

    page.on("requestfailed", record_failed_request)

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.scheme in {"http", "https", "ws", "wss"} and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
        }:
            external_requests.append(request.url)

    page.on("request", record_request)
    try:
        page.goto(site_url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        app = page.frame_locator("iframe.app-frame")
        app.locator("h1", has_text=f"Web {expected_version}").wait_for(
            state="visible",
            timeout=TIMEOUT_MS,
        )
        method = app.locator("#method")
        method.wait_for(state="visible", timeout=TIMEOUT_MS)
        options = method.locator("option").all_text_contents()
        if options != ["D&B", "REDA", "SPA/PVLIB"]:
            raise AssertionError(f"Metodos solares inesperados: {options}")

        canvas = app.locator("#twin3d-canvas")
        canvas.wait_for(state="visible", timeout=TIMEOUT_MS)
        app.locator("#twin3d-status").wait_for(state="visible", timeout=TIMEOUT_MS)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if canvas.get_attribute("data-initialized") == "true":
                break
            page.wait_for_timeout(150)
        else:
            diagnostics = {
                "estado": app.locator("#twin3d-status").inner_text(),
                "advertencia": app.locator("#twin3d-warning").inner_text(),
                "errores_pagina": page_errors,
                "errores_consola": console_errors,
                "solicitudes_fallidas": failed_requests,
            }
            raise AssertionError(
                "Three.js no inicializo el lienzo del gemelo digital: "
                + json.dumps(diagnostics, ensure_ascii=False)
            )

        if external_requests:
            raise AssertionError(f"La exportacion solicito recursos externos: {external_requests}")
        if page_errors:
            raise AssertionError(f"Errores JavaScript en Shinylive: {page_errors}")
        if console_errors:
            raise AssertionError(f"Errores de consola en Shinylive: {console_errors}")
        if failed_requests:
            raise AssertionError(f"Solicitudes fallidas en Shinylive: {failed_requests}")
    finally:
        page.close()


def check_direct_app(browser: Browser, app_url: str, expected_version: str) -> None:
    """Acciona Home y ambos ejes en Manual sobre la aplicacion Shiny directa."""

    page_errors: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        page.goto(app_url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        page.locator("h1", has_text=f"Web {expected_version}").wait_for(
            state="visible",
            timeout=TIMEOUT_MS,
        )
        page.locator("#method").wait_for(state="visible", timeout=TIMEOUT_MS)
        page.locator("#twin3d-canvas").wait_for(state="visible", timeout=TIMEOUT_MS)
        initial = wait_for_state(page, lambda state: "mirror_horizontal_edge" in state, "estado 3D inicial")
        assert_horizontal_lower_edge(initial)

        # Home fija AZ=0 grados y altura=90 grados.
        page.locator('input[name="mode"][value="Home"]').check()
        home = wait_for_state(
            page,
            lambda state: abs(float(state["az_target_deg"])) < 1e-9
            and abs(float(state["el_target_deg"]) - 90.0) < 1e-9,
            "objetivo Home AZ=0, EL=90",
        )
        assert_horizontal_lower_edge(home)

        # Manual: oeste cambia solo acimut; bajar cambia solo altura.
        page.locator('input[name="mode"][value="Manual"]').check()
        manual = wait_for_state(page, lambda state: state.get("mode") == "Manual", "modo Manual")
        az_before = float(manual["az_target_deg"])
        el_before = float(manual["el_target_deg"])
        page.locator("#jog_west").click()
        west = wait_for_state(
            page,
            lambda state: float(state["az_target_deg"]) > az_before,
            "avance positivo hacia oeste",
        )
        if abs(float(west["el_target_deg"]) - el_before) > 1e-9:
            raise AssertionError("El movimiento de acimut altero el objetivo de altura")

        az_after_west = float(west["az_target_deg"])
        page.locator("#jog_down").click()
        down = wait_for_state(
            page,
            lambda state: float(state["el_target_deg"]) < el_before,
            "descenso independiente del eje de altura",
        )
        if abs(float(down["az_target_deg"]) - az_after_west) > 1e-9:
            raise AssertionError("El movimiento de altura altero el objetivo de acimut")
        assert_horizontal_lower_edge(down)

        if page_errors:
            raise AssertionError(f"Errores JavaScript en Shiny: {page_errors}")
    finally:
        page.close()


def launch_browser(playwright: Playwright, channel: str) -> Browser:
    """Abre Chrome en modo sin interfaz con WebGL por software habilitado."""

    return playwright.chromium.launch(
        channel=channel,
        headless=True,
        args=["--use-angle=swiftshader", "--enable-webgl"],
    )


def main() -> None:
    """Levanta ambas aplicaciones y ejecuta toda la revision automatica."""

    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=repo_root / "_site")
    parser.add_argument("--channel", default="chrome")
    args = parser.parse_args()

    site_dir = args.site.resolve()
    if not (site_dir / "index.html").is_file():
        raise FileNotFoundError(f"No existe una exportacion Shinylive en {site_dir}")
    project_metadata = tomllib.loads(
        (repo_root / "web_app" / "pyproject.toml").read_text(encoding="utf-8")
    )
    expected_version = str(project_metadata["project"]["version"])

    static_port = free_port()
    shiny_port = free_port()
    static_url = f"http://127.0.0.1:{static_port}/"
    shiny_url = f"http://127.0.0.1:{shiny_port}/"
    static_command = [
        sys.executable,
        "-m",
        "http.server",
        str(static_port),
        "--bind",
        "127.0.0.1",
        "--directory",
        str(site_dir),
    ]
    shiny_command = [
        sys.executable,
        "-m",
        "shiny",
        "run",
        "--host",
        "127.0.0.1",
        "--port",
        str(shiny_port),
        str(repo_root / "web_app" / "app.py"),
    ]

    with local_server(static_command, repo_root, static_url), local_server(
        shiny_command,
        repo_root,
        shiny_url,
    ), sync_playwright() as playwright:
        browser = launch_browser(playwright, args.channel)
        try:
            check_static_export(browser, static_url, expected_version)
            check_direct_app(browser, shiny_url, expected_version)
        finally:
            browser.close()

    print("PASS: exportacion local, escena 3D y movimientos altazimutales verificados")


if __name__ == "__main__":
    main()
