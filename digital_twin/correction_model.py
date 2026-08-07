"""Estrategias ligeras de correccion de deriva para el gemelo digital."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CorrectionConfig:
    """Parametros configurables de las estrategias de correccion."""

    enabled: bool = False
    strategy: str = "Ninguna"
    constant_az_deg: float = 0.0
    constant_el_deg: float = 0.0
    time_az_rate_deg_per_hour: float = 0.0
    time_el_rate_deg_per_hour: float = 0.0
    polynomial_az_c0: float = 0.0
    polynomial_az_c1: float = 0.0
    polynomial_az_c2: float = 0.0
    polynomial_el_c0: float = 0.0
    polynomial_el_c1: float = 0.0
    polynomial_el_c2: float = 0.0
    image_gain_az: float = 0.5
    image_gain_el: float = 0.5
    image_max_step_deg: float = 1.0
    camera_interval_s: float = 60.0


class CorrectionModel:
    """Mantiene la compensacion AZ/EL y aplica la estrategia seleccionada."""

    STRATEGIES = (
        "Ninguna",
        "Offset constante",
        "Dependiente del tiempo",
        "Polinomial",
        "Impacto observado",
        "Camara periodica",
    )

    def __init__(self, config: CorrectionConfig) -> None:
        self.config = config
        self.correction_az_deg = 0.0
        self.correction_el_deg = 0.0
        self.elapsed_s = 0.0
        self.seconds_since_observation = 0.0
        self.update_count = 0
        self.last_strategy = config.strategy
        self.corrected_this_step = False

    def reset(self) -> None:
        """Borra compensacion, tiempo y contador de actualizaciones."""
        self.correction_az_deg = 0.0
        self.correction_el_deg = 0.0
        self.elapsed_s = 0.0
        self.seconds_since_observation = 0.0
        self.update_count = 0
        self.last_strategy = self.config.strategy
        self.corrected_this_step = False

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        limit = max(0.0, float(limit))
        return max(-limit, min(limit, value))

    def _set_absolute(self, az_deg: float, el_deg: float) -> None:
        changed = (
            abs(az_deg - self.correction_az_deg) > 1e-12
            or abs(el_deg - self.correction_el_deg) > 1e-12
        )
        self.correction_az_deg = float(az_deg)
        self.correction_el_deg = float(el_deg)
        if changed or self.update_count == 0:
            self.update_count += 1
            self.corrected_this_step = True

    def _apply_observed_impact(
        self,
        observed_u_m: float,
        observed_v_m: float,
        target_distance_m: float,
    ) -> None:
        """Convierte error lineal u/v a correccion angular de espejo."""
        if not (
            math.isfinite(observed_u_m)
            and math.isfinite(observed_v_m)
            and math.isfinite(target_distance_m)
            and target_distance_m > 1e-9
        ):
            return
        # La rotacion del rayo reflejado es aproximadamente el doble de la
        # rotacion de la normal, por eso se usa el factor 0.5.
        az_delta = -0.5 * self.config.image_gain_az * math.degrees(
            math.atan2(observed_u_m, target_distance_m)
        )
        el_delta = -0.5 * self.config.image_gain_el * math.degrees(
            math.atan2(observed_v_m, target_distance_m)
        )
        az_delta = self._clamp(az_delta, self.config.image_max_step_deg)
        el_delta = self._clamp(el_delta, self.config.image_max_step_deg)
        self.correction_az_deg += az_delta
        self.correction_el_deg += el_delta
        self.seconds_since_observation = 0.0
        self.update_count += 1
        self.corrected_this_step = True

    def update(
        self,
        simulated_elapsed_s: float,
        observed_u_m: float,
        observed_v_m: float,
        target_distance_m: float,
        observation_trigger: bool = False,
        force: bool = False,
    ) -> tuple[float, float]:
        """Actualiza y devuelve la compensacion de acimut y elevacion."""
        dt_s = max(0.0, float(simulated_elapsed_s))
        if self.config.strategy != self.last_strategy:
            self.reset()
        self.elapsed_s += dt_s
        self.seconds_since_observation += dt_s
        self.corrected_this_step = False

        if not self.config.enabled or self.config.strategy == "Ninguna":
            self.correction_az_deg = 0.0
            self.correction_el_deg = 0.0
            return (0.0, 0.0)

        strategy = self.config.strategy
        hours = self.elapsed_s / 3600.0
        if strategy == "Offset constante":
            self._set_absolute(self.config.constant_az_deg, self.config.constant_el_deg)
        elif strategy == "Dependiente del tiempo":
            self._set_absolute(
                self.config.constant_az_deg + self.config.time_az_rate_deg_per_hour * hours,
                self.config.constant_el_deg + self.config.time_el_rate_deg_per_hour * hours,
            )
        elif strategy == "Polinomial":
            self._set_absolute(
                self.config.polynomial_az_c0
                + self.config.polynomial_az_c1 * hours
                + self.config.polynomial_az_c2 * hours * hours,
                self.config.polynomial_el_c0
                + self.config.polynomial_el_c1 * hours
                + self.config.polynomial_el_c2 * hours * hours,
            )
        elif strategy == "Impacto observado":
            if observation_trigger or force:
                self._apply_observed_impact(
                    observed_u_m,
                    observed_v_m,
                    target_distance_m,
                )
        elif strategy == "Camara periodica":
            due = self.seconds_since_observation + 1e-9 >= max(
                0.001, self.config.camera_interval_s
            )
            if due or force:
                self._apply_observed_impact(
                    observed_u_m,
                    observed_v_m,
                    target_distance_m,
                )
        return (self.correction_az_deg, self.correction_el_deg)
