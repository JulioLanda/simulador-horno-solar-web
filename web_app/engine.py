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
from dataclasses import dataclass, field
from pathlib import Path

try:
    from digital_twin.facet_model import optimal_facet_offsets
except ModuleNotFoundError:
    # En desarrollo ``engine.py`` vive en web_app y los modelos son hermanos;
    # en el paquete Shinylive, ``digital_twin`` queda dentro del mismo folder.
    for candidate in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent):
        if (candidate / "digital_twin" / "facet_model.py").exists():
            sys.path.insert(0, str(candidate))
            break
    from digital_twin.facet_model import optimal_facet_offsets


TAU = 2.0 * math.pi
DEG = math.pi / 180.0
RAD = 180.0 / math.pi
WEB_APP_VERSION = "0.2.1"


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
    "az_limit_min": -95.0,
    "az_limit_max": 95.0,
    "el_limit_min": 0.0,
    "el_limit_max": 90.0,
    "az_deg_per_second": 9.0,
    "el_deg_per_second": 9.0,
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
    mode: str = "Automatico"
    tracking: bool = True
    running: bool = False
    session_started: bool = False
    time_mode: str = "Tiempo real"
    simulated_time: dt.datetime = field(default_factory=lambda: dt.datetime(2026, 8, 6, 12, 0, 0))
    simulated_start: dt.datetime = field(default_factory=lambda: dt.datetime(2026, 8, 6, 12, 0, 0))
    time_scale: float = 60.0
    method: str = "D&B"
    facet_enabled: bool = False
    facet_shape: str = MINIHORNO_WEB_PROFILE["facet_shape"]
    facet_count: int = MINIHORNO_WEB_PROFILE["facet_count"]
    facet_size_m: float = MINIHORNO_WEB_PROFILE["facet_size_m"]
    facet_gap_m: float = MINIHORNO_WEB_PROFILE["facet_gap_m"]
    facet_focal_distance_m: float = MINIHORNO_WEB_PROFILE["facet_focal_distance_m"]
    iterations: int = 0
    history: list[dict[str, object]] = field(default_factory=list)
    _sample_accumulator_s: float = 0.0
    _elapsed_s: float = 0.0

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
            "az_deg_per_second",
            "el_deg_per_second",
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
        elif axis.lower() == "el":
            self.el_target_deg = clamp(
                self.el_target_deg + amount,
                self.el_limit_min,
                self.el_limit_max,
            )
        else:
            raise ValueError(f"Eje manual desconocido: {axis}")

    def stop_manual_motion(self) -> None:
        self.az_target_deg = self.az_angle_deg
        self.el_target_deg = self.el_angle_deg

    def apply_observed_correction(self) -> None:
        """Compensa gradualmente el error angular observado."""
        elapsed_hours = self._elapsed_s / 3600.0
        effective_az = self.az_offset_deg + self.drift_az_deg_per_hour * elapsed_hours
        effective_el = self.el_offset_deg + self.drift_el_deg_per_hour * elapsed_hours
        gain = clamp(self.correction_gain, 0.0, 1.0)
        self.correction_az_deg += (-effective_az - self.correction_az_deg) * gain
        self.correction_el_deg += (-effective_el - self.correction_el_deg) * gain

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
        self.correction_az_deg = 0.0
        self.correction_el_deg = 0.0

    def reset(self) -> None:
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
        self.correction_az_deg = 0.0
        self.correction_el_deg = 0.0

    def start_or_toggle(self) -> None:
        self.session_started = True
        self.running = not self.running if self.session_started and self.running else True

    def pause_or_resume(self) -> None:
        if not self.session_started:
            self.session_started = True
        self.running = not self.running

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
        target = (self.rx, self.ry, self.rz)
        target_direction = v_unit(target)
        ideal_normal = compute_heliostat_normal(sun, target_direction)
        ideal_az, ideal_el = angles_from_normal(ideal_normal)
        elapsed_hours = self._elapsed_s / 3600.0
        effective_az_error = self.az_offset_deg + self.drift_az_deg_per_hour * elapsed_hours
        effective_el_error = self.el_offset_deg + self.drift_el_deg_per_hour * elapsed_hours
        actual_normal = normal_from_angles(
            self.az_angle_deg + effective_az_error,
            self.el_angle_deg + effective_el_error,
        )
        reflected = reflect_vector(v_mul(sun, -1.0), actual_normal)
        valid, impact_u, impact_v, impact_radial, ray_distance = target_impact(reflected, target)
        incidence = angle_between(sun, actual_normal)
        reflection = angle_between(reflected, actual_normal)
        target_difference = angle_between(reflected, target_direction)
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
            "effective_az_error_deg": effective_az_error,
            "effective_el_error_deg": effective_el_error,
        }

    def step(self, wall_dt_s: float) -> None:
        wall_dt_s = clamp(float(wall_dt_s), 0.0, 1.0)
        if not self.running:
            return
        if self.time_mode == "Fecha simulada":
            self.simulated_time += dt.timedelta(seconds=wall_dt_s * max(0.0, self.time_scale))
        self._elapsed_s += wall_dt_s * (max(0.0, self.time_scale) if self.time_mode == "Fecha simulada" else 1.0)
        geometry = self._solar_geometry()
        if self.mode == "Automatico" and self.tracking:
            self.az_target_deg = float(geometry["ideal_az_deg"]) + self.correction_az_deg
            self.el_target_deg = float(geometry["ideal_el_deg"]) + self.correction_el_deg
        elif self.mode == "Home":
            self.az_target_deg = 0.0
            self.el_target_deg = 90.0
        self.az_target_deg = clamp(self.az_target_deg, self.az_limit_min, self.az_limit_max)
        self.el_target_deg = clamp(self.el_target_deg, self.el_limit_min, self.el_limit_max)
        self.az_angle_deg = move_toward(
            self.az_angle_deg,
            self.az_target_deg,
            self.az_deg_per_second * clamp(self.az_pwm, 0.0, 1.0) * wall_dt_s,
            wrap=True,
        )
        self.el_angle_deg = move_toward(
            self.el_angle_deg,
            self.el_target_deg,
            self.el_deg_per_second * clamp(self.el_pwm, 0.0, 1.0) * wall_dt_s,
        )
        self.iterations += 1
        self._sample_accumulator_s += wall_dt_s
        if self._sample_accumulator_s >= 0.5:
            self._sample_accumulator_s = 0.0
            self.history.append(self.snapshot())
            if len(self.history) > 1200:
                del self.history[:-1200]

    def status(self, snapshot: dict[str, object] | None = None) -> tuple[str, str]:
        sample = snapshot or self.snapshot()
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
        geometry = self._solar_geometry()
        radial_m = float(geometry["spot_radial_m"])
        result: dict[str, object] = {
            "simulator_version": WEB_APP_VERSION,
            "timestamp": geometry["when"].isoformat(timespec="seconds"),
            "time_mode": self.time_mode,
            "time_scale": self.time_scale,
            "mode": self.mode,
            "running": self.running,
            "iterations": self.iterations,
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
            "sun": geometry["sun"],
            "normal": geometry["actual_normal"],
            "reflected": geometry["reflected"],
            "target": geometry["target"],
            "mirror_size_m": self.mirror_size_m,
            "base_width_m": self.base_width_m,
            "fork_height_m": self.fork_height_m,
            "rail_length_m": self.rail_length_m,
            "receiver_screen_m": self.receiver_screen_m,
            "target_tolerance_m": self.target_tolerance_m,
            "facet_enabled": self.facet_enabled,
            "facet_shape": self.facet_shape,
            "facet_count": self.facet_count,
            "facet_size_m": self.facet_size_m,
            "facet_gap_m": self.facet_gap_m,
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
