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


def spot_heat_color(value: float, maximum: float) -> str:
    ratio = max(0.0, min(1.0, value / maximum if maximum > 1e-18 else 0.0))
    stops = (
        (0.00, (3, 7, 18)),
        (0.25, (20, 76, 124)),
        (0.50, (18, 160, 151)),
        (0.75, (250, 204, 21)),
        (1.00, (239, 68, 68)),
    )
    for index in range(len(stops) - 1):
        left, left_color = stops[index]
        right, right_color = stops[index + 1]
        if ratio <= right:
            fraction = (ratio - left) / max(1e-9, right - left)
            rgb = tuple(round(a + (b - a) * fraction) for a, b in zip(left_color, right_color))
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return "#ef4444"


def facet_shape_svg(x: float, y: float, radius: float, shape: str, fill: str) -> str:
    radius = max(3.0, min(13.0, radius))
    if shape == "Circular":
        body = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" />'
    elif shape == "Hexagonal":
        points = []
        for vertex in range(6):
            angle = math.radians(-90.0 + vertex * 60.0)
            points.append(f"{x + radius * math.cos(angle):.1f},{y + radius * math.sin(angle):.1f}")
        body = f'<polygon points="{" ".join(points)}" />'
    else:
        body = f'<rect x="{x-radius:.1f}" y="{y-radius:.1f}" width="{2*radius:.1f}" height="{2*radius:.1f}" rx="2" />'
    return f'<g fill="{fill}" stroke="#f8fafc" stroke-width="1.2">{body}</g>'


def facets_svg(
    state: WebTwinState,
    analysis: dict[str, object],
    view_mode: str,
    display_mode: str,
) -> str:
    if not state.facet_enabled:
        return svg_document(
            '<text x="500" y="230" text-anchor="middle" fill="#64748b" font-size="22" font-weight="700">Modelo de facetas desactivado</text>'
            '<text x="500" y="270" text-anchor="middle" fill="#94a3b8" font-size="14">Activa el modelo para calcular geometria, rayos, impactos e intensidad.</text>'
        )

    facets = list(analysis["facets"])
    results = list(analysis["results"])
    result_by_id = {result.facet_id: result for result in results}
    spot_map = analysis["spot_map"]
    metrics = analysis["spot_metrics"]
    active_count = sum(1 for facet in facets if facet.active)
    header = (
        f"{state.facet_shape} | activas {active_count}/{len(facets)} | "
        f"foco {state.facet_focal_distance_m:.3f} m | "
        f"error max {float(analysis['error_max_m']) * 1000.0:.3f} mm"
    )
    content = [
        '<text x="24" y="30" fill="#102a43" font-size="21" font-weight="700">Facetas: geometria, rayos, foco e intensidad</text>',
        f'<text x="24" y="54" fill="#475569" font-size="12" font-family="monospace">{header}</text>',
    ]

    schematic_box = (24.0, 72.0, 490.0, 342.0)
    receiver_box = (510.0, 72.0, 976.0, 342.0)
    if display_mode == "Esquema ampliado":
        schematic_box = (24.0, 72.0, 976.0, 500.0)
        receiver_box = (0.0, 0.0, 0.0, 0.0)
    elif display_mode == "Receptor ampliado":
        schematic_box = (0.0, 0.0, 0.0, 0.0)
        receiver_box = (24.0, 72.0, 976.0, 500.0)

    if schematic_box[2] > schematic_box[0]:
        x0, y0, x1, y1 = schematic_box
        content.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="10" fill="#0b1722" stroke="#31536a"/>')
        content.append(f'<text x="{x0+14}" y="{y0+24}" fill="#ffffff" font-size="13" font-weight="700">Esquema de rayos · {view_mode}</text>')
        focus = analysis["focus"]
        world_points = [(0.0, 0.0, 0.0), focus]
        world_points.extend(facet.center for facet in facets)
        world_points.extend(result.impact_point for result in results if result.impact_point is not None)

        if view_mode == "Resumen":
            center_y = (y0 + y1) / 2.0 + 8.0
            heliostat_x = x0 + 70.0
            concentrator_x = x1 - 64.0
            focus_x = heliostat_x + (concentrator_x - heliostat_x) * 0.64
            content.append(f'<polygon points="{heliostat_x-34},{center_y+8} {heliostat_x+34},{center_y-8} {heliostat_x+37},{center_y+2} {heliostat_x-31},{center_y+18}" fill="#b9dbea" stroke="#ffffff"/>')
            content.append(f'<line x1="{heliostat_x}" y1="{center_y+12}" x2="{heliostat_x}" y2="{center_y+72}" stroke="#7892a5" stroke-width="5"/>')
            for offset in (-22.0, 0.0, 22.0):
                content.append(f'<line x1="{heliostat_x-34}" y1="{center_y+offset}" x2="{heliostat_x+16}" y2="{center_y+offset}" stroke="#ffb454" stroke-width="2" marker-end="url(#arrow-orange)"/>')
            max_extent = max([max(abs(f.layout_u_m), abs(f.layout_v_m)) for f in facets] + [state.facet_size_m])
            layout_scale = min(130.0, (y1-y0-90.0) / max(0.01, 2.0 * max_extent))
            for facet in facets:
                fx = concentrator_x + facet.layout_u_m * layout_scale
                fy = center_y - facet.layout_v_m * layout_scale
                content.append(facet_shape_svg(fx, fy, state.facet_size_m * layout_scale * 0.43, facet.shape, "#d6b95f" if facet.active else "#5f6570"))
                if facet.active:
                    result = result_by_id.get(facet.id)
                    impact_offset = 0.0 if result is None or not math.isfinite(result.impact_v_m) else max(-55.0, min(55.0, result.impact_v_m * 1200.0))
                    content.append(f'<line x1="{fx:.1f}" y1="{fy:.1f}" x2="{focus_x:.1f}" y2="{center_y-impact_offset:.1f}" stroke="#66d9ef" stroke-width="1.2"/>')
            content.append(f'<line x1="{focus_x}" y1="{center_y-58}" x2="{focus_x}" y2="{center_y+58}" stroke="#58d6e7" stroke-width="2"/>')
            content.append(f'<text x="{heliostat_x}" y="{center_y+94}" text-anchor="middle" fill="#dbeafe" font-size="10">Heliostato móvil</text>')
            content.append(f'<text x="{focus_x}" y="{center_y-66}" text-anchor="middle" fill="#8ce8f2" font-size="10">Plano receptor / foco</text>')
        else:
            def raw_projection(point: tuple[float, float, float]) -> tuple[float, float]:
                px, py, pz = point
                if view_mode == "Superior X-Y":
                    return py, px
                if view_mode == "Lateral Y-Z":
                    return py, pz
                return px - 0.65 * py, pz - 0.25 * px - 0.22 * py

            projected = [raw_projection(point) for point in world_points]
            min_x = min(point[0] for point in projected)
            max_x = max(point[0] for point in projected)
            min_y = min(point[1] for point in projected)
            max_y = max(point[1] for point in projected)
            scale = min((x1-x0-70.0) / max(0.05, max_x-min_x), (y1-y0-70.0) / max(0.05, max_y-min_y))
            middle_x = (min_x + max_x) / 2.0
            middle_y = (min_y + max_y) / 2.0
            def project(point: tuple[float, float, float]) -> tuple[float, float]:
                raw_x, raw_y = raw_projection(point)
                return ((x0+x1)/2.0 + (raw_x-middle_x)*scale, (y0+y1)/2.0 - (raw_y-middle_y)*scale + 10.0)

            hx, hy = project((0.0, 0.0, 0.0))
            focus_x, focus_y = project(focus)
            content.append(f'<rect x="{hx-24}" y="{hy-8}" width="48" height="16" fill="#b9dbea" stroke="#ffffff" transform="rotate(-12 {hx} {hy})"/>')
            content.append(f'<line x1="{hx}" y1="{hy+7}" x2="{hx}" y2="{hy+38}" stroke="#7892a5" stroke-width="4"/>')
            for offset in (-14.0, 0.0, 14.0):
                content.append(f'<line x1="{hx-24}" y1="{hy+offset}" x2="{hx+20}" y2="{hy+offset}" stroke="#ffb454" stroke-width="2"/>')
            content.append(f'<circle cx="{focus_x}" cy="{focus_y}" r="6" fill="#58d6e7" stroke="#ffffff"/>')
            for facet in facets:
                fx, fy = project(facet.center)
                content.append(facet_shape_svg(fx, fy, facet.size * scale * 0.42, facet.shape, "#d6b95f" if facet.active else "#5f6570"))
                result = result_by_id.get(facet.id)
                if facet.active and result is not None:
                    endpoint = result.impact_point or focus
                    ex, ey = project(endpoint)
                    content.append(f'<line x1="{fx}" y1="{fy}" x2="{ex}" y2="{ey}" stroke="#66d9ef" stroke-width="1.1"/>')
            content.append(f'<text x="{x0+14}" y="{y1-14}" fill="#cbd5e1" font-size="10">n/facetas: dorado activo, gris inactivo · incidente naranja · reflejado cian</text>')

    if receiver_box[2] > receiver_box[0]:
        x0, y0, x1, y1 = receiver_box
        content.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="10" fill="#fffdf5" stroke="#8a7b58"/>')
        content.append(f'<text x="{x0+14}" y="{y0+24}" fill="#102a43" font-size="13" font-weight="700">Plano receptor / foco e intensidad</text>')
        map_size = min(y1-y0-68.0, (x1-x0)*0.58)
        left = x0 + 24.0
        top = y0 + 42.0
        center_x = left + map_size/2.0
        center_y = top + map_size/2.0
        half_range = spot_map.half_size_m if spot_map is not None else max(0.005, float(analysis["error_max_m"])*1.25)
        if spot_map is not None:
            display_resolution = min(31, spot_map.resolution)
            cell = map_size / display_resolution
            maximum = max(spot_map.intensity, default=0.0)
            for row in range(display_resolution):
                source_row = round(row * (spot_map.resolution-1) / max(1, display_resolution-1))
                for column in range(display_resolution):
                    source_column = round(column * (spot_map.resolution-1) / max(1, display_resolution-1))
                    value = spot_map.value(source_row, source_column)
                    draw_x = left + column*cell
                    draw_y = top + map_size - (row+1)*cell
                    content.append(f'<rect x="{draw_x:.1f}" y="{draw_y:.1f}" width="{cell+0.6:.1f}" height="{cell+0.6:.1f}" fill="{spot_heat_color(value, maximum)}"/>')
        else:
            content.append(f'<rect x="{left}" y="{top}" width="{map_size}" height="{map_size}" fill="#f8fafc"/>')
        content.append(f'<rect x="{left}" y="{top}" width="{map_size}" height="{map_size}" fill="none" stroke="#334155"/>')
        content.append(f'<line x1="{left}" y1="{center_y}" x2="{left+map_size}" y2="{center_y}" stroke="#a89b78"/>')
        content.append(f'<line x1="{center_x}" y1="{top}" x2="{center_x}" y2="{top+map_size}" stroke="#a89b78"/>')
        pixels_per_m = map_size / (2.0*half_range)
        for result in results:
            if not (math.isfinite(result.impact_u_m) and math.isfinite(result.impact_v_m)):
                continue
            px = max(left, min(left+map_size, center_x + result.impact_u_m*pixels_per_m))
            py = max(top, min(top+map_size, center_y - result.impact_v_m*pixels_per_m))
            content.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#ffffff" stroke="#b42318"/>')
            if len(facets) <= 18 or result.facet_id == state.facet_selected_id:
                content.append(f'<text x="{px+6:.1f}" y="{py-5:.1f}" fill="#b42318" font-size="8">{result.facet_id}</text>')
        details_x = left + map_size + 20.0
        if spot_map is None:
            detail_lines = ["Mapa desactivado", f"Impactos: {len(results)}", f"Rango: +/- {half_range*1000.0:.1f} mm"]
        else:
            detail_lines = [
                f"Activas: {active_count}/{len(facets)}",
                f"Centroide u: {metrics.centroid_u_m*1000.0:+.3f} mm",
                f"Centroide v: {metrics.centroid_v_m*1000.0:+.3f} mm",
                f"Error centroide: {metrics.centroid_error_m*1000.0:.3f} mm",
                f"Diametro eq.: {metrics.equivalent_diameter_m*1000.0:.3f} mm",
                f"Sigma mayor: {metrics.major_sigma_m*1000.0:.3f} mm",
                f"Sigma menor: {metrics.minor_sigma_m*1000.0:.3f} mm",
                f"Orientacion: {metrics.orientation_deg:+.2f} deg",
                f"Forma: {metrics.shape}",
                f"Normalizacion: {spot_map.normalization}",
            ]
        for index, line in enumerate(detail_lines):
            content.append(f'<text x="{details_x}" y="{top+18+index*20}" fill="#334155" font-size="10" font-family="monospace">{line}</text>')
        content.append(f'<text x="{center_x}" y="{top+map_size+18}" text-anchor="middle" fill="#475569" font-size="9">u [mm] oeste + · v [mm] cenit +</text>')

    if display_mode == "Vista general":
        table_y = 374.0
        content.append(f'<text x="24" y="{table_y}" fill="#102a43" font-size="13" font-weight="700">Resultados por faceta</text>')
        visible = facets[:18]
        for index, facet in enumerate(visible):
            column = index // 6
            row = index % 6
            x = 24.0 + column*320.0
            y = table_y + 24.0 + row*24.0
            result = result_by_id.get(facet.id)
            if not facet.active:
                detail, color = "INACTIVA · sin contribucion", "#64748b"
            elif result is None or not math.isfinite(result.focus_error_m):
                detail, color = "sin cruce con receptor", "#b42318"
            else:
                detail = f"u {result.impact_u_m*1000.0:+7.3f} | v {result.impact_v_m*1000.0:+7.3f} | err {result.focus_error_m*1000.0:7.3f} mm"
                color = "#16834f" if result.focus_error_m < 1e-6 else "#b42318"
            content.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="9" font-family="monospace">{facet.id}: {detail}</text>')
        if len(facets) > len(visible):
            content.append(f'<text x="976" y="{table_y}" text-anchor="end" fill="#64748b" font-size="9">Se muestran 18 de {len(facets)}; todos se calculan.</text>')

    defs = '<defs><marker id="arrow-orange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#ffb454"/></marker></defs>'
    return svg_document(defs + "".join(content), width=1000, height=540)


def control_section(title: str, *children: object, opened: bool = False) -> object:
    attributes = {"class": "control-section"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(title),
        ui.div(*children, class_="control-section-body"),
        **attributes,
    )


def manual_chapter(title: str, *children: object, opened: bool = False) -> object:
    attributes = {"class": "manual-chapter"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(title),
        ui.div(*children, class_="manual-chapter-body"),
        **attributes,
    )


def manual_panel() -> object:
    return ui.div(
        ui.div(
            ui.div("MANUAL DE USUARIO", class_="manual-kicker"),
            ui.h2("Gemelo digital del mini horno solar · edición web"),
            ui.p(
                "Guía completa de configuración, operación, interpretación y experimentos. "
                "Todos los cálculos se ejecutan localmente en el navegador; la aplicación no controla hardware físico.",
            ),
            class_="manual-hero",
        ),
        manual_chapter(
            "1. Inicio rápido",
            ui.tags.ol(
                ui.tags.li("Elige Tiempo real o Fecha simulada y configura el reloj."),
                ui.tags.li("Carga Minihorno IER o escribe las dimensiones de tu diseño."),
                ui.tags.li("Selecciona Automático, Manual o Home y ajusta motores, errores y facetas."),
                ui.tags.li("Pulsa INICIAR SIMULACIÓN. La configuración puede prepararse antes de iniciar."),
                ui.tags.li("Revisa las pestañas y guarda las muestras con GUARDAR CSV."),
            ),
            opened=True,
        ),
        manual_chapter(
            "2. Controles principales y estados",
            ui.p("INICIAR SIMULACIÓN comienza una sesión. PAUSAR congela reloj y movimiento. REANUDAR continúa la misma sesión. VOLVER A CONFIGURAR detiene la sesión, devuelve el heliostato a 0°/90° y conserva los valores escritos en los controles."),
            ui.p("Los estados principales son: listo para configurar, simulación pausada, moviendo al objetivo, en objetivo, Sol bajo el horizonte y sin impacto frontal. El estado y los objetivos AZ/EL aparecen siempre sobre las pestañas."),
        ),
        manual_chapter(
            "3. Tiempo real y fecha simulada",
            ui.p("Tiempo real usa la hora civil del equipo con el desfase UTC configurado. Fecha simulada usa el día y hora elegidos; APLICAR FECHA Y HORA fija el origen y la velocidad multiplica únicamente el avance del reloj solar."),
            ui.p("La posición solar usa latitud, longitud, desfase UTC y el método seleccionado. La simulación no comienza automáticamente al cambiar estos parámetros."),
        ),
        manual_chapter(
            "4. Modos de operación",
            ui.p("Automático calcula la normal ideal y mueve ambos ejes gradualmente hacia el objetivo cuando Seguimiento solar está activo. Manual modifica los objetivos con Oeste/Este y Bajar/Subir; el paso se expresa en grados. Home solicita un retorno gradual a AZ 0° y EL 90°."),
            ui.p("PWM multiplica la velocidad máxima de cada eje. Cambiar de modo nunca teletransporta el heliostato: parte desde la pose actual."),
        ),
        manual_chapter(
            "5. Calibración y perfiles",
            ui.p("Minihorno IER restaura ubicación, target, espejo, base, horquilla, riel, pantalla, tolerancia, límites, velocidades y geometría de facetas. Diseño propio permite conservar los valores escritos por el usuario."),
            ui.p("RX, RY y RZ son coordenadas en metros desde el centro óptico del espejo. X es oeste positivo, Y es sur positivo y Z es cenit positivo. Todas las dimensiones se interpretan directamente en metros, sin factores de escala ocultos."),
        ),
        manual_chapter(
            "6. Gemelo 3D",
            ui.p("Isométrica, Frontal, Lateral y Superior restablecen vistas fijas. En cámara libre, el clic izquierdo desplaza, el clic derecho gira y la rueda controla el zoom. La tarjeta de orientación muestra los ejes locales."),
            ui.p("El espejo, la base, el receptor, el riel y los vectores se actualizan con el estado. Si las facetas están activas, las activas aparecen doradas, las inactivas grises y los rayos centrales se dibujan hacia el plano receptor."),
        ),
        manual_chapter(
            "7. Pantalla / spot",
            ui.p("El plano receptor usa u horizontal, positivo hacia el oeste, y v vertical, positivo hacia el cenit. El círculo verde es la tolerancia. Error radial es la distancia entre el impacto calculado y el centro nominal."),
            ui.p("La ley utilizada es dr = di − 2(di · N)N. Después se intersecta el rayo con el plano que pasa por R. Si el cruce queda detrás del origen o el rayo es paralelo, el impacto se marca como no válido."),
        ),
        manual_chapter(
            "8. Trayectoria solar",
            ui.p("La gráfica recorre el día activo: X es acimut de laboratorio, donde este es negativo, sur es 0° y oeste es positivo; Y es altura solar entre 0° y 90°. El punto actual corresponde al reloj del experimento."),
        ),
        manual_chapter(
            "9. Facetas, rayos e intensidad",
            ui.p("Forma admite cuadrada, circular y hexagonal. Cantidad genera un acomodo compacto y centrado. Tamaño significa lado, diámetro o ancho entre caras, respectivamente. Separación agrega espacio libre y Focal fija la distancia del concentrador al plano receptor."),
            ui.p("Selecciona un ID como F5 para aplicarle desalineación horizontal o vertical. ACTIVAR/DESACTIVAR SELECCIONADA controla su contribución; TODAS ON/OFF opera sobre el conjunto completo."),
            ui.p("Resumen, Superior X-Y, Lateral Y-Z y 3D isométrica cambian la proyección del trazado. Vista general reúne esquema, receptor y tabla; los otros modos amplían un panel."),
            ui.p("El mapa suma manchas gaussianas por faceta. Sigma base controla su dispersión, Rango fija el plano visible, Resolución debe ser impar entre 21 y 121 y Normalización puede conservar el total, el pico o los valores sin normalizar. Centroide, diámetro equivalente, sigmas y orientación describen el spot combinado."),
        ),
        manual_chapter(
            "10. Deriva y corrección",
            ui.p("Offset aplica un error angular fijo; deriva crece en grados por hora del experimento. CORREGIR AHORA aproxima gradualmente la compensación al error observado según la ganancia. Una ganancia de 50 % elimina la mitad del error restante en cada pulsación."),
        ),
        manual_chapter(
            "11. Diagnóstico y exportación",
            ui.p("Diagnóstico muestra error AZ/EL, error del spot, altura solar, incidencia, diferencia reflejado-target, correcciones y vectores. GUARDAR CSV exporta el historial; si aún no hay muestras exporta la lectura actual."),
            ui.p("Para comparar experimentos cambia una familia de variables por vez y registra perfil, reloj, modo, errores, facetas, normalización y resolución."),
        ),
        manual_chapter(
            "12. Experimentos sugeridos",
            ui.tags.ul(
                ui.tags.li("Seguimiento nominal: Minihorno IER, fecha simulada al mediodía, Automático y sin errores."),
                ui.tags.li("Transitorio: parte desde una pose Manual, cambia a Automático y observa el movimiento gradual."),
                ui.tags.li("Deriva: aplica 0.2 deg/h, acelera el reloj y compara el error antes y después de varias correcciones."),
                ui.tags.li("Facetas: activa el mapa, desalinea F1, compara impactos y después desactiva F1."),
                ui.tags.li("Geometría propia: modifica target y dimensiones, revisa la escena 3D y exporta el resultado."),
            ),
        ),
        manual_chapter(
            "13. Solución de problemas y límites",
            ui.tags.ul(
                ui.tags.li("Sin movimiento: inicia la sesión, revisa el modo, el PWM y los límites configurados."),
                ui.tags.li("Sin spot: confirma que el Sol esté sobre el horizonte y que el rayo cruce frontalmente el receptor."),
                ui.tags.li("Sin mapa: activa modelo, mapa y al menos una faceta; aumenta el rango si los impactos quedan fuera."),
                ui.tags.li("Rendimiento lento: reduce cantidad de facetas o resolución del mapa."),
                ui.tags.li("La web es un simulador didáctico geométrico; no incluye sombras, clima, deformación térmica, potencia radiométrica absoluta ni control GPIO/serial."),
            ),
        ),
        class_="manual-panel",
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
            ui.h1("Mini horno solar · Web 0.3.0"),
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
                "Facetas: geometria, rayos e intensidad",
                ui.input_checkbox("facet_enabled", "Activar modelo", False),
                ui.input_checkbox("spot_map_enabled", "Activar mapa de intensidad", False),
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
                ui.hr(),
                ui.strong("Control por faceta"),
                ui.input_text("facet_selected", "ID seleccionada", value="F5", placeholder="Ej. F12"),
                ui.div(
                    ui.input_numeric("facet_misalign_h", "Desalineacion H [deg]", value=0.0, step=0.01),
                    ui.input_numeric("facet_misalign_v", "Desalineacion V [deg]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_action_button("facet_on", "ACTIVAR SELECCIONADA", class_="secondary-action facet-action"),
                    ui.input_action_button("facet_off", "DESACTIVAR SELECCIONADA", class_="secondary-action facet-action"),
                    class_="facet-action-grid",
                ),
                ui.div(
                    ui.input_action_button("facets_all_on", "TODAS ON", class_="secondary-action facet-action"),
                    ui.input_action_button("facets_all_off", "TODAS OFF", class_="secondary-action facet-action"),
                    class_="facet-action-grid",
                ),
                ui.hr(),
                ui.strong("Visualizacion y mapa"),
                ui.input_select(
                    "facet_view_mode",
                    "Vista de rayos",
                    choices=("Resumen", "Superior X-Y", "Lateral Y-Z", "3D isometrica"),
                    selected="Resumen",
                ),
                ui.input_select(
                    "facet_display_mode",
                    "Panel mostrado",
                    choices=("Vista general", "Esquema ampliado", "Receptor ampliado"),
                    selected="Vista general",
                ),
                ui.div(
                    ui.input_numeric("spot_sigma_mm", "Sigma base [mm]", value=3.0, min=0.01, step=0.1),
                    ui.input_numeric("spot_half_mm", "Rango +/- [mm]", value=50.0, min=1.0, step=1.0),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("spot_resolution", "Resolucion impar", value=51, min=21, max=121, step=2),
                    ui.input_select("spot_normalization", "Normalizacion", choices=("Total = 1", "Pico = 1", "Sin normalizar"), selected="Total = 1"),
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
                    ui.nav_panel("Manual", manual_panel()),
                    id="main_view",
                ),
                class_="view-tabs",
            ),
            ui.output_ui("readout_strip"),
            class_="workspace-panel",
        ),
        class_="app-grid",
    ),
    title="Gemelo digital del mini horno solar",
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
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.facet_horizontal_misalignment_deg = float(input.facet_misalign_h())
        state.facet_vertical_misalignment_deg = float(input.facet_misalign_v())
        state.spot_map_enabled = bool(input.spot_map_enabled())
        state.spot_base_sigma_m = float(input.spot_sigma_mm()) / 1000.0
        state.spot_map_half_size_m = float(input.spot_half_mm()) / 1000.0
        state.spot_map_resolution = int(input.spot_resolution())
        state.spot_normalization = str(input.spot_normalization())
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
        state.set_all_facets_active(True)
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
    @reactive.event(input.facet_on)
    def facet_on() -> None:
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.set_selected_facet_active(True)
        ui.update_text("facet_selected", value=state.facet_selected_id, session=session)
        bump()

    @reactive.effect
    @reactive.event(input.facet_off)
    def facet_off() -> None:
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.set_selected_facet_active(False)
        ui.update_text("facet_selected", value=state.facet_selected_id, session=session)
        bump()

    @reactive.effect
    @reactive.event(input.facets_all_on)
    def facets_all_on() -> None:
        state.set_all_facets_active(True)
        bump()

    @reactive.effect
    @reactive.event(input.facets_all_off)
    def facets_all_off() -> None:
        state.set_all_facets_active(False)
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
        analysis = state.facet_analysis()
        sample["facets"] = [
            [facet.id, facet.layout_u_m, facet.layout_v_m, facet.active]
            for facet in analysis["facets"]
        ]
        sample["facet_focus"] = analysis["focus"]
        sample["facet_rays"] = [
            [result.facet_id, result.facet_center, result.impact_point]
            for result in analysis["results"]
            if result.impact_point is not None
        ]
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
        return ui.HTML(
            facets_svg(
                state,
                state.facet_analysis(),
                str(input.facet_view_mode()),
                str(input.facet_display_mode()),
            )
        )

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
