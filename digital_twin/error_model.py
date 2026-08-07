"""Errores geometricos y mecanicos del gemelo digital.

Convencion global: +x oeste, +y sur y +z cenit. Los errores XYZ se expresan
en metros dentro de la geometria activa; los errores angulares, en grados.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


DEG = math.pi / 180.0


@dataclass
class ErrorConfig:
    """Configuracion independiente de cada fuente de error simulada."""

    enable_elevation_offset: bool = False
    elevation_offset_deg: float = 0.0
    enable_azimuth_offset: bool = False
    azimuth_offset_deg: float = 0.0
    enable_north_south_misalignment: bool = False
    north_south_misalignment_deg: float = 0.0
    enable_target_position_error: bool = False
    target_error_x_m: float = 0.0
    target_error_y_m: float = 0.0
    target_error_z_m: float = 0.0
    enable_heliostat_position_error: bool = False
    heliostat_error_x_m: float = 0.0
    heliostat_error_y_m: float = 0.0
    heliostat_error_z_m: float = 0.0
    enable_peralte_error: bool = False
    peralte_error_deg: float = 0.0
    enable_backlash: bool = False
    backlash_deg: float = 0.0
    enable_directional_error: bool = False
    upward_error_deg: float = 0.0
    downward_error_deg: float = 0.0
    enable_random_noise: bool = False
    random_noise_std_deg: float = 0.0
    random_seed: int = 12345
    correction_azimuth_deg: float = 0.0
    correction_elevation_deg: float = 0.0

    def active_error_names(self) -> list[str]:
        """Devuelve nombres breves de los errores habilitados."""
        names: list[str] = []
        switches = (
            (self.enable_elevation_offset, "offset elevacion"),
            (self.enable_azimuth_offset, "offset acimut"),
            (self.enable_north_south_misalignment, "eje norte-sur"),
            (self.enable_target_position_error, "posicion target"),
            (self.enable_heliostat_position_error, "coordenadas heliostato"),
            (self.enable_peralte_error, "peralte"),
            (self.enable_backlash, "backlash"),
            (self.enable_directional_error, "subida/bajada"),
            (self.enable_random_noise, "ruido"),
        )
        for enabled, name in switches:
            if enabled:
                names.append(name)
        return names


@dataclass(frozen=True)
class MotionErrorSample:
    """Errores que dependen de una correccion o movimiento concreto."""

    backlash_az_deg: float = 0.0
    backlash_el_deg: float = 0.0
    directional_el_deg: float = 0.0
    noise_az_deg: float = 0.0
    noise_el_deg: float = 0.0
    az_direction: int = 0
    el_direction: int = 0


class ErrorModel:
    """Aplica errores configurados con ruido reproducible por semilla."""

    def __init__(self, config: ErrorConfig) -> None:
        self.config = config
        self._seed = int(config.random_seed)
        self._rng = random.Random(self._seed)

    @staticmethod
    def _direction(delta_deg: float) -> int:
        if delta_deg > 1e-12:
            return 1
        if delta_deg < -1e-12:
            return -1
        return 0

    def reset_random(self) -> None:
        """Reinicia la secuencia para repetir exactamente el mismo ruido."""
        self._seed = int(self.config.random_seed)
        self._rng.seed(self._seed)

    def _ensure_seed(self) -> None:
        if int(self.config.random_seed) != self._seed:
            self.reset_random()

    def sample_motion(self, az_delta_deg: float, el_delta_deg: float) -> MotionErrorSample:
        """Muestrea backlash, error direccional y ruido para un movimiento."""
        self._ensure_seed()
        az_direction = self._direction(az_delta_deg)
        el_direction = self._direction(el_delta_deg)
        backlash = max(0.0, float(self.config.backlash_deg))
        backlash_az = -az_direction * backlash if self.config.enable_backlash else 0.0
        backlash_el = -el_direction * backlash if self.config.enable_backlash else 0.0
        directional = 0.0
        if self.config.enable_directional_error:
            if el_direction > 0:
                directional = self.config.upward_error_deg
            elif el_direction < 0:
                directional = self.config.downward_error_deg
        noise_az = noise_el = 0.0
        if self.config.enable_random_noise and self.config.random_noise_std_deg > 0.0:
            std = float(self.config.random_noise_std_deg)
            noise_az = self._rng.gauss(0.0, std)
            noise_el = self._rng.gauss(0.0, std)
        return MotionErrorSample(
            backlash_az_deg=backlash_az,
            backlash_el_deg=backlash_el,
            directional_el_deg=directional,
            noise_az_deg=noise_az,
            noise_el_deg=noise_el,
            az_direction=az_direction,
            el_direction=el_direction,
        )

    def effective_target(
        self,
        nominal_target: tuple[float, float, float],
        include_errors: bool,
    ) -> tuple[float, float, float]:
        """Aplica error de target y coordenadas del heliostato al vector relativo."""
        if not include_errors:
            return nominal_target
        x, y, z = nominal_target
        if self.config.enable_target_position_error:
            x += self.config.target_error_x_m
            y += self.config.target_error_y_m
            z += self.config.target_error_z_m
        if self.config.enable_heliostat_position_error:
            x -= self.config.heliostat_error_x_m
            y -= self.config.heliostat_error_y_m
            z -= self.config.heliostat_error_z_m
        return (x, y, z)

    def angular_errors(
        self,
        sample: MotionErrorSample,
        corrected: bool,
    ) -> tuple[float, float]:
        """Combina errores angulares activos y compensacion manual opcional."""
        az_error = 0.0
        el_error = 0.0
        if self.config.enable_azimuth_offset:
            az_error += self.config.azimuth_offset_deg
        if self.config.enable_north_south_misalignment:
            # Aproximacion ligera: desviacion horizontal del marco como yaw.
            az_error += self.config.north_south_misalignment_deg
        if self.config.enable_elevation_offset:
            el_error += self.config.elevation_offset_deg
        if self.config.enable_peralte_error:
            el_error += self.config.peralte_error_deg
        az_error += sample.backlash_az_deg + sample.noise_az_deg
        el_error += sample.backlash_el_deg + sample.directional_el_deg + sample.noise_el_deg
        if corrected:
            az_error += self.config.correction_azimuth_deg
            el_error += self.config.correction_elevation_deg
        return az_error, el_error

    def normal_from_command(
        self,
        command_az_deg: float,
        command_el_deg: float,
        sample: MotionErrorSample,
        include_errors: bool,
        corrected: bool = False,
    ) -> tuple[float, float, float]:
        """Calcula la normal real desde el comando y los errores activos."""
        az_error = el_error = 0.0
        if include_errors:
            az_error, el_error = self.angular_errors(sample, corrected)
        az = (command_az_deg + az_error) * DEG
        el = (command_el_deg + el_error) * DEG
        cos_el = math.cos(el)
        return (cos_el * math.sin(az), cos_el * math.cos(az), math.sin(el))
