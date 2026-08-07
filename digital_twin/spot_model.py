"""Pseudotrazado ligero del spot combinado producido por las facetas."""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    from digital_twin.facet_model import FacetRayResult, dot, plane_basis, unit
except ModuleNotFoundError:  # Permite ejecutar directamente run_digital_twin.py.
    from facet_model import FacetRayResult, dot, plane_basis, unit


@dataclass(frozen=True)
class SpotContribution:
    """Mancha gaussiana eliptica asociada al rayo central de una faceta."""

    facet_id: str
    center_u_m: float
    center_v_m: float
    sigma_minor_m: float
    sigma_major_m: float
    orientation_rad: float
    weight: float = 1.0


@dataclass(frozen=True)
class SpotMetrics:
    """Metricas energeticas y geometricas del mapa combinado."""

    centroid_u_m: float = 0.0
    centroid_v_m: float = 0.0
    centroid_error_m: float = 0.0
    maximum_intensity: float = 0.0
    total_intensity: float = 0.0
    equivalent_radius_m: float = 0.0
    equivalent_diameter_m: float = 0.0
    major_sigma_m: float = 0.0
    minor_sigma_m: float = 0.0
    orientation_deg: float = 0.0
    shape: str = "Sin spot"


@dataclass(frozen=True)
class SpotMapResult:
    """Cuadricula de intensidad y sus metricas calculadas."""

    resolution: int
    half_size_m: float
    u_coordinates_m: tuple[float, ...]
    v_coordinates_m: tuple[float, ...]
    intensity: tuple[float, ...]
    metrics: SpotMetrics
    normalization: str

    def value(self, row: int, column: int) -> float:
        return self.intensity[row * self.resolution + column]


def contribution_from_ray(
    result: FacetRayResult,
    receiver_normal: tuple[float, float, float],
    base_sigma_m: float,
    weight: float = 1.0,
) -> SpotContribution | None:
    """Convierte un impacto central en una elipse segun su incidencia."""
    if not (
        math.isfinite(result.impact_u_m)
        and math.isfinite(result.impact_v_m)
        and result.impact_point is not None
    ):
        return None
    direction = unit(result.reflected_direction)
    normal = unit(receiver_normal)
    cosine_incidence = max(0.15, min(1.0, abs(dot(direction, normal))))
    sigma_minor = max(1e-6, float(base_sigma_m))
    sigma_major = sigma_minor / cosine_incidence
    u_axis, v_axis = plane_basis(normal)
    projected_u = dot(direction, u_axis)
    projected_v = dot(direction, v_axis)
    orientation = (
        math.atan2(projected_v, projected_u)
        if math.hypot(projected_u, projected_v) > 1e-12
        else 0.0
    )
    return SpotContribution(
        facet_id=result.facet_id,
        center_u_m=result.impact_u_m,
        center_v_m=result.impact_v_m,
        sigma_minor_m=sigma_minor,
        sigma_major_m=sigma_major,
        orientation_rad=orientation,
        weight=max(0.0, float(weight)),
    )


def _normalized_resolution(resolution: int) -> int:
    bounded = max(21, min(int(resolution), 121))
    return bounded if bounded % 2 else bounded + 1


def _normalize_grid(values: list[float], mode: str) -> None:
    if not values:
        return
    if mode == "Total = 1":
        divisor = sum(values)
    elif mode == "Pico = 1":
        divisor = max(values, default=0.0)
    else:
        return
    if divisor > 1e-18:
        for index, value in enumerate(values):
            values[index] = value / divisor


def _metrics(
    values: list[float],
    u_coordinates: list[float],
    v_coordinates: list[float],
    resolution: int,
) -> SpotMetrics:
    total = sum(values)
    if total <= 1e-18:
        return SpotMetrics()
    centroid_u = 0.0
    centroid_v = 0.0
    for row, v_m in enumerate(v_coordinates):
        offset = row * resolution
        for column, u_m in enumerate(u_coordinates):
            intensity = values[offset + column]
            centroid_u += intensity * u_m
            centroid_v += intensity * v_m
    centroid_u /= total
    centroid_v /= total

    variance_u = 0.0
    variance_v = 0.0
    covariance = 0.0
    for row, v_m in enumerate(v_coordinates):
        dv = v_m - centroid_v
        offset = row * resolution
        for column, u_m in enumerate(u_coordinates):
            intensity = values[offset + column]
            du = u_m - centroid_u
            variance_u += intensity * du * du
            variance_v += intensity * dv * dv
            covariance += intensity * du * dv
    variance_u /= total
    variance_v /= total
    covariance /= total
    trace = variance_u + variance_v
    discriminant = math.sqrt(max(0.0, (variance_u - variance_v) ** 2 + 4.0 * covariance**2))
    major_variance = max(0.0, (trace + discriminant) / 2.0)
    minor_variance = max(0.0, (trace - discriminant) / 2.0)
    major_sigma = math.sqrt(major_variance)
    minor_sigma = math.sqrt(minor_variance)
    orientation = 0.5 * math.degrees(math.atan2(2.0 * covariance, variance_u - variance_v))
    equivalent_radius = math.sqrt(max(0.0, trace))
    ratio = major_sigma / max(1e-12, minor_sigma)
    if ratio < 1.10:
        shape = "Circular"
    elif ratio < 2.0:
        shape = "Eliptica"
    else:
        shape = "Alargada"
    return SpotMetrics(
        centroid_u_m=centroid_u,
        centroid_v_m=centroid_v,
        centroid_error_m=math.hypot(centroid_u, centroid_v),
        maximum_intensity=max(values),
        total_intensity=total,
        equivalent_radius_m=equivalent_radius,
        equivalent_diameter_m=2.0 * equivalent_radius,
        major_sigma_m=major_sigma,
        minor_sigma_m=minor_sigma,
        orientation_deg=orientation,
        shape=shape,
    )


def generate_spot_map(
    contributions: list[SpotContribution],
    half_size_m: float = 0.05,
    resolution: int = 51,
    normalization: str = "Total = 1",
) -> SpotMapResult:
    """Superpone manchas gaussianas evaluando solo hasta 3.5 sigma."""
    half_size = max(1e-4, float(half_size_m))
    grid_resolution = _normalized_resolution(resolution)
    step = 2.0 * half_size / (grid_resolution - 1)
    u_coordinates = [-half_size + index * step for index in range(grid_resolution)]
    v_coordinates = [-half_size + index * step for index in range(grid_resolution)]
    intensity = [0.0] * (grid_resolution * grid_resolution)

    for contribution in contributions:
        if contribution.weight <= 0.0:
            continue
        sigma_minor = max(1e-6, contribution.sigma_minor_m)
        sigma_major = max(sigma_minor, contribution.sigma_major_m)
        extent = 3.5 * sigma_major
        min_column = max(
            0,
            int(math.floor((contribution.center_u_m - extent + half_size) / step)),
        )
        max_column = min(
            grid_resolution - 1,
            int(math.ceil((contribution.center_u_m + extent + half_size) / step)),
        )
        min_row = max(
            0,
            int(math.floor((contribution.center_v_m - extent + half_size) / step)),
        )
        max_row = min(
            grid_resolution - 1,
            int(math.ceil((contribution.center_v_m + extent + half_size) / step)),
        )
        cosine = math.cos(contribution.orientation_rad)
        sine = math.sin(contribution.orientation_rad)
        inv_major_sq = 1.0 / (sigma_major * sigma_major)
        inv_minor_sq = 1.0 / (sigma_minor * sigma_minor)
        for row in range(min_row, max_row + 1):
            dv = v_coordinates[row] - contribution.center_v_m
            offset = row * grid_resolution
            for column in range(min_column, max_column + 1):
                du = u_coordinates[column] - contribution.center_u_m
                along_major = du * cosine + dv * sine
                along_minor = -du * sine + dv * cosine
                exponent = -0.5 * (
                    along_major * along_major * inv_major_sq
                    + along_minor * along_minor * inv_minor_sq
                )
                intensity[offset + column] += contribution.weight * math.exp(exponent)

    normalized_mode = (
        normalization
        if normalization in ("Total = 1", "Pico = 1", "Sin normalizar")
        else "Total = 1"
    )
    _normalize_grid(intensity, normalized_mode)
    metrics = _metrics(intensity, u_coordinates, v_coordinates, grid_resolution)
    return SpotMapResult(
        resolution=grid_resolution,
        half_size_m=half_size,
        u_coordinates_m=tuple(u_coordinates),
        v_coordinates_m=tuple(v_coordinates),
        intensity=tuple(intensity),
        metrics=metrics,
        normalization=normalized_mode,
    )
