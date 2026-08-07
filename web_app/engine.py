"""Nucleo ligero del gemelo digital para ejecucion en CPython y Pyodide.

No importa Tkinter ni accede al sistema de archivos. La interfaz web puede
ejecutarlo completamente dentro del navegador mediante Shinylive/Pyodide.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from digital_twin.facet_model import (
        build_compact_facets,
        dot as facet_dot,
        optimal_facet_offsets,
        trace_facets,
        unit as facet_unit,
    )
    from digital_twin.spot_model import (
        SpotMetrics,
        contribution_from_ray,
        generate_spot_map,
    )
    from digital_twin.error_model import ErrorConfig, ErrorModel, MotionErrorSample
    from digital_twin.correction_model import CorrectionConfig, CorrectionModel
except ModuleNotFoundError:
    # En desarrollo ``engine.py`` vive en web_app y los modelos son hermanos;
    # en el paquete Shinylive, ``digital_twin`` queda dentro del mismo folder.
    for candidate in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent):
        if (candidate / "digital_twin" / "facet_model.py").exists():
            sys.path.insert(0, str(candidate))
            break
    from digital_twin.facet_model import (
        build_compact_facets,
        dot as facet_dot,
        optimal_facet_offsets,
        trace_facets,
        unit as facet_unit,
    )
    from digital_twin.spot_model import (
        SpotMetrics,
        contribution_from_ray,
        generate_spot_map,
    )
    from digital_twin.error_model import ErrorConfig, ErrorModel, MotionErrorSample
    from digital_twin.correction_model import CorrectionConfig, CorrectionModel


TAU = 2.0 * math.pi
DEG = math.pi / 180.0
RAD = 180.0 / math.pi
WEB_APP_VERSION = "0.4.0"


MINIHORNO_WEB_PROFILE = {
    "lat_deg": 18.85,
    "lon_deg": -99.233333,
    "utc_offset_hours": -6.0,
    "rx": 0.0,
    "ry": 5.55,
    "rz": -0.40,
    "mirror_size_m": 2.0,
    "base_width_m": 1.90,
    "fork_height_m": 2.20,
    "rail_length_m": 5.50,
    "receiver_screen_m": 1.60,
    "target_tolerance_m": 0.010,
    "peralte_deg": 0.40,
    "cdr_deg": 0.07,
    "camera_offset_az_deg": 0.0,
    "camera_offset_el_deg": 0.0,
    "control_delay_s": 0.05,
    "az_limit_min": -95.0,
    "az_limit_max": 95.0,
    "el_limit_min": 0.0,
    "el_limit_max": 90.0,
    "az_deg_per_second": 9.0,
    "el_deg_per_second": 9.0,
    "az_counts_per_degree": 280.0,
    "el_counts_per_degree": 280.0,
    "facet_shape": "Cuadrada",
    "facet_count": 9,
    "facet_size_m": 0.30,
    "facet_gap_m": 0.03,
    "facet_focal_distance_m": 2.50,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_deg(angle: float) -> float:
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def v_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def v_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(v_dot(vector, vector))


def v_unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = v_norm(vector)
    if magnitude < 1e-12:
        raise ValueError("No se puede normalizar un vector nulo")
    return v_mul(vector, 1.0 / magnitude)


def angle_between(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.acos(clamp(v_dot(v_unit(a), v_unit(b)), -1.0, 1.0)) * RAD


def reflect_vector(
    incident_direction: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> tuple[float, float, float]:
    incident = v_unit(incident_direction)
    surface_normal = v_unit(normal)
    return v_unit(v_sub(incident, v_mul(surface_normal, 2.0 * v_dot(incident, surface_normal))))


def compute_heliostat_normal(
    sun_direction: tuple[float, float, float],
    target_direction: tuple[float, float, float],
) -> tuple[float, float, float]:
    return v_unit(v_add(v_unit(sun_direction), v_unit(target_direction)))


def normal_from_angles(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    azimuth = azimuth_deg * DEG
    elevation = elevation_deg * DEG
    return (
        math.cos(elevation) * math.sin(azimuth),
        math.cos(elevation) * math.cos(azimuth),
        math.sin(elevation),
    )


def angles_from_normal(normal: tuple[float, float, float]) -> tuple[float, float]:
    normal = v_unit(normal)
    return (
        wrap_deg(math.atan2(normal[0], normal[1]) * RAD),
        math.asin(clamp(normal[2], -1.0, 1.0)) * RAD,
    )


def solar_position_db(
    when: dt.datetime,
    lat_deg: float,
    lon_deg: float,
    utc_offset_hours: float,
    method: str = "D&B",
) -> tuple[float, float, float]:
    """Devuelve zenit, altura y acimut de laboratorio en grados."""
    day = when.timetuple().tm_yday
    civil_hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    b = TAU * (day - 81) / 364.0
    equation_of_time = 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    if method.upper() == "REDA":
        equation_of_time += 0.2 * math.sin(TAU * day / 365.0)
    standard_meridian = 15.0 * clamp(float(utc_offset_hours), -14.0, 14.0)
    solar_time = civil_hour + (4.0 * (lon_deg - standard_meridian) + equation_of_time) / 60.0
    hour_angle = 15.0 * (solar_time - 12.0) * DEG
    declination = 23.45 * DEG * math.sin(TAU * (284 + day) / 365.0)
    if method.upper() == "REDA":
        declination += 0.05 * DEG * math.cos(TAU * day / 365.0)
    latitude = lat_deg * DEG
    sin_altitude = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    altitude = math.asin(clamp(sin_altitude, -1.0, 1.0))
    east = -math.cos(declination) * math.sin(hour_angle)
    north = (
        math.cos(latitude) * math.sin(declination)
        - math.sin(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    azimuth = math.atan2(-east, -north) * RAD
    altitude_deg = altitude * RAD
    return 90.0 - altitude_deg, altitude_deg, wrap_deg(azimuth)


def target_frame(
    target: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    normal = v_unit(target)
    up = (0.0, 0.0, 1.0)
    u_axis = v_cross(normal, up)
    if v_norm(u_axis) < 1e-12:
        u_axis = (1.0, 0.0, 0.0)
    else:
        u_axis = v_unit(u_axis)
    v_axis = v_sub(up, v_mul(normal, v_dot(up, normal)))
    if v_norm(v_axis) < 1e-12:
        v_axis = v_cross(normal, u_axis)
    return normal, u_axis, v_unit(v_axis)


def target_impact(
    ray_direction: tuple[float, float, float],
    target: tuple[float, float, float],
) -> tuple[bool, float, float, float, float]:
    """Devuelve validez, u, v, radio y distancia de rayo, todo en metros."""
    direction = v_unit(ray_direction)
    plane_normal, u_axis, v_axis = target_frame(target)
    denominator = v_dot(direction, plane_normal)
    if abs(denominator) < 1e-12:
        return False, float("nan"), float("nan"), float("inf"), float("nan")
    distance = v_dot(target, plane_normal) / denominator
    if distance <= 0.0:
        return False, float("nan"), float("nan"), float("inf"), distance
    point = v_mul(direction, distance)
    relative = v_sub(point, target)
    u_m = v_dot(relative, u_axis)
    v_m = v_dot(relative, v_axis)
    return True, u_m, v_m, math.hypot(u_m, v_m), distance


def move_toward(current: float, target: float, maximum_step: float, wrap: bool = False) -> float:
    error = wrap_deg(target - current) if wrap else target - current
    if abs(error) <= maximum_step:
        return wrap_deg(target) if wrap else target
    result = current + math.copysign(maximum_step, error)
    return wrap_deg(result) if wrap else result


@dataclass
class WebTwinState:
    """Estado compartido por la interfaz Shiny y las salidas graficas."""

    lat_deg: float = MINIHORNO_WEB_PROFILE["lat_deg"]
    lon_deg: float = MINIHORNO_WEB_PROFILE["lon_deg"]
    utc_offset_hours: float = MINIHORNO_WEB_PROFILE["utc_offset_hours"]
    rx: float = MINIHORNO_WEB_PROFILE["rx"]
    ry: float = MINIHORNO_WEB_PROFILE["ry"]
    rz: float = MINIHORNO_WEB_PROFILE["rz"]
    receiver_screen_m: float = MINIHORNO_WEB_PROFILE["receiver_screen_m"]
    target_tolerance_m: float = MINIHORNO_WEB_PROFILE["target_tolerance_m"]
    mirror_size_m: float = MINIHORNO_WEB_PROFILE["mirror_size_m"]
    base_width_m: float = MINIHORNO_WEB_PROFILE["base_width_m"]
    fork_height_m: float = MINIHORNO_WEB_PROFILE["fork_height_m"]
    rail_length_m: float = MINIHORNO_WEB_PROFILE["rail_length_m"]
    az_deg_per_second: float = MINIHORNO_WEB_PROFILE["az_deg_per_second"]
    el_deg_per_second: float = MINIHORNO_WEB_PROFILE["el_deg_per_second"]
    az_limit_min: float = MINIHORNO_WEB_PROFILE["az_limit_min"]
    az_limit_max: float = MINIHORNO_WEB_PROFILE["az_limit_max"]
    el_limit_min: float = MINIHORNO_WEB_PROFILE["el_limit_min"]
    el_limit_max: float = MINIHORNO_WEB_PROFILE["el_limit_max"]
    peralte_deg: float = MINIHORNO_WEB_PROFILE["peralte_deg"]
    cdr_deg: float = MINIHORNO_WEB_PROFILE["cdr_deg"]
    camera_offset_az_deg: float = MINIHORNO_WEB_PROFILE["camera_offset_az_deg"]
    camera_offset_el_deg: float = MINIHORNO_WEB_PROFILE["camera_offset_el_deg"]
    control_delay_s: float = MINIHORNO_WEB_PROFILE["control_delay_s"]
    az_counts_per_degree: float = MINIHORNO_WEB_PROFILE["az_counts_per_degree"]
    el_counts_per_degree: float = MINIHORNO_WEB_PROFILE["el_counts_per_degree"]
    az_motor_on: bool = True
    el_motor_on: bool = True
    az_pwm: float = 0.55
    el_pwm: float = 0.55
    az_angle_deg: float = 0.0
    el_angle_deg: float = 90.0
    az_target_deg: float = 0.0
    el_target_deg: float = 90.0
    az_offset_deg: float = 0.0
    el_offset_deg: float = 0.0
    drift_az_deg_per_hour: float = 0.0
    drift_el_deg_per_hour: float = 0.0
    correction_az_deg: float = 0.0
    correction_el_deg: float = 0.0
    correction_gain: float = 0.50
    error_mode: str = "Corregido"
    error_config: ErrorConfig = field(default_factory=ErrorConfig)
    correction_config: CorrectionConfig = field(default_factory=CorrectionConfig)
    motion_error_sample: MotionErrorSample = field(default_factory=MotionErrorSample)
    correction_update_count: int = 0
    correction_pending: bool = False
    mode: str = "Automatico"
    tracking: bool = True
    tracking_update_interval_s: float = 1.0
    tracking_updates_manual: bool = False
    tracking_update_pending: bool = False
    tracking_schedule_initialized: bool = False
    seconds_since_tracking_update: float = 0.0
    tracking_update_count: int = 0
    tracking_error_max_m: float = 0.0
    tracking_error_average_m: float = 0.0
    tracking_error_rms_m: float = 0.0
    held_target_az_deg: float = 0.0
    held_target_el_deg: float = 90.0
    running: bool = False
    session_started: bool = False
    time_mode: str = "Tiempo real"
    simulated_time: dt.datetime = field(default_factory=lambda: dt.datetime(2026, 8, 6, 12, 0, 0))
    simulated_start: dt.datetime = field(default_factory=lambda: dt.datetime(2026, 8, 6, 12, 0, 0))
    time_scale: float = 60.0
    simulation_step_s: float = 60.0
    method: str = "D&B"
    facet_enabled: bool = False
    facet_shape: str = MINIHORNO_WEB_PROFILE["facet_shape"]
    facet_count: int = MINIHORNO_WEB_PROFILE["facet_count"]
    facet_size_m: float = MINIHORNO_WEB_PROFILE["facet_size_m"]
    facet_gap_m: float = MINIHORNO_WEB_PROFILE["facet_gap_m"]
    facet_focal_distance_m: float = MINIHORNO_WEB_PROFILE["facet_focal_distance_m"]
    facet_selected_id: str = "F5"
    facet_horizontal_misalignment_deg: float = 0.0
    facet_vertical_misalignment_deg: float = 0.0
    facet_active_ids: set[str] = field(
        default_factory=lambda: {f"F{index}" for index in range(1, 10)}
    )
    spot_map_enabled: bool = False
    spot_base_sigma_m: float = 0.003
    spot_map_half_size_m: float = 0.050
    spot_map_resolution: int = 51
    spot_normalization: str = "Total = 1"
    show_sun_vector: bool = True
    show_normal_vector: bool = True
    show_reflected_vector: bool = True
    show_target_direction: bool = True
    show_target_line: bool = True
    show_mechanical_guides: bool = False
    iterations: int = 0
    history: list[dict[str, object]] = field(default_factory=list)
    history_limit: int = 1200
    events: list[dict[str, str]] = field(default_factory=list)
    replay_active: bool = False
    replay_index: int = 0
    replay_rows: list[dict[str, object]] = field(default_factory=list, repr=False)
    _sample_accumulator_s: float = 0.0
    _elapsed_s: float = 0.0
    _interval_error_max_m: float = field(default=0.0, repr=False)
    _interval_error_sum_m: float = field(default=0.0, repr=False)
    _interval_error_sq_sum_m: float = field(default=0.0, repr=False)
    _interval_error_samples: int = field(default=0, repr=False)
    _last_tracking_state: bool = field(default=True, repr=False)
    _error_model: ErrorModel = field(init=False, repr=False)
    _correction_model: CorrectionModel = field(init=False, repr=False)
    _facet_previous_count: int = field(default=9, repr=False)
    _facet_cache_key: tuple[object, ...] | None = field(default=None, repr=False)
    _facet_cache: dict[str, object] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._error_model = ErrorModel(self.error_config)
        self._correction_model = CorrectionModel(self.correction_config)
        self.held_target_az_deg = self.az_target_deg
        self.held_target_el_deg = self.el_target_deg
        self.add_event("Sistema", "Gemelo web listo para configurar")

    def apply_profile(self, profile: dict[str, object]) -> None:
        """Aplica de forma segura un perfil geometrico compatible con la web."""
        numeric_fields = (
            "lat_deg",
            "lon_deg",
            "utc_offset_hours",
            "rx",
            "ry",
            "rz",
            "mirror_size_m",
            "base_width_m",
            "fork_height_m",
            "rail_length_m",
            "receiver_screen_m",
            "target_tolerance_m",
            "peralte_deg",
            "cdr_deg",
            "camera_offset_az_deg",
            "camera_offset_el_deg",
            "control_delay_s",
            "az_deg_per_second",
            "el_deg_per_second",
            "az_counts_per_degree",
            "el_counts_per_degree",
            "az_limit_min",
            "az_limit_max",
            "el_limit_min",
            "el_limit_max",
            "facet_count",
            "facet_size_m",
            "facet_gap_m",
            "facet_focal_distance_m",
        )
        for name in numeric_fields:
            if name in profile:
                setattr(self, name, type(getattr(self, name))(profile[name]))
        if "facet_shape" in profile:
            self.facet_shape = str(profile["facet_shape"])

    def set_manual_target(self, axis: str, direction: float, step_deg: float = 2.0) -> None:
        """Desplaza el objetivo manual sin teletransportar el heliostato."""
        amount = abs(float(step_deg)) * (1.0 if direction >= 0.0 else -1.0)
        if axis.lower() == "az":
            self.az_target_deg = clamp(
                self.az_target_deg + amount,
                self.az_limit_min,
                self.az_limit_max,
            )
            self.motion_error_sample = self._error_model.sample_motion(amount, 0.0)
        elif axis.lower() == "el":
            self.el_target_deg = clamp(
                self.el_target_deg + amount,
                self.el_limit_min,
                self.el_limit_max,
            )
            self.motion_error_sample = self._error_model.sample_motion(0.0, amount)
        else:
            raise ValueError(f"Eje manual desconocido: {axis}")

    def stop_manual_motion(self) -> None:
        self.az_target_deg = self.az_angle_deg
        self.el_target_deg = self.el_angle_deg

    def resample_motion_errors(self, az_delta_deg: float, el_delta_deg: float) -> None:
        self.motion_error_sample = self._error_model.sample_motion(az_delta_deg, el_delta_deg)

    def normalize_facet_selection(self) -> None:
        """Mantiene IDs validos al cambiar la cantidad de facetas."""
        previous_ids = set(self.facet_active_ids)
        previous_selected = self.facet_selected_id
        previous_count = self._facet_previous_count
        count = max(1, min(int(self.facet_count), 200))
        valid_ids = {f"F{index}" for index in range(1, count + 1)}
        if count > self._facet_previous_count:
            self.facet_active_ids.update(
                f"F{index}" for index in range(self._facet_previous_count + 1, count + 1)
            )
        self.facet_active_ids.intersection_update(valid_ids)
        selected = self.facet_selected_id.strip().upper()
        if selected not in valid_ids:
            selected = "F1"
        self.facet_selected_id = selected
        self._facet_previous_count = count
        if (
            previous_ids != self.facet_active_ids
            or previous_selected != self.facet_selected_id
            or previous_count != self._facet_previous_count
        ):
            self._facet_cache_key = None

    def set_selected_facet_active(self, active: bool) -> None:
        self.normalize_facet_selection()
        if active:
            self.facet_active_ids.add(self.facet_selected_id)
        else:
            self.facet_active_ids.discard(self.facet_selected_id)
        self._facet_cache_key = None

    def set_all_facets_active(self, active: bool) -> None:
        count = max(1, min(int(self.facet_count), 200))
        self.facet_active_ids = (
            {f"F{index}" for index in range(1, count + 1)} if active else set()
        )
        self._facet_previous_count = count
        self._facet_cache_key = None

    def add_event(self, category: str, message: str) -> None:
        """Registra una entrada breve y limitada de la bitacora operativa."""
        self.events.append(
            {
                "timestamp": self.active_datetime().isoformat(timespec="seconds"),
                "category": str(category),
                "message": str(message),
            }
        )
        if len(self.events) > 250:
            del self.events[:-250]

    def clear_events(self) -> None:
        self.events.clear()
        self.add_event("Sistema", "Bitacora limpiada")

    def configure_tracking_updates(self, value: str | float | None) -> None:
        """Configura actualizacion automatica o exclusivamente bajo orden."""
        manual = value is None or str(value).strip().lower() == "manual"
        interval = self.tracking_update_interval_s if manual else max(0.001, float(value))
        if manual != self.tracking_updates_manual or abs(interval - self.tracking_update_interval_s) > 1e-12:
            self.tracking_updates_manual = manual
            self.tracking_update_interval_s = interval
            self.reset_tracking_schedule()

    def reset_tracking_schedule(self) -> None:
        self.seconds_since_tracking_update = 0.0
        self.tracking_update_count = 0
        self.tracking_update_pending = False
        self.tracking_schedule_initialized = False
        self.held_target_az_deg = self.az_angle_deg
        self.held_target_el_deg = self.el_angle_deg
        self.tracking_error_max_m = 0.0
        self.tracking_error_average_m = 0.0
        self.tracking_error_rms_m = 0.0
        self._reset_interval_error_accumulators()

    def request_tracking_update(self) -> None:
        self.tracking_update_pending = True
        self.add_event("Seguimiento", "Actualizacion manual solicitada")

    def _reset_interval_error_accumulators(self) -> None:
        self._interval_error_max_m = 0.0
        self._interval_error_sum_m = 0.0
        self._interval_error_sq_sum_m = 0.0
        self._interval_error_samples = 0

    def _accumulate_tracking_error(self, error_m: float) -> None:
        if not math.isfinite(error_m):
            return
        value = max(0.0, error_m)
        self._interval_error_max_m = max(self._interval_error_max_m, value)
        self._interval_error_sum_m += value
        self._interval_error_sq_sum_m += value * value
        self._interval_error_samples += 1

    def _finish_tracking_interval(self) -> None:
        if self._interval_error_samples:
            count = self._interval_error_samples
            self.tracking_error_max_m = self._interval_error_max_m
            self.tracking_error_average_m = self._interval_error_sum_m / count
            self.tracking_error_rms_m = math.sqrt(self._interval_error_sq_sum_m / count)
        self._reset_interval_error_accumulators()

    def _apply_tracking_update(self, az_deg: float, el_deg: float) -> None:
        if self.tracking_schedule_initialized:
            self._finish_tracking_interval()
        self.held_target_az_deg = clamp(az_deg, self.az_limit_min, self.az_limit_max)
        self.held_target_el_deg = clamp(el_deg, self.el_limit_min, self.el_limit_max)
        self.motion_error_sample = self._error_model.sample_motion(
            wrap_deg(self.held_target_az_deg - self.az_angle_deg),
            self.held_target_el_deg - self.el_angle_deg,
        )
        self.seconds_since_tracking_update = 0.0
        self.tracking_update_count += 1
        self.tracking_update_pending = False
        self.tracking_schedule_initialized = True
        self.add_event(
            "Seguimiento",
            f"Objetivo actualizado a AZ {self.held_target_az_deg:.3f} deg, EL {self.held_target_el_deg:.3f} deg",
        )

    def reset_correction(self) -> None:
        self._correction_model.reset()
        self.correction_az_deg = 0.0
        self.correction_el_deg = 0.0
        self.correction_update_count = 0
        self.correction_pending = False
        self.add_event("Correccion", "Compensacion acumulada reiniciada")

    def _update_correction(self, simulated_elapsed_s: float, force: bool = False) -> None:
        geometry = self._solar_geometry()
        self.correction_config.image_gain_az = clamp(self.correction_gain, 0.0, 1.0)
        self.correction_config.image_gain_el = clamp(self.correction_gain, 0.0, 1.0)
        target = geometry["error_target"]
        az_deg, el_deg = self._correction_model.update(
            simulated_elapsed_s=max(0.0, simulated_elapsed_s),
            observed_u_m=float(geometry["corrected_spot_u_m"]),
            observed_v_m=float(geometry["corrected_spot_v_m"]),
            target_distance_m=v_norm(target),
            observation_trigger=False,
            force=force,
        )
        self.correction_az_deg = az_deg
        self.correction_el_deg = el_deg
        self.correction_update_count = self._correction_model.update_count
        if self._correction_model.corrected_this_step:
            self.add_event(
                "Correccion",
                f"{self.correction_config.strategy}: AZ {az_deg:+.4f} deg, EL {el_deg:+.4f} deg",
            )

    def apply_observed_correction(self) -> None:
        """Fuerza una observacion usando la estrategia actualmente elegida."""
        if self.correction_config.strategy == "Ninguna":
            self.correction_config.strategy = "Impacto observado"
        self.correction_config.enabled = True
        self._update_correction(0.0, force=True)

    def active_datetime(self) -> dt.datetime:
        if self.time_mode == "Fecha simulada":
            return self.simulated_time
        timezone = dt.timezone(dt.timedelta(hours=clamp(self.utc_offset_hours, -14.0, 14.0)))
        return dt.datetime.now(dt.timezone.utc).astimezone(timezone).replace(tzinfo=None)

    def apply_simulated_time(self, date_text: str, time_text: str) -> None:
        parsed = dt.datetime.fromisoformat(f"{date_text}T{time_text}")
        self.simulated_start = parsed
        self.simulated_time = parsed
        self.history.clear()
        self.iterations = 0
        self._elapsed_s = 0.0
        self.reset_tracking_schedule()
        self.reset_correction()
        self.add_event("Reloj", f"Fecha simulada aplicada: {parsed.isoformat(timespec='seconds')}")

    def step_simulated_time(self, seconds: float | None = None) -> float:
        if self.time_mode != "Fecha simulada" or self.running:
            return 0.0
        amount = max(0.0, float(self.simulation_step_s if seconds is None else seconds))
        self.simulated_time += dt.timedelta(seconds=amount)
        self._elapsed_s += amount
        self.add_event("Reloj", f"Avance manual de {amount:g} s")
        return amount

    def reset_simulated_time(self) -> None:
        self.simulated_time = self.simulated_start
        self._elapsed_s = 0.0
        self.history.clear()
        self.reset_tracking_schedule()
        self.reset_correction()
        self.add_event("Reloj", "Reloj simulado reiniciado")

    def start_replay(self) -> bool:
        if not self.history:
            self.add_event("Replay", "No hay muestras para reproducir")
            return False
        self.running = False
        self.replay_rows = [dict(row) for row in self.history]
        self.replay_index = 0
        self.replay_active = True
        self._sample_accumulator_s = 0.0
        self.add_event("Replay", f"Reproduccion iniciada con {len(self.replay_rows)} muestras")
        return True

    def stop_replay(self) -> None:
        if self.replay_active:
            self.replay_active = False
            self.replay_rows = []
            self.replay_index = 0
            self.add_event("Replay", "Regreso al estado vivo")

    def reset(self) -> None:
        self.stop_replay()
        self.running = False
        self.session_started = False
        self.az_angle_deg = 0.0
        self.el_angle_deg = 90.0
        self.az_target_deg = 0.0
        self.el_target_deg = 90.0
        self.simulated_time = self.simulated_start
        self.history.clear()
        self.iterations = 0
        self._elapsed_s = 0.0
        self.reset_tracking_schedule()
        self.reset_correction()
        self.add_event("Sistema", "Sesion restablecida para configurar")

    def start_or_toggle(self) -> None:
        self.session_started = True
        self.running = not self.running if self.session_started and self.running else True

    def pause_or_resume(self) -> None:
        if self.replay_active:
            self.stop_replay()
        if not self.session_started:
            self.session_started = True
        self.running = not self.running
        self.add_event("Sesion", "Simulacion en marcha" if self.running else "Simulacion pausada")

    def _solar_geometry(self) -> dict[str, object]:
        when = self.active_datetime()
        zenith, altitude, solar_azimuth = solar_position_db(
            when,
            self.lat_deg,
            self.lon_deg,
            self.utc_offset_hours,
            self.method,
        )
        altitude_rad = altitude * DEG
        azimuth_rad = solar_azimuth * DEG
        sun = (
            math.cos(altitude_rad) * math.sin(azimuth_rad),
            math.cos(altitude_rad) * math.cos(azimuth_rad),
            math.sin(altitude_rad),
        )
        nominal_target = (self.rx, self.ry, self.rz)
        nominal_target_direction = v_unit(nominal_target)
        ideal_normal = compute_heliostat_normal(sun, nominal_target_direction)
        ideal_az_optical, ideal_el_optical = angles_from_normal(ideal_normal)
        ideal_az = wrap_deg(ideal_az_optical + self.camera_offset_az_deg)
        ideal_el = ideal_el_optical + self.peralte_deg + self.camera_offset_el_deg
        elapsed_hours = self._elapsed_s / 3600.0
        drift_az = self.drift_az_deg_per_hour * elapsed_hours
        drift_el = self.drift_el_deg_per_hour * elapsed_hours

        def scenario(name: str) -> dict[str, object]:
            uses_errors = name != "Ideal"
            corrected = name == "Corregido"
            target = self._error_model.effective_target(nominal_target, uses_errors)
            command_az = self.az_angle_deg
            command_el = self.el_angle_deg - self.peralte_deg
            if uses_errors:
                command_az += drift_az
                command_el += drift_el
            if corrected:
                command_az += self.correction_az_deg
                command_el += self.correction_el_deg
            normal = self._error_model.normal_from_command(
                command_az,
                command_el,
                self.motion_error_sample,
                include_errors=uses_errors,
                corrected=False,
            )
            reflected = reflect_vector(v_mul(sun, -1.0), normal)
            valid, impact_u, impact_v, impact_radial, ray_distance = target_impact(reflected, target)
            target_direction = v_unit(target)
            return {
                "target": target,
                "target_direction": target_direction,
                "normal": normal,
                "reflected": reflected,
                "spot_valid": valid,
                "spot_u_m": impact_u,
                "spot_v_m": impact_v,
                "spot_radial_m": impact_radial,
                "ray_distance_m": ray_distance,
                "incidence_deg": angle_between(sun, normal),
                "reflection_deg": angle_between(reflected, normal),
                "target_difference_deg": angle_between(reflected, target_direction),
            }

        scenarios = {name: scenario(name) for name in ("Ideal", "Con error", "Corregido")}
        selected = scenarios.get(self.error_mode, scenarios["Corregido"])
        actual_normal = selected["normal"]
        reflected = selected["reflected"]
        target = selected["target"]
        target_direction = selected["target_direction"]
        valid = selected["spot_valid"]
        impact_u = selected["spot_u_m"]
        impact_v = selected["spot_v_m"]
        impact_radial = selected["spot_radial_m"]
        ray_distance = selected["ray_distance_m"]
        incidence = angle_between(sun, actual_normal)
        reflection = angle_between(reflected, actual_normal)
        target_difference = angle_between(reflected, target_direction)
        configured_az_error = (
            (self.error_config.azimuth_offset_deg if self.error_config.enable_azimuth_offset else 0.0)
            + (self.error_config.north_south_misalignment_deg if self.error_config.enable_north_south_misalignment else 0.0)
        )
        configured_el_error = (
            (self.error_config.elevation_offset_deg if self.error_config.enable_elevation_offset else 0.0)
            + (self.error_config.peralte_error_deg if self.error_config.enable_peralte_error else 0.0)
        )
        return {
            "when": when,
            "zenith_deg": zenith,
            "altitude_deg": altitude,
            "solar_azimuth_deg": solar_azimuth,
            "sun": sun,
            "target": target,
            "target_direction": target_direction,
            "ideal_normal": ideal_normal,
            "ideal_az_deg": ideal_az,
            "ideal_el_deg": ideal_el,
            "actual_normal": actual_normal,
            "reflected": reflected,
            "spot_valid": valid,
            "spot_u_m": impact_u,
            "spot_v_m": impact_v,
            "spot_radial_m": impact_radial,
            "ray_distance_m": ray_distance,
            "incidence_deg": incidence,
            "reflection_deg": reflection,
            "target_difference_deg": target_difference,
            "effective_az_error_deg": configured_az_error + drift_az,
            "effective_el_error_deg": configured_el_error + drift_el,
            "ideal_spot_u_m": scenarios["Ideal"]["spot_u_m"],
            "ideal_spot_v_m": scenarios["Ideal"]["spot_v_m"],
            "ideal_spot_radial_m": scenarios["Ideal"]["spot_radial_m"],
            "error_spot_u_m": scenarios["Con error"]["spot_u_m"],
            "error_spot_v_m": scenarios["Con error"]["spot_v_m"],
            "error_spot_radial_m": scenarios["Con error"]["spot_radial_m"],
            "corrected_spot_u_m": scenarios["Corregido"]["spot_u_m"],
            "corrected_spot_v_m": scenarios["Corregido"]["spot_v_m"],
            "corrected_spot_radial_m": scenarios["Corregido"]["spot_radial_m"],
            "error_target": scenarios["Con error"]["target"],
        }

    def step(self, wall_dt_s: float) -> None:
        wall_dt_s = clamp(float(wall_dt_s), 0.0, 1.0)
        if self.replay_active:
            self._sample_accumulator_s += wall_dt_s
            if self.replay_rows and self._sample_accumulator_s >= 0.65:
                self._sample_accumulator_s = 0.0
                self.replay_index = (self.replay_index + 1) % len(self.replay_rows)
            return
        if not self.running:
            return
        solar_elapsed_s = wall_dt_s * (max(0.0, self.time_scale) if self.time_mode == "Fecha simulada" else 1.0)
        if self.time_mode == "Fecha simulada":
            self.simulated_time += dt.timedelta(seconds=solar_elapsed_s)
        self._elapsed_s += solar_elapsed_s
        geometry = self._solar_geometry()
        if self.mode == "Automatico" and self.tracking:
            if not self._last_tracking_state:
                self.reset_tracking_schedule()
            if self.tracking_schedule_initialized:
                self.seconds_since_tracking_update += solar_elapsed_s
                self._accumulate_tracking_error(float(geometry["corrected_spot_radial_m"]))
            interval_due = (
                not self.tracking_updates_manual
                and self.seconds_since_tracking_update + 1e-9 >= self.tracking_update_interval_s
            )
            if not self.tracking_schedule_initialized or self.tracking_update_pending or interval_due:
                self._apply_tracking_update(
                    float(geometry["ideal_az_deg"]),
                    float(geometry["ideal_el_deg"]),
                )
            self.az_target_deg = self.held_target_az_deg
            self.el_target_deg = self.held_target_el_deg
        elif self.mode == "Automatico" and self._last_tracking_state and not self.tracking:
            self.stop_manual_motion()
        elif self.mode == "Home":
            self.az_target_deg = 0.0
            self.el_target_deg = 90.0
        self._last_tracking_state = self.tracking
        self.az_target_deg = clamp(self.az_target_deg, self.az_limit_min, self.az_limit_max)
        self.el_target_deg = clamp(self.el_target_deg, self.el_limit_min, self.el_limit_max)
        if self.az_motor_on and abs(wrap_deg(self.az_target_deg - self.az_angle_deg)) > self.cdr_deg:
            self.az_angle_deg = move_toward(
                self.az_angle_deg,
                self.az_target_deg,
                self.az_deg_per_second * clamp(self.az_pwm, 0.0, 1.0) * wall_dt_s,
                wrap=True,
            )
        if self.el_motor_on and abs(self.el_target_deg - self.el_angle_deg) > self.cdr_deg:
            self.el_angle_deg = move_toward(
                self.el_angle_deg,
                self.el_target_deg,
                self.el_deg_per_second * clamp(self.el_pwm, 0.0, 1.0) * wall_dt_s,
            )
        self._update_correction(solar_elapsed_s)
        self.iterations += 1
        self._sample_accumulator_s += wall_dt_s
        if self._sample_accumulator_s >= 0.5:
            self._sample_accumulator_s = 0.0
            self.history.append(self.snapshot())
            if len(self.history) > max(2, min(int(self.history_limit), 20000)):
                del self.history[:-self.history_limit]

    def status(self, snapshot: dict[str, object] | None = None) -> tuple[str, str]:
        sample = snapshot or self.snapshot()
        if self.replay_active:
            return f"REPLAY {self.replay_index + 1}/{len(self.replay_rows)}", "paused"
        if not self.session_started:
            return "LISTO PARA CONFIGURAR", "config"
        if not self.running:
            return "SIMULACION PAUSADA", "paused"
        if float(sample["altitude_deg"]) <= 0.0:
            return "SOL BAJO HORIZONTE", "alert"
        if not bool(sample["spot_valid"]):
            return "SIN IMPACTO FRONTAL", "alert"
        if float(sample["spot_radial_mm"]) <= self.target_tolerance_m * 1000.0:
            return "EN OBJETIVO", "ok"
        return "MOVIENDO AL OBJETIVO", "moving"

    def snapshot(self) -> dict[str, object]:
        if self.replay_active and self.replay_rows:
            replay_sample = dict(self.replay_rows[self.replay_index])
            replay_sample["status"], replay_sample["status_kind"] = self.status(replay_sample)
            replay_sample["replay_active"] = True
            replay_sample["replay_index"] = self.replay_index
            return replay_sample
        geometry = self._solar_geometry()
        radial_m = float(geometry["spot_radial_m"])
        facet_analysis = self.facet_analysis()
        spot_metrics = facet_analysis["spot_metrics"]
        active_errors = list(self.error_config.active_error_names())
        if abs(self.drift_az_deg_per_hour) > 1e-12 or abs(self.drift_el_deg_per_hour) > 1e-12:
            active_errors.append("deriva temporal")
        result: dict[str, object] = {
            "simulator_version": WEB_APP_VERSION,
            "timestamp": geometry["when"].isoformat(timespec="seconds"),
            "time_mode": self.time_mode,
            "time_scale": self.time_scale,
            "simulation_step_s": self.simulation_step_s,
            "mode": self.mode,
            "tracking": self.tracking,
            "session_started": self.session_started,
            "running": self.running,
            "replay_active": False,
            "iterations": self.iterations,
            "history_limit": self.history_limit,
            "az_deg": self.az_angle_deg,
            "el_deg": self.el_angle_deg,
            "az_target_deg": self.az_target_deg,
            "el_target_deg": self.el_target_deg,
            "az_error_deg": wrap_deg(self.az_target_deg - self.az_angle_deg),
            "el_error_deg": self.el_target_deg - self.el_angle_deg,
            "spot_valid": geometry["spot_valid"],
            "spot_u_mm": float(geometry["spot_u_m"]) * 1000.0,
            "spot_v_mm": float(geometry["spot_v_m"]) * 1000.0,
            "spot_radial_mm": radial_m * 1000.0,
            "ray_distance_m": geometry["ray_distance_m"],
            "zenith_deg": geometry["zenith_deg"],
            "altitude_deg": geometry["altitude_deg"],
            "solar_azimuth_deg": geometry["solar_azimuth_deg"],
            "incidence_deg": geometry["incidence_deg"],
            "reflection_deg": geometry["reflection_deg"],
            "target_difference_deg": geometry["target_difference_deg"],
            "effective_az_error_deg": geometry["effective_az_error_deg"],
            "effective_el_error_deg": geometry["effective_el_error_deg"],
            "correction_az_deg": self.correction_az_deg,
            "correction_el_deg": self.correction_el_deg,
            "correction_enabled": self.correction_config.enabled,
            "correction_strategy": self.correction_config.strategy,
            "correction_update_count": self.correction_update_count,
            "correction_constant_az_deg": self.correction_config.constant_az_deg,
            "correction_constant_el_deg": self.correction_config.constant_el_deg,
            "correction_rate_az_deg_per_hour": self.correction_config.time_az_rate_deg_per_hour,
            "correction_rate_el_deg_per_hour": self.correction_config.time_el_rate_deg_per_hour,
            "correction_poly_az_c0": self.correction_config.polynomial_az_c0,
            "correction_poly_az_c1": self.correction_config.polynomial_az_c1,
            "correction_poly_az_c2": self.correction_config.polynomial_az_c2,
            "correction_poly_el_c0": self.correction_config.polynomial_el_c0,
            "correction_poly_el_c1": self.correction_config.polynomial_el_c1,
            "correction_poly_el_c2": self.correction_config.polynomial_el_c2,
            "correction_gain": self.correction_gain,
            "correction_max_step_deg": self.correction_config.image_max_step_deg,
            "correction_camera_interval_s": self.correction_config.camera_interval_s,
            "error_mode": self.error_mode,
            "active_errors": ", ".join(active_errors) if active_errors else "ninguno",
            "ideal_spot_u_mm": float(geometry["ideal_spot_u_m"]) * 1000.0,
            "ideal_spot_v_mm": float(geometry["ideal_spot_v_m"]) * 1000.0,
            "ideal_spot_radial_mm": float(geometry["ideal_spot_radial_m"]) * 1000.0,
            "error_spot_u_mm": float(geometry["error_spot_u_m"]) * 1000.0,
            "error_spot_v_mm": float(geometry["error_spot_v_m"]) * 1000.0,
            "error_spot_radial_mm": float(geometry["error_spot_radial_m"]) * 1000.0,
            "corrected_spot_u_mm": float(geometry["corrected_spot_u_m"]) * 1000.0,
            "corrected_spot_v_mm": float(geometry["corrected_spot_v_m"]) * 1000.0,
            "corrected_spot_radial_mm": float(geometry["corrected_spot_radial_m"]) * 1000.0,
            "tracking_update_interval_s": "manual" if self.tracking_updates_manual else self.tracking_update_interval_s,
            "seconds_since_tracking_update_s": self.seconds_since_tracking_update,
            "tracking_update_count": self.tracking_update_count,
            "tracking_error_max_mm": self.tracking_error_max_m * 1000.0,
            "tracking_error_average_mm": self.tracking_error_average_m * 1000.0,
            "tracking_error_rms_mm": self.tracking_error_rms_m * 1000.0,
            "sun": geometry["sun"],
            "normal": geometry["actual_normal"],
            "reflected": geometry["reflected"],
            "target": geometry["target"],
            "sun_x": geometry["sun"][0],
            "sun_y": geometry["sun"][1],
            "sun_z": geometry["sun"][2],
            "normal_x": geometry["actual_normal"][0],
            "normal_y": geometry["actual_normal"][1],
            "normal_z": geometry["actual_normal"][2],
            "reflected_x": geometry["reflected"][0],
            "reflected_y": geometry["reflected"][1],
            "reflected_z": geometry["reflected"][2],
            "target_x_m": geometry["target"][0],
            "target_y_m": geometry["target"][1],
            "target_z_m": geometry["target"][2],
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "utc_offset_hours": self.utc_offset_hours,
            "solar_method": self.method,
            "mirror_size_m": self.mirror_size_m,
            "base_width_m": self.base_width_m,
            "fork_height_m": self.fork_height_m,
            "rail_length_m": self.rail_length_m,
            "receiver_screen_m": self.receiver_screen_m,
            "target_tolerance_m": self.target_tolerance_m,
            "peralte_deg": self.peralte_deg,
            "cdr_deg": self.cdr_deg,
            "camera_offset_az_deg": self.camera_offset_az_deg,
            "camera_offset_el_deg": self.camera_offset_el_deg,
            "control_delay_s": self.control_delay_s,
            "az_limit_min_deg": self.az_limit_min,
            "az_limit_max_deg": self.az_limit_max,
            "el_limit_min_deg": self.el_limit_min,
            "el_limit_max_deg": self.el_limit_max,
            "az_motor_on": self.az_motor_on,
            "el_motor_on": self.el_motor_on,
            "az_pwm": self.az_pwm,
            "el_pwm": self.el_pwm,
            "az_speed_deg_s": self.az_deg_per_second,
            "el_speed_deg_s": self.el_deg_per_second,
            "az_encoder_counts": round(self.az_angle_deg * self.az_counts_per_degree),
            "el_encoder_counts": round(self.el_angle_deg * self.el_counts_per_degree),
            "az_counts_per_degree": self.az_counts_per_degree,
            "el_counts_per_degree": self.el_counts_per_degree,
            "facet_enabled": self.facet_enabled,
            "facet_shape": self.facet_shape,
            "facet_count": self.facet_count,
            "facet_size_m": self.facet_size_m,
            "facet_gap_m": self.facet_gap_m,
            "facet_focal_distance_m": self.facet_focal_distance_m,
            "facet_selected_id": self.facet_selected_id,
            "facet_active_count": len(self.facet_active_ids),
            "facet_active_ids": ",".join(sorted(self.facet_active_ids)),
            "facet_misalignment_h_deg": self.facet_horizontal_misalignment_deg,
            "facet_misalignment_v_deg": self.facet_vertical_misalignment_deg,
            "spot_map_enabled": self.spot_map_enabled,
            "spot_map_resolution": self.spot_map_resolution,
            "spot_normalization": self.spot_normalization,
            "spot_base_sigma_m": self.spot_base_sigma_m,
            "spot_map_half_size_m": self.spot_map_half_size_m,
            "facet_error_max_mm": float(facet_analysis["error_max_m"]) * 1000.0,
            "facet_error_average_mm": float(facet_analysis["error_average_m"]) * 1000.0,
            "spot_centroid_u_mm": spot_metrics.centroid_u_m * 1000.0,
            "spot_centroid_v_mm": spot_metrics.centroid_v_m * 1000.0,
            "spot_centroid_error_mm": spot_metrics.centroid_error_m * 1000.0,
            "spot_maximum_intensity": spot_metrics.maximum_intensity,
            "spot_total_intensity": spot_metrics.total_intensity,
            "spot_equivalent_diameter_mm": spot_metrics.equivalent_diameter_m * 1000.0,
            "spot_shape": spot_metrics.shape,
            "show_sun_vector": self.show_sun_vector,
            "show_normal_vector": self.show_normal_vector,
            "show_reflected_vector": self.show_reflected_vector,
            "show_target_direction": self.show_target_direction,
            "show_target_line": self.show_target_line,
            "show_mechanical_guides": self.show_mechanical_guides,
            "error_enable_azimuth_offset": self.error_config.enable_azimuth_offset,
            "error_azimuth_offset_deg": self.error_config.azimuth_offset_deg,
            "error_enable_elevation_offset": self.error_config.enable_elevation_offset,
            "error_elevation_offset_deg": self.error_config.elevation_offset_deg,
            "error_enable_north_south": self.error_config.enable_north_south_misalignment,
            "error_north_south_deg": self.error_config.north_south_misalignment_deg,
            "error_enable_target_xyz": self.error_config.enable_target_position_error,
            "error_target_x_m": self.error_config.target_error_x_m,
            "error_target_y_m": self.error_config.target_error_y_m,
            "error_target_z_m": self.error_config.target_error_z_m,
            "error_enable_heliostat_xyz": self.error_config.enable_heliostat_position_error,
            "error_heliostat_x_m": self.error_config.heliostat_error_x_m,
            "error_heliostat_y_m": self.error_config.heliostat_error_y_m,
            "error_heliostat_z_m": self.error_config.heliostat_error_z_m,
            "error_enable_peralte": self.error_config.enable_peralte_error,
            "error_peralte_deg": self.error_config.peralte_error_deg,
            "error_enable_backlash": self.error_config.enable_backlash,
            "error_backlash_deg": self.error_config.backlash_deg,
            "error_enable_directional": self.error_config.enable_directional_error,
            "error_upward_deg": self.error_config.upward_error_deg,
            "error_downward_deg": self.error_config.downward_error_deg,
            "error_enable_noise": self.error_config.enable_random_noise,
            "error_noise_std_deg": self.error_config.random_noise_std_deg,
            "error_noise_seed": self.error_config.random_seed,
            "drift_az_deg_per_hour": self.drift_az_deg_per_hour,
            "drift_el_deg_per_hour": self.drift_el_deg_per_hour,
        }
        result["status"], result["status_kind"] = self.status(result)
        return result

    def solar_path(self, step_minutes: int = 10) -> list[tuple[float, float]]:
        when = self.active_datetime()
        midnight = when.replace(hour=0, minute=0, second=0, microsecond=0)
        points: list[tuple[float, float]] = []
        for minute in range(0, 24 * 60 + 1, max(1, int(step_minutes))):
            sample_time = midnight + dt.timedelta(minutes=minute)
            _zenith, altitude, azimuth = solar_position_db(
                sample_time,
                self.lat_deg,
                self.lon_deg,
                self.utc_offset_hours,
                self.method,
            )
            if altitude >= 0.0:
                points.append((azimuth, altitude))
        return points

    def facet_layout(self) -> list[tuple[str, float, float]]:
        offsets = optimal_facet_offsets(
            max(1, min(int(self.facet_count), 200)),
            self.facet_shape,
            max(0.001, self.facet_size_m),
            max(0.0, self.facet_gap_m),
        )
        return [(f"F{index}", u_m, v_m) for index, (u_m, v_m) in enumerate(offsets, 1)]

    def facet_analysis(self) -> dict[str, object]:
        """Calcula facetas, rayos centrales, impactos y mapa de intensidad."""
        self.normalize_facet_selection()
        if not self.facet_enabled:
            return {
                "facets": [],
                "results": [],
                "focus": (0.0, 0.0, 0.0),
                "receiver_normal": (0.0, 1.0, 0.0),
                "error_max_m": 0.0,
                "error_average_m": 0.0,
                "spot_map": None,
                "spot_metrics": SpotMetrics(),
            }

        count = max(1, min(int(self.facet_count), 200))
        resolution = max(21, min(int(self.spot_map_resolution), 121))
        if resolution % 2 == 0:
            resolution += 1
        target = tuple(float(value) for value in self._solar_geometry()["target"])
        cache_key: tuple[object, ...] = (
            target,
            self.facet_shape,
            count,
            float(self.facet_size_m),
            float(self.facet_gap_m),
            float(self.facet_focal_distance_m),
            tuple(sorted(self.facet_active_ids)),
            self.facet_selected_id,
            float(self.facet_horizontal_misalignment_deg),
            float(self.facet_vertical_misalignment_deg),
            self.spot_map_enabled,
            float(self.spot_base_sigma_m),
            float(self.spot_map_half_size_m),
            resolution,
            self.spot_normalization,
        )
        if cache_key == self._facet_cache_key and self._facet_cache is not None:
            return self._facet_cache

        if v_norm(target) < 1e-12:
            analysis = {
                "facets": [],
                "results": [],
                "focus": (0.0, 0.0, 0.0),
                "receiver_normal": (0.0, 1.0, 0.0),
                "error_max_m": float("nan"),
                "error_average_m": float("nan"),
                "spot_map": None,
                "spot_metrics": SpotMetrics(),
            }
            self._facet_cache_key = cache_key
            self._facet_cache = analysis
            return analysis
        axis = facet_unit(target)
        focal_distance = max(0.001, float(self.facet_focal_distance_m))
        focus = v_sub(target, v_mul(axis, focal_distance))
        facets = build_compact_facets(
            concentrator_center=target,
            focus=focus,
            count=count,
            shape=self.facet_shape,
            size_m=max(0.001, float(self.facet_size_m)),
            gap_m=max(0.0, float(self.facet_gap_m)),
            focal_distance_m=focal_distance,
            active_ids=set(self.facet_active_ids),
            misaligned_facet_id=self.facet_selected_id,
            horizontal_misalignment_deg=float(self.facet_horizontal_misalignment_deg),
            vertical_misalignment_deg=float(self.facet_vertical_misalignment_deg),
        )
        results = trace_facets(
            facets,
            heliostat_origin=(0.0, 0.0, 0.0),
            receiver_center=focus,
            receiver_normal=axis,
        )
        errors = [result.focus_error_m for result in results if math.isfinite(result.focus_error_m)]
        spot_map = None
        spot_metrics = SpotMetrics()
        if self.spot_map_enabled and results:
            facets_by_id = {facet.id: facet for facet in facets}
            contributions = []
            for result in results:
                facet = facets_by_id.get(result.facet_id)
                if facet is None:
                    continue
                if facet.shape == "Circular":
                    area_factor = math.pi / 4.0
                elif facet.shape == "Hexagonal":
                    area_factor = math.sqrt(3.0) / 2.0
                else:
                    area_factor = 1.0
                receiver_cosine = abs(
                    facet_dot(facet_unit(result.reflected_direction), axis)
                )
                contribution = contribution_from_ray(
                    result,
                    receiver_normal=axis,
                    base_sigma_m=max(1e-5, float(self.spot_base_sigma_m)),
                    weight=area_factor * receiver_cosine,
                )
                if contribution is not None:
                    contributions.append(contribution)
            spot_map = generate_spot_map(
                contributions,
                half_size_m=max(0.001, float(self.spot_map_half_size_m)),
                resolution=resolution,
                normalization=self.spot_normalization,
            )
            spot_metrics = spot_map.metrics

        analysis: dict[str, object] = {
            "facets": facets,
            "results": results,
            "focus": focus,
            "receiver_normal": axis,
            "error_max_m": max(errors, default=0.0),
            "error_average_m": sum(errors) / len(errors) if errors else 0.0,
            "spot_map": spot_map,
            "spot_metrics": spot_metrics,
        }
        self._facet_cache_key = cache_key
        self._facet_cache = analysis
        return analysis

    def export_csv_text(self) -> str:
        rows = self.history or [self.snapshot()]
        serializable_rows = [
            {key: value for key, value in row.items() if not isinstance(value, tuple)}
            for row in rows
        ]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(serializable_rows[0].keys()))
        writer.writeheader()
        writer.writerows(serializable_rows)
        return stream.getvalue()

    def export_facets_csv_text(self) -> str:
        """Exporta una fila por faceta, incluida su geometria y su impacto."""
        analysis = self.facet_analysis()
        results = {item.facet_id: item for item in analysis["results"]}
        rows: list[dict[str, object]] = []
        for facet in analysis["facets"]:
            result = results.get(facet.id)
            impact = result.impact_point if result is not None else None
            reflected = result.reflected_direction if result is not None else None
            rows.append(
                {
                    "facet_id": facet.id,
                    "active": facet.active,
                    "shape": facet.shape,
                    "size_m": facet.size,
                    "layout_u_m": facet.layout_u_m,
                    "layout_v_m": facet.layout_v_m,
                    "center_x_m": facet.center[0],
                    "center_y_m": facet.center[1],
                    "center_z_m": facet.center[2],
                    "normal_x": facet.normal[0],
                    "normal_y": facet.normal[1],
                    "normal_z": facet.normal[2],
                    "impact_u_mm": result.impact_u_m * 1000.0 if result else "",
                    "impact_v_mm": result.impact_v_m * 1000.0 if result else "",
                    "focus_error_mm": result.focus_error_m * 1000.0 if result else "",
                    "impact_x_m": impact[0] if impact else "",
                    "impact_y_m": impact[1] if impact else "",
                    "impact_z_m": impact[2] if impact else "",
                    "reflected_x": reflected[0] if reflected else "",
                    "reflected_y": reflected[1] if reflected else "",
                    "reflected_z": reflected[2] if reflected else "",
                }
            )
        if not rows:
            rows.append({"facet_id": "", "active": False, "shape": self.facet_shape})
        stream = io.StringIO()
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()

    def export_events_csv_text(self) -> str:
        rows = self.events or [{"timestamp": "", "category": "", "message": "Sin eventos"}]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=("timestamp", "category", "message"))
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()

    def export_experiment_zip(self) -> bytes:
        """Empaqueta historial, facetas y bitacora sin usar el sistema de archivos."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("historial.csv", self.export_csv_text())
            archive.writestr("facetas.csv", self.export_facets_csv_text())
            archive.writestr("eventos.csv", self.export_events_csv_text())
            archive.writestr(
                "LEEME.txt",
                "Gemelo digital web 0.4.0\n"
                "historial.csv: serie temporal y configuracion completa.\n"
                "facetas.csv: una fila por faceta con geometria, normal e impacto.\n"
                "eventos.csv: bitacora operativa de la sesion.\n",
            )
        return buffer.getvalue()
