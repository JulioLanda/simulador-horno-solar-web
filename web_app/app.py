"""Edicion web experimental del gemelo digital del mini horno solar."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
from pathlib import Path

from shiny import App, reactive, render, ui

try:
    from .engine import MINIHORNO_WEB_PROFILE, WebTwinState
except ImportError:
    from engine import MINIHORNO_WEB_PROFILE, WebTwinState


APP_DIR = Path(__file__).parent


def number(value: object, digits: int = 2) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{numeric:.{digits}f}" if math.isfinite(numeric) else "--"


def json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def svg_document(content: str, width: int = 1000, height: int = 520, dark: bool = False) -> str:
    background = "#0b1620" if dark else "#f8fafc"
    return (
        f'<svg class="sim-svg" viewBox="0 0 {width} {height}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" style="background:{background}">'
        f"{content}</svg>"
    )


def scene_svg(sample: dict[str, object]) -> str:
    target = tuple(float(value) for value in sample["target"])
    sun = tuple(float(value) for value in sample["sun"])
    normal = tuple(float(value) for value in sample["normal"])

    def project(point: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = point
        return 210.0 + x * 54.0 + y * 72.0, 350.0 - z * 72.0 - y * 24.0

    origin = project((0.0, 0.0, 0.0))
    target_point = project(target)
    grid_lines: list[str] = []
    for longitudinal in range(0, 8):
        start = project((-2.2, longitudinal * 0.8, -1.4))
        end = project((2.2, longitudinal * 0.8, -1.4))
        grid_lines.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" />'
        )
    for transverse in range(-2, 3):
        start = project((transverse * 0.8, 0.0, -1.4))
        end = project((transverse * 0.8, 6.4, -1.4))
        grid_lines.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" />'
        )
    mirror_center = project((0.0, 0.0, 0.0))
    azimuth = math.radians(float(sample["az_deg"]))
    elevation = math.radians(float(sample["el_deg"]))
    half_width = 78.0
    half_height = max(12.0, 58.0 * abs(math.sin(elevation)) + 8.0)
    skew = 25.0 * math.sin(azimuth)
    mirror_points = (
        (mirror_center[0] - half_width + skew, mirror_center[1] - half_height),
        (mirror_center[0] + half_width + skew, mirror_center[1] - half_height),
        (mirror_center[0] + half_width - skew, mirror_center[1] + half_height),
        (mirror_center[0] - half_width - skew, mirror_center[1] + half_height),
    )
    mirror_polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in mirror_points)
    sun_end = project(v_scale(sun, 2.4))
    normal_end = project(v_scale(normal, 1.35))
    status = html.escape(str(sample["status"]))
    content = f"""
    <defs>
      <linearGradient id="mirror" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#eefaff"/><stop offset="1" stop-color="#91c6d8"/>
      </linearGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <g stroke="#23475d" stroke-width="1" opacity=".72">{''.join(grid_lines)}</g>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{target_point[0]:.1f}" y2="{target_point[1]:.1f}" stroke="#6f8798" stroke-width="5"/>
    <g stroke="#6d879c" stroke-width="5" fill="none">
      <line x1="{origin[0]-50:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+18:.1f}"/>
      <line x1="{origin[0]+50:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+18:.1f}"/>
      <line x1="{origin[0]:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+12:.1f}"/>
    </g>
    <polygon points="{mirror_polygon}" fill="url(#mirror)" stroke="#d9f4ff" stroke-width="3"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{sun_end[0]:.1f}" y2="{sun_end[1]:.1f}" stroke="#ffd93d" stroke-width="5" filter="url(#glow)"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{normal_end[0]:.1f}" y2="{normal_end[1]:.1f}" stroke="#ff9f43" stroke-width="4" stroke-dasharray="8 6"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{target_point[0]:.1f}" y2="{target_point[1]:.1f}" stroke="#7de3ef" stroke-width="3" stroke-dasharray="7 7"/>
    <g transform="translate({target_point[0]:.1f} {target_point[1]:.1f})">
      <rect x="-20" y="-68" width="40" height="136" rx="7" fill="#c28d32" stroke="#f5d776" stroke-width="3"/>
      <circle cx="0" cy="0" r="13" fill="#fff3bd" stroke="#fff" stroke-width="2"/>
    </g>
    <g transform="translate(28 28)">
      <rect width="265" height="82" rx="8" fill="#102638" stroke="#31536a"/>
      <text x="16" y="27" fill="#f4d35e" font-size="15" font-weight="700">GEMELO WEB · VISTA ISOMETRICA</text>
      <text x="16" y="52" fill="#d7e7f2" font-size="13">AZ {number(sample['az_deg'])}° · EL {number(sample['el_deg'])}°</text>
      <text x="16" y="72" fill="#75e6a4" font-size="12">{status}</text>
    </g>
    <g transform="translate(785 420)" font-size="12" font-weight="700">
      <line x1="0" y1="40" x2="75" y2="40" stroke="#ff6b6b" stroke-width="3"/><text x="82" y="44" fill="#ffb0b0">+X oeste</text>
      <line x1="0" y1="40" x2="-32" y2="5" stroke="#75e6a4" stroke-width="3"/><text x="-75" y="0" fill="#75e6a4">+Y sur</text>
      <line x1="0" y1="40" x2="0" y2="-35" stroke="#8ebcff" stroke-width="3"/><text x="8" y="4" fill="#8ebcff">+Z cenit</text>
    </g>
    """
    return svg_document(content, dark=True)


def v_scale(vector: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return vector[0] * scalar, vector[1] * scalar, vector[2] * scalar


def spot_svg(sample: dict[str, object], history: list[dict[str, object]], tolerance_mm: float) -> str:
    valid = bool(sample["spot_valid"])
    u_mm = float(sample["spot_u_mm"])
    v_mm = float(sample["spot_v_mm"])
    radial_mm = float(sample["spot_radial_mm"])
    finite_radius = radial_mm if math.isfinite(radial_mm) else 0.0
    half_range = max(100.0, tolerance_mm * 4.0, finite_radius * 1.20)
    left, top, size = 95.0, 58.0, 410.0
    center_x, center_y = left + size / 2.0, top + size / 2.0

    def map_point(u_value: float, v_value: float) -> tuple[float, float]:
        return (
            center_x + u_value / half_range * size / 2.0,
            center_y - v_value / half_range * size / 2.0,
        )

    trail_points: list[str] = []
    for item in history[-100:]:
        if not bool(item.get("spot_valid", False)):
            continue
        item_u = float(item.get("spot_u_mm", 0.0))
        item_v = float(item.get("spot_v_mm", 0.0))
        if math.isfinite(item_u) and math.isfinite(item_v):
            x, y = map_point(item_u, item_v)
            trail_points.append(f"{x:.1f},{y:.1f}")
    marker = ""
    if valid and math.isfinite(u_mm) and math.isfinite(v_mm):
        marker_x, marker_y = map_point(u_mm, v_mm)
        marker = (
            f'<circle cx="{marker_x:.1f}" cy="{marker_y:.1f}" r="10" fill="#ef4444" '
            'stroke="#ffffff" stroke-width="3"/><circle '
            f'cx="{marker_x:.1f}" cy="{marker_y:.1f}" r="19" fill="none" stroke="#ef4444" stroke-width="2"/>'
        )
    tolerance_px = tolerance_mm / half_range * size / 2.0
    grid = []
    for tick in range(-4, 5):
        position = left + (tick + 4) * size / 8.0
        grid.append(f'<line x1="{position:.1f}" y1="{top}" x2="{position:.1f}" y2="{top+size}"/>')
        position_y = top + (tick + 4) * size / 8.0
        grid.append(f'<line x1="{left}" y1="{position_y:.1f}" x2="{left+size}" y2="{position_y:.1f}"/>')
    trail = f'<polyline points="{" ".join(trail_points)}" fill="none" stroke="#60a5fa" stroke-width="2" opacity=".7"/>' if len(trail_points) > 1 else ""
    content = f"""
    <text x="34" y="32" fill="#102a43" font-size="22" font-weight="700">Pantalla / spot</text>
    <rect x="{left}" y="{top}" width="{size}" height="{size}" fill="#fffdf5" stroke="#8b6f2b" stroke-width="2"/>
    <g stroke="#d9cfb5" stroke-width="1">{''.join(grid)}</g>
    <line x1="{center_x}" y1="{top}" x2="{center_x}" y2="{top+size}" stroke="#6b5b35" stroke-width="2"/>
    <line x1="{left}" y1="{center_y}" x2="{left+size}" y2="{center_y}" stroke="#6b5b35" stroke-width="2"/>
    <circle cx="{center_x}" cy="{center_y}" r="{tolerance_px:.1f}" fill="none" stroke="#16a34a" stroke-width="3" stroke-dasharray="6 5"/>
    {trail}{marker}
    <text x="{center_x}" y="{top+size+34}" text-anchor="middle" fill="#334155" font-size="13">u [mm] · oeste positivo · rango ±{half_range:.1f}</text>
    <text x="34" y="{center_y}" transform="rotate(-90 34 {center_y})" text-anchor="middle" fill="#334155" font-size="13">v [mm] · cenit positivo</text>
    <g transform="translate(560 70)">
      <rect width="395" height="325" rx="14" fill="#ffffff" stroke="#cad5df"/>
      <text x="24" y="42" fill="#102a43" font-size="21" font-weight="700">Lectura actual</text>
      <text x="24" y="84" fill="#334155" font-size="16">Horizontal u</text><text x="365" y="84" text-anchor="end" fill="#0f4c5c" font-size="18" font-weight="700">{number(u_mm)} mm</text>
      <text x="24" y="120" fill="#334155" font-size="16">Vertical v</text><text x="365" y="120" text-anchor="end" fill="#0f4c5c" font-size="18" font-weight="700">{number(v_mm)} mm</text>
      <text x="24" y="156" fill="#334155" font-size="16">Error radial</text><text x="365" y="156" text-anchor="end" fill="#dc2626" font-size="18" font-weight="700">{number(radial_mm)} mm</text>
      <text x="24" y="192" fill="#334155" font-size="16">Tolerancia</text><text x="365" y="192" text-anchor="end" fill="#16834f" font-size="18" font-weight="700">{tolerance_mm:.2f} mm</text>
      <rect x="24" y="226" width="341" height="52" rx="8" fill="{'#16834f' if valid and radial_mm <= tolerance_mm else '#b42318'}"/>
      <text x="194" y="259" text-anchor="middle" fill="#ffffff" font-size="16" font-weight="700">{html.escape(str(sample['status']))}</text>
    </g>
    """
    return svg_document(content)


def solar_svg(sample: dict[str, object], path: list[tuple[float, float]]) -> str:
    left, top, width, height = 80.0, 70.0, 820.0, 365.0

    def map_point(azimuth: float, altitude: float) -> tuple[float, float]:
        return left + (azimuth + 180.0) / 360.0 * width, top + (90.0 - altitude) / 90.0 * height

    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (map_point(az, alt) for az, alt in path))
    current_x, current_y = map_point(float(sample["solar_azimuth_deg"]), float(sample["altitude_deg"]))
    grid: list[str] = []
    labels: list[str] = []
    for altitude in range(0, 91, 15):
        _x, y = map_point(-180.0, float(altitude))
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+width}" y2="{y:.1f}"/>')
        labels.append(f'<text x="{left-15}" y="{y+4:.1f}" text-anchor="end">{altitude}</text>')
    for azimuth in range(-180, 181, 45):
        x, _y = map_point(float(azimuth), 0.0)
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+height}"/>')
        labels.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle">{azimuth}</text>')
    content = f"""
    <text x="30" y="34" fill="#102a43" font-size="22" font-weight="700">Trayectoria solar del dia</text>
    <rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#ffffff" stroke="#cbd5e1"/>
    <g stroke="#e2e8f0">{''.join(grid)}</g>
    <g fill="#475569" font-size="12">{''.join(labels)}</g>
    <polyline points="{points}" fill="none" stroke="#d98b00" stroke-width="4"/>
    <line x1="{current_x:.1f}" y1="{top}" x2="{current_x:.1f}" y2="{top+height}" stroke="#ef4444" stroke-dasharray="5 5" opacity=".7"/>
    <line x1="{left}" y1="{current_y:.1f}" x2="{left+width}" y2="{current_y:.1f}" stroke="#ef4444" stroke-dasharray="5 5" opacity=".7"/>
    <circle cx="{current_x:.1f}" cy="{current_y:.1f}" r="8" fill="#ef4444" stroke="#fff" stroke-width="3"/>
    <text x="{left+width/2}" y="{top+height+52}" text-anchor="middle" fill="#334155" font-size="13">Acimut de laboratorio [deg]: este − · sur 0 · oeste +</text>
    <g transform="translate(625 18)"><rect width="305" height="42" rx="8" fill="#102638"/><text x="16" y="27" fill="#ffffff" font-size="13">Alt {number(sample['altitude_deg'])}° · Az {number(sample['solar_azimuth_deg'])}° · Zenit {number(sample['zenith_deg'])}°</text></g>
    """
    return svg_document(content)


def facets_svg(state: WebTwinState) -> str:
    if not state.facet_enabled:
        return svg_document(
            '<text x="500" y="245" text-anchor="middle" fill="#64748b" font-size="22" font-weight="700">Modelo de facetas desactivado</text>'
            '<text x="500" y="280" text-anchor="middle" fill="#94a3b8" font-size="14">Activalo en el panel izquierdo para generar el acomodo optimo.</text>'
        )
    layout = state.facet_layout()
    max_extent = max([abs(value) for _name, u, v in layout for value in (u, v)] + [state.facet_size_m])
    scale = 340.0 / max(0.1, 2.0 * max_extent + state.facet_size_m)
    shapes: list[str] = []
    for facet_id, u_m, v_m in layout:
        x = 350.0 + u_m * scale
        y = 260.0 - v_m * scale
        size = max(8.0, state.facet_size_m * scale)
        if state.facet_shape == "Circular":
            shape = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size/2:.1f}" />'
        elif state.facet_shape == "Hexagonal":
            points = []
            for index in range(6):
                angle = math.radians(60 * index + 30)
                points.append(f"{x + size/2 * math.cos(angle):.1f},{y + size/2 * math.sin(angle):.1f}")
            shape = f'<polygon points="{" ".join(points)}" />'
        else:
            shape = f'<rect x="{x-size/2:.1f}" y="{y-size/2:.1f}" width="{size:.1f}" height="{size:.1f}" rx="2" />'
        shapes.append(f'<g fill="#d8edf5" stroke="#178ca4" stroke-width="2">{shape}<text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle" fill="#102a43" stroke="none" font-size="11">{facet_id}</text></g>')
    content = f"""
    <text x="30" y="36" fill="#102a43" font-size="22" font-weight="700">Facetas / acomodo optimo</text>
    <rect x="70" y="70" width="560" height="390" rx="14" fill="#0f2636" stroke="#31536a"/>
    {''.join(shapes)}
    <g transform="translate(670 90)">
      <rect width="285" height="290" rx="14" fill="#ffffff" stroke="#cad5df"/>
      <text x="22" y="42" fill="#102a43" font-size="19" font-weight="700">Configuracion</text>
      <text x="22" y="84" fill="#475569" font-size="15">Forma</text><text x="255" y="84" text-anchor="end" fill="#0f4c5c" font-size="16" font-weight="700">{state.facet_shape}</text>
      <text x="22" y="122" fill="#475569" font-size="15">Cantidad</text><text x="255" y="122" text-anchor="end" fill="#0f4c5c" font-size="16" font-weight="700">{len(layout)}</text>
      <text x="22" y="160" fill="#475569" font-size="15">Tamano</text><text x="255" y="160" text-anchor="end" fill="#0f4c5c" font-size="16" font-weight="700">{state.facet_size_m:.3f} m</text>
      <text x="22" y="198" fill="#475569" font-size="15">Separacion</text><text x="255" y="198" text-anchor="end" fill="#0f4c5c" font-size="16" font-weight="700">{state.facet_gap_m:.3f} m</text>
      <text x="22" y="236" fill="#475569" font-size="15">Distancia focal</text><text x="255" y="236" text-anchor="end" fill="#0f4c5c" font-size="16" font-weight="700">{state.facet_focal_distance_m:.3f} m</text>
    </g>
    """
    return svg_document(content)


def control_section(title: str, *children: object, opened: bool = False) -> object:
    attributes = {"class": "control-section"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(title),
        ui.div(*children, class_="control-section-body"),
        **attributes,
    )


def twin_3d_panel() -> object:
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.button("Isometrica", type="button", class_="view-button active", **{"data-twin-view": "iso"}),
                ui.tags.button("Frontal", type="button", class_="view-button", **{"data-twin-view": "front"}),
                ui.tags.button("Lateral", type="button", class_="view-button", **{"data-twin-view": "side"}),
                ui.tags.button("Superior", type="button", class_="view-button", **{"data-twin-view": "top"}),
                class_="camera-toolbar",
            ),
            ui.div(
                ui.strong("Camara libre"),
                ui.span("Click izquierdo: desplazar · Click derecho: girar · Rueda: zoom"),
                class_="camera-help",
            ),
            class_="twin-toolbar",
        ),
        ui.div(
            ui.tags.canvas(id="twin3d-canvas", **{"aria-label": "Gemelo tridimensional interactivo del heliostato"}),
            ui.div("Preparando escena 3D...", id="twin3d-status", class_="twin-status"),
            ui.div(
                ui.strong("Orientacion local"),
                ui.span("X rojo: oeste · Z verde: sur · Y azul: cenit"),
                class_="orientation-card",
            ),
            ui.div("", id="twin3d-warning", class_="twin-warning", hidden=True),
            class_="twin-stage",
        ),
        ui.div(ui.output_ui("scene_state"), class_="scene-state-host", **{"aria-hidden": "true"}),
        class_="twin-panel",
    )


def drift_panel() -> object:
    return ui.div(
        ui.div(
            ui.output_ui("correction_readout"),
            ui.input_action_button(
                "correct_now",
                "CORREGIR DESDE IMPACTO",
                class_="correction-action",
            ),
            class_="drift-toolbar",
        ),
        ui.output_ui("drift_chart"),
        class_="drift-panel",
    )


def drift_svg(state: WebTwinState) -> str:
    samples = (state.history or [state.snapshot()])[-180:]
    width, height = 1000, 520
    left, right = 78.0, 966.0
    panels = ((65.0, 225.0, "Error angular respecto al objetivo [deg]"), (300.0, 460.0, "Error radial del spot [mm]"))

    def finite(value: object) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return result if math.isfinite(result) else 0.0

    angular = [math.hypot(finite(item.get("az_error_deg")), finite(item.get("el_error_deg"))) for item in samples]
    radial = [finite(item.get("spot_radial_mm")) for item in samples]

    def plot(values: list[float], top: float, bottom: float, color: str) -> tuple[str, float]:
        maximum = max(max(values, default=0.0), 0.001)
        points = []
        denominator = max(1, len(values) - 1)
        for index, value in enumerate(values):
            x = left + (right - left) * index / denominator
            y = bottom - (bottom - top) * max(0.0, value) / maximum
            points.append(f"{x:.1f},{y:.1f}")
        return " ".join(points), maximum

    angular_points, angular_max = plot(angular, panels[0][0], panels[0][1], "#178ca4")
    radial_points, radial_max = plot(radial, panels[1][0], panels[1][1], "#c43131")
    content: list[str] = [
        '<rect width="1000" height="520" fill="#f8fafc"/>',
        '<text x="28" y="34" fill="#102a43" font-size="20" font-weight="700">Deriva temporal y correccion observada</text>',
    ]
    for (top, bottom, label), maximum, points, color in zip(
        panels,
        (angular_max, radial_max),
        (angular_points, radial_points),
        ("#178ca4", "#c43131"),
    ):
        content.extend(
            [
                f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="#ffffff" stroke="#cbd5df"/>',
                f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#64748b"/>',
                f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#64748b"/>',
                f'<text x="{left}" y="{top-10}" fill="#334155" font-size="14" font-weight="700">{label}</text>',
                f'<text x="{left-10}" y="{top+5}" text-anchor="end" fill="#64748b" font-size="12">{maximum:.3f}</text>',
                f'<text x="{left-10}" y="{bottom+4}" text-anchor="end" fill="#64748b" font-size="12">0</text>',
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>',
            ]
        )
    content.append(f'<text x="{(left+right)/2}" y="500" text-anchor="middle" fill="#64748b" font-size="13">Muestras en orden temporal · {len(samples)} visibles</text>')
    return svg_document("".join(content), width, height)


app_ui = ui.page_fluid(
    ui.head_content(
        ui.include_js(
            APP_DIR / "www" / "twin3d.js",
            method="inline",
            type="module",
        ),
    ),
    ui.include_css(APP_DIR / "www" / "styles.css"),
    ui.div(
        ui.div(
            ui.div("GEMELO DIGITAL", class_="eyebrow"),
            ui.h1("Mini horno solar · Web 0.2.4"),
            ui.p("Gemelo tridimensional y simulacion local en el navegador"),
            class_="brand-block",
        ),
        ui.output_ui("clock_card"),
        class_="topbar",
    ),
    ui.div(
        ui.tags.aside(
            control_section(
                "Modo de operacion",
                ui.input_radio_buttons(
                    "mode",
                    None,
                    choices=("Automatico", "Manual", "Home"),
                    selected="Automatico",
                    inline=True,
                ),
                ui.panel_conditional(
                    "input.mode === 'Automatico'",
                    ui.input_checkbox("tracking", "Seguimiento solar", True),
                    ui.p("El objetivo solar se actualiza continuamente mientras la sesion esta activa.", class_="field-help"),
                ),
                ui.panel_conditional(
                    "input.mode === 'Manual'",
                    ui.input_numeric("manual_step", "Paso objetivo [deg]", value=2.0, min=0.1, max=20.0, step=0.5),
                    ui.div(
                        ui.input_action_button("jog_east", "< ESTE", class_="jog-button"),
                        ui.input_action_button("stop_manual", "DETENER", class_="stop-button"),
                        ui.input_action_button("jog_west", "OESTE >", class_="jog-button"),
                        class_="jog-row",
                    ),
                    ui.div(
                        ui.input_action_button("jog_down", "< BAJAR", class_="jog-button"),
                        ui.input_action_button("jog_up", "SUBIR >", class_="jog-button"),
                        class_="jog-row two",
                    ),
                    ui.p("Los botones cambian el objetivo; los motores se desplazan gradualmente segun el PWM.", class_="field-help"),
                ),
                ui.panel_conditional(
                    "input.mode === 'Home'",
                    ui.p("Al iniciar, el heliostato regresara gradualmente a AZ 0° y EL 90°.", class_="field-help home-note"),
                ),
                opened=True,
            ),
            control_section(
                "Tiempo del experimento",
                ui.input_radio_buttons(
                    "time_mode",
                    None,
                    choices=("Tiempo real", "Fecha simulada"),
                    selected="Tiempo real",
                ),
                ui.input_date("sim_date", "Fecha simulada", value="2026-08-06"),
                ui.input_text("sim_time", "Hora", value="12:00:00"),
                ui.input_select("time_scale", "Velocidad", choices=("1", "10", "60", "120", "600"), selected="60"),
                ui.input_action_button("apply_time", "APLICAR FECHA Y HORA", class_="secondary-action full"),
                opened=True,
            ),
            control_section(
                "Calibracion y perfiles",
                ui.input_select(
                    "geometry_profile",
                    "Perfil geometrico",
                    choices=("Minihorno IER", "Diseno personalizado"),
                    selected="Minihorno IER",
                ),
                ui.input_action_button("load_profile", "CARGAR PERFIL SELECCIONADO", class_="profile-action full"),
                ui.h4("Ubicacion y objetivo"),
                ui.div(
                    ui.input_numeric("lat", "Latitud [deg]", value=MINIHORNO_WEB_PROFILE["lat_deg"], step=0.01),
                    ui.input_numeric("lon", "Longitud [deg]", value=MINIHORNO_WEB_PROFILE["lon_deg"], step=0.01),
                    class_="two-columns",
                ),
                ui.input_numeric("utc", "Zona UTC [h]", value=MINIHORNO_WEB_PROFILE["utc_offset_hours"], step=1),
                ui.div(
                    ui.input_numeric("rx", "RX [m]", value=MINIHORNO_WEB_PROFILE["rx"], step=0.01),
                    ui.input_numeric("ry", "RY [m]", value=MINIHORNO_WEB_PROFILE["ry"], step=0.01),
                    ui.input_numeric("rz", "RZ [m]", value=MINIHORNO_WEB_PROFILE["rz"], step=0.01),
                    class_="three-columns",
                ),
                ui.input_select("method", "Metodo solar", choices=("D&B", "REDA"), selected="D&B"),
                ui.h4("Heliostato"),
                ui.div(
                    ui.input_numeric("mirror_size", "Espejo lado [m]", value=MINIHORNO_WEB_PROFILE["mirror_size_m"], min=0.05, step=0.05),
                    ui.input_numeric("base_width", "Base ancho [m]", value=MINIHORNO_WEB_PROFILE["base_width_m"], min=0.10, step=0.05),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("fork_height", "Horquilla alto [m]", value=MINIHORNO_WEB_PROFILE["fork_height_m"], min=0.10, step=0.05),
                    ui.input_numeric("rail_length", "Riel largo [m]", value=MINIHORNO_WEB_PROFILE["rail_length_m"], min=0.10, step=0.05),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("receiver_screen", "Pantalla diam. [m]", value=MINIHORNO_WEB_PROFILE["receiver_screen_m"], min=0.03, step=0.05),
                    ui.input_numeric("target_tolerance", "Tolerancia [m]", value=MINIHORNO_WEB_PROFILE["target_tolerance_m"], min=0.0001, step=0.001),
                    class_="two-columns",
                ),
                ui.p("RX, RY y RZ se miden desde el centro optico del espejo.", class_="field-help"),
                opened=True,
            ),
            control_section(
                "Motores, errores y correccion",
                ui.input_slider("az_pwm", "PWM acimut", min=0, max=100, value=55, step=1, post=" %"),
                ui.input_slider("el_pwm", "PWM elevacion", min=0, max=100, value=55, step=1, post=" %"),
                ui.div(
                    ui.input_numeric("az_speed", "Vel. AZ [deg/s]", value=MINIHORNO_WEB_PROFILE["az_deg_per_second"], min=0.1, step=0.5),
                    ui.input_numeric("el_speed", "Vel. EL [deg/s]", value=MINIHORNO_WEB_PROFILE["el_deg_per_second"], min=0.1, step=0.5),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("az_offset", "Offset AZ [deg]", value=0.0, step=0.01),
                    ui.input_numeric("el_offset", "Offset EL [deg]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("drift_az", "Deriva AZ [deg/h]", value=0.0, step=0.01),
                    ui.input_numeric("drift_el", "Deriva EL [deg/h]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.input_slider("correction_gain", "Ganancia de correccion", min=0, max=100, value=50, step=5, post=" %"),
            ),
            control_section(
                "Facetas",
                ui.input_checkbox("facet_enabled", "Activar modelo", False),
                ui.input_select("facet_shape", "Forma", choices=("Cuadrada", "Circular", "Hexagonal"), selected="Cuadrada"),
                ui.div(
                    ui.input_numeric("facet_count", "Cantidad", value=9, min=1, max=200, step=1),
                    ui.input_numeric("facet_size", "Tamano [m]", value=0.30, min=0.001, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("facet_gap", "Separacion [m]", value=0.03, min=0, step=0.005),
                    ui.input_numeric("facet_focal", "Focal [m]", value=2.50, min=0.01, step=0.05),
                    class_="two-columns",
                ),
            ),
            class_="sidebar-panel",
        ),
        ui.tags.main(
            ui.div(
                ui.output_ui("operation_badge"),
                ui.div(
                    ui.input_action_button("toggle_run", "INICIAR SIMULACION", class_="primary-action"),
                    ui.input_action_button("reset", "VOLVER A CONFIGURAR", class_="secondary-action"),
                    ui.download_button("download_csv", "GUARDAR CSV", class_="secondary-action"),
                    class_="action-row",
                ),
                class_="operation-row",
            ),
            ui.div(
                ui.navset_card_tab(
                    ui.nav_panel("Gemelo 3D", twin_3d_panel()),
                    ui.nav_panel("Pantalla / spot", ui.output_ui("spot_view")),
                    ui.nav_panel("Trayectoria solar", ui.output_ui("solar_view")),
                    ui.nav_panel("Facetas", ui.output_ui("facet_view")),
                    ui.nav_panel("Deriva y correccion", drift_panel()),
                    ui.nav_panel("Diagnostico", ui.output_ui("diagnostic_view")),
                    id="main_view",
                ),
                class_="view-tabs",
            ),
            ui.output_ui("readout_strip"),
            class_="workspace-panel",
        ),
        class_="app-grid",
    ),
    title="Gemelo digital web",
)


def server(input, output, session) -> None:  # type: ignore[no-untyped-def]
    state = WebTwinState()
    revision = reactive.value(0)
    revision_counter = [0]

    def bump() -> None:
        revision_counter[0] += 1
        revision.set(revision_counter[0])

    @reactive.effect
    def sync_controls() -> None:
        selected_mode = str(input.mode())
        if selected_mode != state.mode and selected_mode == "Manual":
            state.stop_manual_motion()
        state.mode = selected_mode
        state.tracking = bool(input.tracking())
        state.time_mode = str(input.time_mode())
        state.time_scale = float(input.time_scale())
        state.lat_deg = float(input.lat())
        state.lon_deg = float(input.lon())
        state.utc_offset_hours = float(input.utc())
        state.rx = float(input.rx())
        state.ry = float(input.ry())
        state.rz = float(input.rz())
        state.mirror_size_m = float(input.mirror_size())
        state.base_width_m = float(input.base_width())
        state.fork_height_m = float(input.fork_height())
        state.rail_length_m = float(input.rail_length())
        state.receiver_screen_m = float(input.receiver_screen())
        state.target_tolerance_m = float(input.target_tolerance())
        state.method = str(input.method())
        state.az_pwm = float(input.az_pwm()) / 100.0
        state.el_pwm = float(input.el_pwm()) / 100.0
        state.az_deg_per_second = float(input.az_speed())
        state.el_deg_per_second = float(input.el_speed())
        state.az_offset_deg = float(input.az_offset())
        state.el_offset_deg = float(input.el_offset())
        state.drift_az_deg_per_hour = float(input.drift_az())
        state.drift_el_deg_per_hour = float(input.drift_el())
        state.correction_gain = float(input.correction_gain()) / 100.0
        state.facet_enabled = bool(input.facet_enabled())
        state.facet_shape = str(input.facet_shape())
        state.facet_count = int(input.facet_count())
        state.facet_size_m = float(input.facet_size())
        state.facet_gap_m = float(input.facet_gap())
        state.facet_focal_distance_m = float(input.facet_focal())
        bump()

    @reactive.effect
    @reactive.event(input.load_profile)
    def load_profile() -> None:
        if str(input.geometry_profile()) != "Minihorno IER":
            return
        profile = MINIHORNO_WEB_PROFILE
        updates = {
            "lat": "lat_deg",
            "lon": "lon_deg",
            "utc": "utc_offset_hours",
            "rx": "rx",
            "ry": "ry",
            "rz": "rz",
            "mirror_size": "mirror_size_m",
            "base_width": "base_width_m",
            "fork_height": "fork_height_m",
            "rail_length": "rail_length_m",
            "receiver_screen": "receiver_screen_m",
            "target_tolerance": "target_tolerance_m",
            "az_speed": "az_deg_per_second",
            "el_speed": "el_deg_per_second",
            "facet_count": "facet_count",
            "facet_size": "facet_size_m",
            "facet_gap": "facet_gap_m",
            "facet_focal": "facet_focal_distance_m",
        }
        for input_id, profile_name in updates.items():
            ui.update_numeric(input_id, value=profile[profile_name], session=session)
        ui.update_select("facet_shape", selected=str(profile["facet_shape"]), session=session)
        state.apply_profile(profile)
        bump()

    @reactive.effect
    @reactive.event(input.toggle_run)
    def toggle_run() -> None:
        state.pause_or_resume()
        bump()

    def manual_step() -> float:
        return max(0.1, float(input.manual_step()))

    @reactive.effect
    @reactive.event(input.jog_west)
    def jog_west() -> None:
        state.set_manual_target("az", 1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_east)
    def jog_east() -> None:
        state.set_manual_target("az", -1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_up)
    def jog_up() -> None:
        state.set_manual_target("el", 1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_down)
    def jog_down() -> None:
        state.set_manual_target("el", -1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.stop_manual)
    def stop_manual() -> None:
        state.stop_manual_motion()
        bump()

    @reactive.effect
    @reactive.event(input.correct_now)
    def correct_now() -> None:
        state.apply_observed_correction()
        bump()

    @reactive.effect
    @reactive.event(input.reset)
    def reset_state() -> None:
        state.reset()
        bump()

    @reactive.effect
    @reactive.event(input.apply_time)
    def apply_time() -> None:
        try:
            date_value = input.sim_date()
            date_text = date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value)
            state.apply_simulated_time(date_text, str(input.sim_time()))
        except ValueError:
            pass
        bump()

    @reactive.effect
    def simulation_clock() -> None:
        reactive.invalidate_later(0.15)
        state.step(0.15)
        bump()

    @output
    @render.ui
    def clock_card() -> object:
        revision.get()
        sample = state.snapshot()
        when = dt.datetime.fromisoformat(str(sample["timestamp"]))
        multiplier = f"{state.time_scale:g}x" if state.time_mode == "Fecha simulada" else "1x"
        return ui.div(
            ui.div("RELOJ DEL EXPERIMENTO", class_="clock-label"),
            ui.div(
                ui.span(when.strftime("%Y-%m-%d"), class_="clock-date"),
                ui.span(when.strftime("%H:%M:%S"), class_="clock-time"),
                class_="clock-value",
            ),
            ui.div(f"{state.time_mode.upper()} · UTC {state.utc_offset_hours:+g} · {multiplier}", class_="clock-mode"),
            class_="clock-card",
        )

    @reactive.effect
    def update_run_button() -> None:
        revision.get()
        if state.running:
            label = "PAUSAR"
        elif state.session_started:
            label = "REANUDAR"
        else:
            label = "INICIAR SIMULACION"
        ui.update_action_button("toggle_run", label=label, session=session)

    @output
    @render.ui
    def operation_badge() -> object:
        revision.get()
        sample = state.snapshot()
        return ui.div(
            ui.span(str(sample["status"]), class_=f"status-chip {sample['status_kind']}"),
            ui.span(
                f"Modo {state.mode} · AZ {number(sample['az_deg'])}° / {number(sample['az_target_deg'])}° · "
                f"EL {number(sample['el_deg'])}° / {number(sample['el_target_deg'])}°",
                class_="status-context",
            ),
            class_="status-block",
        )

    @output
    @render.ui
    def scene_state() -> object:
        current_revision = revision.get()
        sample = state.snapshot()
        sample["revision"] = current_revision
        sample["facets"] = state.facet_layout() if state.facet_enabled else []
        return ui.div(
            json.dumps(json_safe(sample), ensure_ascii=False, allow_nan=False),
            class_="twin-state-payload",
        )

    @output
    @render.ui
    def spot_view() -> object:
        revision.get()
        return ui.HTML(
            spot_svg(
                state.snapshot(),
                state.history,
                state.target_tolerance_m * 1000.0,
            )
        )

    @output
    @render.ui
    def solar_view() -> object:
        revision.get()
        return ui.HTML(solar_svg(state.snapshot(), state.solar_path()))

    @output
    @render.ui
    def facet_view() -> object:
        revision.get()
        return ui.HTML(facets_svg(state))

    @output
    @render.ui
    def correction_readout() -> object:
        revision.get()
        sample = state.snapshot()
        return ui.div(
            ui.strong("Correccion acumulada"),
            ui.span(
                f"AZ {number(sample['correction_az_deg'], 4)}° · "
                f"EL {number(sample['correction_el_deg'], 4)}°"
            ),
            class_="correction-readout",
        )

    @output
    @render.ui
    def drift_chart() -> object:
        revision.get()
        return ui.HTML(drift_svg(state))

    @output
    @render.ui
    def diagnostic_view() -> object:
        revision.get()
        sample = state.snapshot()
        diagnostics = (
            ("Error acimut", number(sample["az_error_deg"], 3), "deg"),
            ("Error elevacion", number(sample["el_error_deg"], 3), "deg"),
            ("Error spot", number(sample["spot_radial_mm"], 3), "mm"),
            ("Altura solar", number(sample["altitude_deg"], 3), "deg"),
            ("Incidencia", number(sample["incidence_deg"], 3), "deg"),
            ("Reflejado vs target", number(sample["target_difference_deg"], 4), "deg"),
            ("Correccion AZ", number(sample["correction_az_deg"], 4), "deg"),
            ("Correccion EL", number(sample["correction_el_deg"], 4), "deg"),
        )
        return ui.div(
            ui.h2("Diagnostico de seguimiento"),
            ui.div(
                *(
                    ui.div(
                        ui.div(label, class_="metric-label"),
                        ui.div(f"{value} {unit}", class_="metric-value"),
                        class_="metric-card",
                    )
                    for label, value, unit in diagnostics
                ),
                class_="diagnostic-grid",
            ),
            ui.div(
                ui.h3("Vectores geometricos"),
                ui.pre(
                    f"Sol S       {sample['sun']}\n"
                    f"Normal N    {sample['normal']}\n"
                    f"Reflejado   {sample['reflected']}\n"
                    f"Target R    {sample['target']}"
                ),
                class_="vector-card",
            ),
            class_="diagnostic-panel",
        )

    @output
    @render.ui
    def readout_strip() -> object:
        revision.get()
        sample = state.snapshot()
        values = (
            ("Acimut", f"{number(sample['az_deg'])}°"),
            ("Elevacion", f"{number(sample['el_deg'])}°"),
            ("Impacto u / v", f"{number(sample['spot_u_mm'])} / {number(sample['spot_v_mm'])} mm"),
            ("Error radial", f"{number(sample['spot_radial_mm'])} mm"),
            ("Sol", f"Alt {number(sample['altitude_deg'])}° · Az {number(sample['solar_azimuth_deg'])}°"),
            ("Muestras", str(len(state.history))),
        )
        return ui.div(
            *(ui.div(ui.span(label), ui.strong(value), class_="readout-item") for label, value in values),
            class_="readout-strip",
        )

    @output
    @render.download_button(filename=lambda: f"gemelo_web_{state.active_datetime():%Y%m%d_%H%M%S}.csv")
    def download_csv():  # type: ignore[no-untyped-def]
        yield state.export_csv_text()


app = App(app_ui, server, static_assets=APP_DIR / "www")
