"""Modelo ligero de concentrador facetado con un rayo central por faceta.

La convencion global es +x oeste, +y sur y +z cenit. El concentrador se
coloca alrededor del target actual y mira hacia un foco situado sobre el eje
optico, entre el concentrador y el heliostato.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


Vector3 = Tuple[float, float, float]


def add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def subtract(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def multiply(vector: Vector3, scalar: float) -> Vector3:
    return (vector[0] * scalar, vector[1] * scalar, vector[2] * scalar)


def dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(vector: Vector3) -> float:
    return math.sqrt(dot(vector, vector))


def unit(vector: Vector3) -> Vector3:
    magnitude = norm(vector)
    if magnitude < 1e-12:
        raise ValueError("No se puede normalizar un vector nulo")
    return multiply(vector, 1.0 / magnitude)


def reflect(direction: Vector3, normal: Vector3) -> Vector3:
    """Refleja una direccion de propagacion sobre una normal unitaria."""
    incoming = unit(direction)
    surface_normal = unit(normal)
    return unit(subtract(incoming, multiply(surface_normal, 2.0 * dot(incoming, surface_normal))))


def rotate_about_axis(vector: Vector3, axis: Vector3, angle_deg: float) -> Vector3:
    """Rota un vector con Rodrigues alrededor de ``axis``."""
    axis_unit = unit(axis)
    angle = math.radians(float(angle_deg))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return unit(
        add(
            add(multiply(vector, cosine), multiply(cross(axis_unit, vector), sine)),
            multiply(axis_unit, dot(axis_unit, vector) * (1.0 - cosine)),
        )
    )


def plane_basis(normal: Vector3) -> tuple[Vector3, Vector3]:
    """Crea ejes del receptor: u aproximadamente oeste y v aproximadamente cenit."""
    plane_normal = unit(normal)
    west = (1.0, 0.0, 0.0)
    u_raw = subtract(west, multiply(plane_normal, dot(west, plane_normal)))
    if norm(u_raw) < 1e-9:
        south = (0.0, 1.0, 0.0)
        u_raw = subtract(south, multiply(plane_normal, dot(south, plane_normal)))
    u_axis = unit(u_raw)
    v_axis = unit(cross(u_axis, plane_normal))
    if dot(v_axis, (0.0, 0.0, 1.0)) < 0.0:
        v_axis = multiply(v_axis, -1.0)
    return u_axis, v_axis


@dataclass
class Facet:
    """Una faceta cuadrada del concentrador."""

    id: str
    center: Vector3
    normal: Vector3
    size: float
    focal_distance: float | None = None
    aim_direction: Vector3 | None = None
    active: bool = True
    shape: str = "Cuadrada"
    layout_u_m: float = 0.0
    layout_v_m: float = 0.0
    incident_direction: Vector3 | None = None


@dataclass(frozen=True)
class FacetRayResult:
    """Resultado optico de un rayo central de una faceta activa."""

    facet_id: str
    facet_center: Vector3
    incident_direction: Vector3
    reflected_direction: Vector3
    impact_point: Vector3 | None
    impact_u_m: float
    impact_v_m: float
    focus_error_m: float


def ideal_facet_normal(
    heliostat_origin: Vector3,
    facet_center: Vector3,
    focus: Vector3,
) -> Vector3:
    """Normal que refleja el rayo heliostato-faceta exactamente al foco."""
    incoming = unit(subtract(facet_center, heliostat_origin))
    outgoing = unit(subtract(focus, facet_center))
    return normal_from_incident_and_aim(incoming, outgoing)


def normal_from_incident_and_aim(
    incident_direction: Vector3,
    aim_direction: Vector3,
) -> Vector3:
    """Normal que refleja una direccion incidente hacia una direccion deseada."""
    return unit(subtract(unit(incident_direction), unit(aim_direction)))


def intersect_receiver(
    ray_origin: Vector3,
    ray_direction: Vector3,
    receiver_center: Vector3,
    receiver_normal: Vector3,
) -> Vector3 | None:
    """Intersecta un rayo con el plano receptor; rechaza paralelos o cruces atras."""
    direction = unit(ray_direction)
    plane_normal = unit(receiver_normal)
    denominator = dot(direction, plane_normal)
    if abs(denominator) < 1e-12:
        return None
    ray_parameter = dot(subtract(receiver_center, ray_origin), plane_normal) / denominator
    if ray_parameter <= 1e-12:
        return None
    return add(ray_origin, multiply(direction, ray_parameter))


def trace_facet(
    facet: Facet,
    heliostat_origin: Vector3,
    receiver_center: Vector3,
    receiver_normal: Vector3,
) -> FacetRayResult | None:
    """Traza el rayo central de una faceta activa hasta el receptor."""
    if not facet.active:
        return None
    incident = (
        unit(facet.incident_direction)
        if facet.incident_direction is not None
        else unit(subtract(facet.center, heliostat_origin))
    )
    reflected = reflect(incident, facet.normal)
    impact = intersect_receiver(facet.center, reflected, receiver_center, receiver_normal)
    if impact is None:
        return FacetRayResult(
            facet_id=facet.id,
            facet_center=facet.center,
            incident_direction=incident,
            reflected_direction=reflected,
            impact_point=None,
            impact_u_m=float("nan"),
            impact_v_m=float("nan"),
            focus_error_m=float("inf"),
        )
    u_axis, v_axis = plane_basis(receiver_normal)
    error_vector = subtract(impact, receiver_center)
    impact_u = dot(error_vector, u_axis)
    impact_v = dot(error_vector, v_axis)
    return FacetRayResult(
        facet_id=facet.id,
        facet_center=facet.center,
        incident_direction=incident,
        reflected_direction=reflected,
        impact_point=impact,
        impact_u_m=impact_u,
        impact_v_m=impact_v,
        focus_error_m=math.hypot(impact_u, impact_v),
    )


def build_rectangular_facets(
    concentrator_center: Vector3,
    focus: Vector3,
    rows: int = 3,
    columns: int = 3,
    spacing_m: float = 0.035,
    size_m: float = 0.03,
    focal_distance_m: float | None = None,
    active_ids: set[str] | None = None,
    misaligned_facet_id: str = "",
    horizontal_misalignment_deg: float = 0.0,
    vertical_misalignment_deg: float = 0.0,
    heliostat_origin: Vector3 = (0.0, 0.0, 0.0),
) -> list[Facet]:
    """Construye una cuadricula pequena enfocada al mismo punto receptor."""
    rows = max(1, int(rows))
    columns = max(1, int(columns))
    spacing_m = max(1e-6, float(spacing_m))
    size_m = max(1e-6, float(size_m))
    optical_axis = unit(subtract(concentrator_center, heliostat_origin))
    horizontal_axis, vertical_axis = plane_basis(optical_axis)
    facets: list[Facet] = []
    shared_incident = unit(subtract(concentrator_center, heliostat_origin))
    index = 1
    for row in range(rows):
        vertical_offset = (row - (rows - 1) / 2.0) * spacing_m
        for column in range(columns):
            horizontal_offset = (column - (columns - 1) / 2.0) * spacing_m
            facet_id = f"F{index}"
            center = add(
                concentrator_center,
                add(
                    multiply(horizontal_axis, horizontal_offset),
                    multiply(vertical_axis, vertical_offset),
                ),
            )
            aim_direction = unit(subtract(focus, center))
            normal = normal_from_incident_and_aim(shared_incident, aim_direction)
            if facet_id == misaligned_facet_id:
                normal = rotate_about_axis(normal, vertical_axis, horizontal_misalignment_deg)
                normal = rotate_about_axis(normal, horizontal_axis, vertical_misalignment_deg)
            facets.append(
                Facet(
                    id=facet_id,
                    center=center,
                    normal=normal,
                    size=size_m,
                    focal_distance=focal_distance_m,
                    aim_direction=aim_direction,
                    active=active_ids is None or facet_id in active_ids,
                    shape="Cuadrada",
                    layout_u_m=horizontal_offset,
                    layout_v_m=vertical_offset,
                    incident_direction=shared_incident,
                )
            )
            index += 1
    return facets


def _balanced_square_offsets(count: int, pitch_m: float) -> list[tuple[float, float]]:
    """Distribuye cuadrados en filas compactas con la menor envolvente posible."""
    best_rows = 1
    best_score: tuple[float, int, float] | None = None
    for rows in range(1, count + 1):
        columns = math.ceil(count / rows)
        score = (max(rows, columns), rows * columns - count, abs(rows - columns))
        if best_score is None or score < best_score:
            best_score = score
            best_rows = rows
    base = count // best_rows
    remainder = count % best_rows
    row_counts = [base] * best_rows
    row_order = sorted(range(best_rows), key=lambda row: (abs(row - (best_rows - 1) / 2.0), row))
    for row in row_order[:remainder]:
        row_counts[row] += 1
    offsets: list[tuple[float, float]] = []
    for row, row_count in enumerate(row_counts):
        v_m = (row - (best_rows - 1) / 2.0) * pitch_m
        for column in range(row_count):
            u_m = (column - (row_count - 1) / 2.0) * pitch_m
            offsets.append((u_m, v_m))
    return _center_offsets(offsets)


def _center_offsets(offsets: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Centra exactamente el centroide geometrico de un conjunto de posiciones."""
    if not offsets:
        return []
    mean_u = sum(offset[0] for offset in offsets) / len(offsets)
    mean_v = sum(offset[1] for offset in offsets) / len(offsets)
    return [(u_m - mean_u, v_m - mean_v) for u_m, v_m in offsets]


def _compact_triangular_offsets(count: int, pitch_m: float) -> list[tuple[float, float]]:
    """Selecciona los puntos mas cercanos al centro de una reticula triangular."""
    limit = max(2, math.ceil(math.sqrt(count)) + 2)
    vertical_pitch = pitch_m * math.sqrt(3.0) / 2.0
    best_offsets: list[tuple[float, float]] = []
    best_score: tuple[float, float] | None = None
    for shift_u in (0.0, 0.5):
        for shift_v in (0.0, 0.5):
            candidates: list[tuple[float, float]] = []
            for row in range(-limit, limit + 1):
                row_offset = 0.5 if row % 2 else 0.0
                for column in range(-limit, limit + 1):
                    u_m = (column + row_offset + shift_u) * pitch_m
                    v_m = (row + shift_v) * vertical_pitch
                    candidates.append((u_m, v_m))
            candidates.sort(key=lambda offset: (offset[0] ** 2 + offset[1] ** 2, math.atan2(offset[1], offset[0])))
            selected = _center_offsets(candidates[:count])
            max_radius = max(math.hypot(u_m, v_m) for u_m, v_m in selected)
            width = max(u_m for u_m, _ in selected) - min(u_m for u_m, _ in selected)
            height = max(v_m for _, v_m in selected) - min(v_m for _, v_m in selected)
            score = (max_radius, width * height)
            if best_score is None or score < best_score:
                best_score = score
                best_offsets = selected
    return best_offsets


def optimal_facet_offsets(
    count: int,
    shape: str,
    size_m: float,
    gap_m: float = 0.0,
) -> list[tuple[float, float]]:
    """Calcula una distribucion compacta y centrada para forma y cantidad dadas."""
    count = max(1, int(count))
    size_m = max(1e-6, float(size_m))
    gap_m = max(0.0, float(gap_m))
    pitch_m = size_m + gap_m
    if shape == "Cuadrada":
        return _balanced_square_offsets(count, pitch_m)
    if shape in ("Circular", "Hexagonal"):
        return _compact_triangular_offsets(count, pitch_m)
    raise ValueError(f"Forma de faceta no soportada: {shape}")


def build_compact_facets(
    concentrator_center: Vector3,
    focus: Vector3,
    count: int,
    shape: str,
    size_m: float,
    gap_m: float = 0.0,
    focal_distance_m: float | None = None,
    active_ids: set[str] | None = None,
    misaligned_facet_id: str = "",
    horizontal_misalignment_deg: float = 0.0,
    vertical_misalignment_deg: float = 0.0,
    heliostat_origin: Vector3 = (0.0, 0.0, 0.0),
) -> list[Facet]:
    """Construye una cantidad arbitraria con empaquetamiento segun su forma."""
    optical_axis = unit(subtract(concentrator_center, heliostat_origin))
    horizontal_axis, vertical_axis = plane_basis(optical_axis)
    offsets = optimal_facet_offsets(count, shape, size_m, gap_m)
    facets: list[Facet] = []
    for index, (horizontal_offset, vertical_offset) in enumerate(offsets, start=1):
        facet_id = f"F{index}"
        center = add(
            concentrator_center,
            add(
                multiply(horizontal_axis, horizontal_offset),
                multiply(vertical_axis, vertical_offset),
            ),
        )
        aim_direction = unit(subtract(focus, center))
        normal = normal_from_incident_and_aim(optical_axis, aim_direction)
        if facet_id == misaligned_facet_id:
            normal = rotate_about_axis(normal, vertical_axis, horizontal_misalignment_deg)
            normal = rotate_about_axis(normal, horizontal_axis, vertical_misalignment_deg)
        facets.append(
            Facet(
                id=facet_id,
                center=center,
                normal=normal,
                size=max(1e-6, float(size_m)),
                focal_distance=focal_distance_m,
                aim_direction=aim_direction,
                active=active_ids is None or facet_id in active_ids,
                shape=shape,
                layout_u_m=horizontal_offset,
                layout_v_m=vertical_offset,
                incident_direction=optical_axis,
            )
        )
    return facets


def trace_facets(
    facets: list[Facet],
    heliostat_origin: Vector3,
    receiver_center: Vector3,
    receiver_normal: Vector3,
) -> list[FacetRayResult]:
    """Traza solo las facetas activas, eliminando las inactivas de la contribucion."""
    results: list[FacetRayResult] = []
    for facet in facets:
        result = trace_facet(facet, heliostat_origin, receiver_center, receiver_normal)
        if result is not None:
            results.append(result)
    return results
