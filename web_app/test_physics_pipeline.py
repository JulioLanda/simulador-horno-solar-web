"""Pruebas integrales de la cadena física de un instante."""

from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import FrozenInstanceError

from web_app.physics_pipeline import (
    PhysicalStepInputs,
    simulate_physical_step,
)


class PhysicsPipelineTests(unittest.TestCase):
    """Comprueba la composición del núcleo sin iniciar la interfaz web."""

    def temixco_inputs(self, **changes: object) -> PhysicalStepInputs:
        """Construye el caso diurno de referencia permitiendo variaciones."""

        # Mantener un único caso base hace comparables todas las pruebas.
        values: dict[str, object] = {
            "when": dt.datetime(2026, 8, 6, 12, 0, 0),
            "latitude_deg": 18.85,
            "longitude_deg": -99.233333,
            "utc_offset_hours": -6.0,
            "site_altitude_m": 1280.0,
            "pressure_pa": 101325.0,
            "temperature_c": 25.0,
        }
        # Cada prueba modifica solo el parámetro físico que pretende aislar.
        values.update(changes)
        return PhysicalStepInputs(**values)  # type: ignore[arg-type]

    def test_default_geometry_preserves_documented_relative_receiver(self) -> None:
        """Los valores globales deben conservar el desplazamiento documentado."""

        inputs = self.temixco_inputs()
        relative = tuple(
            receiver - heliostat
            for receiver, heliostat in zip(
                inputs.receiver_center,
                inputs.heliostat_center,
                strict=True,
            )
        )
        # Las restas binarias como 1.80 - 2.20 requieren tolerancia de redondeo.
        for actual, expected in zip(relative, (0.0, 5.55, -0.40), strict=True):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_inputs_and_results_are_immutable(self) -> None:
        """Una captura física no debe cambiar después de haberse calculado."""

        inputs = self.temixco_inputs()
        result = simulate_physical_step(inputs)
        with self.assertRaises(FrozenInstanceError):
            inputs.solar_method = "spa"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.reason = "alterado"  # type: ignore[misc]

    def test_ideal_reachable_case_hits_receiver_center(self) -> None:
        """Sin errores ni saturación, la cadena completa debe cerrar en cero."""

        result = simulate_physical_step(self.temixco_inputs())

        self.assertTrue(result.operational)
        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "impacto_valido")
        self.assertIsNotNone(result.limited_commands)
        self.assertEqual(result.limited_commands.limit_labels, ())  # type: ignore[union-attr]
        self.assertIsNotNone(result.impact)
        self.assertAlmostEqual(result.impact.u_m, 0.0, places=12)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.impact.v_m, 0.0, places=12)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.impact.radial_error_m, 0.0, places=12)  # type: ignore[union-attr]

    def test_night_stops_before_commands_and_impact(self) -> None:
        """La noche conserva el Sol calculado, pero no fabrica la solución."""

        result = simulate_physical_step(
            self.temixco_inputs(when=dt.datetime(2026, 8, 6, 0, 0, 0))
        )

        self.assertLess(result.solar_position.altitude_deg, 0.0)
        self.assertFalse(result.operational)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "sol_fuera_de_operacion")
        self.assertIsNone(result.ideal_commands)
        self.assertIsNone(result.actual_pose)
        self.assertIsNone(result.impact)

    def test_operating_threshold_is_strict_in_complete_flow(self) -> None:
        """Estar exactamente en el umbral no autoriza el movimiento."""

        baseline = simulate_physical_step(self.temixco_inputs())
        result = simulate_physical_step(
            self.temixco_inputs(
                minimum_solar_altitude_deg=baseline.solar_position.altitude_deg
            )
        )

        self.assertFalse(result.operational)
        self.assertEqual(result.reason, "sol_fuera_de_operacion")
        self.assertIsNone(result.limited_commands)

    def test_azimuth_saturation_stops_only_that_axis_and_propagates_reason(self) -> None:
        """Offsets excesivos deben activar ambos extremos sin alterar altura."""

        cases = (
            (200.0, 90.0, "limite_acimut_oeste"),
            (-200.0, -90.0, "limite_acimut_este"),
        )
        for offset, expected_angle, expected_label in cases:
            with self.subTest(offset=offset):
                result = simulate_physical_step(
                    self.temixco_inputs(azimuth_offset_deg=offset)
                )

                self.assertTrue(result.operational)
                self.assertIsNotNone(result.offset_commands)
                self.assertIsNotNone(result.limited_commands)
                limited = result.limited_commands
                self.assertEqual(  # type: ignore[union-attr]
                    limited.applied.azimuth_deg,
                    expected_angle,
                )
                self.assertEqual(  # type: ignore[union-attr]
                    limited.applied.height_deg,
                    result.offset_commands.height_deg,  # type: ignore[union-attr]
                )
                self.assertEqual(  # type: ignore[union-attr]
                    limited.limit_labels,
                    (expected_label,),
                )
                self.assertFalse(result.valid)
                self.assertIsNotNone(result.impact)
                self.assertEqual(  # type: ignore[union-attr]
                    result.reason,
                    result.impact.reason,
                )
                self.assertEqual(result.reason, "interseccion_detras_del_origen")

    def test_height_saturation_stops_only_that_axis(self) -> None:
        """El límite Home debe detener altura y conservar el acimut solicitado."""

        result = simulate_physical_step(
            self.temixco_inputs(height_offset_deg=100.0)
        )

        self.assertIsNotNone(result.offset_commands)
        self.assertIsNotNone(result.limited_commands)
        limited = result.limited_commands
        self.assertEqual(limited.applied.height_deg, 90.0)  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            limited.applied.azimuth_deg,
            result.offset_commands.azimuth_deg,  # type: ignore[union-attr]
        )
        self.assertEqual(limited.limit_labels, ("limite_altura_home",))  # type: ignore[union-attr]

    def test_vertical_ideal_normal_preserves_fallback_azimuth_at_home(self) -> None:
        """La singularidad vertical debe conservar orientación y cerrar óptica."""

        # Obtener el vector solar real que utilizará la segunda ejecución.
        baseline = simulate_physical_step(self.temixco_inputs())
        sun = baseline.sun_direction

        # Reflejar el rayo respecto de una normal vertical define un receptor
        # cuya bisectriz ideal será exactamente el cenit.
        vertical_reflection = (-sun[0], -sun[1], sun[2])
        self.assertTrue(baseline.valid)
        pivot = self.temixco_inputs().heliostat_center
        receiver = tuple(
            pivot_component + 5.0 * direction_component
            for pivot_component, direction_component in zip(
                pivot,
                vertical_reflection,
                strict=True,
            )
        )

        result = simulate_physical_step(
            self.temixco_inputs(
                receiver_center=receiver,
                fallback_azimuth_deg=37.0,
            )
        )

        self.assertIsNotNone(result.ideal_commands)
        self.assertAlmostEqual(result.ideal_commands.azimuth_deg, 37.0, places=10)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.ideal_commands.height_deg, 90.0, places=10)  # type: ignore[union-attr]
        self.assertIsNotNone(result.actual_pose)
        self.assertAlmostEqual(result.actual_pose.horizontal_edge[2], 0.0, places=12)  # type: ignore[union-attr]
        self.assertTrue(result.valid)
        self.assertIsNotNone(result.impact)
        self.assertAlmostEqual(result.impact.radial_error_m, 0.0, places=12)  # type: ignore[union-attr]

    def test_reda_and_spa_produce_same_physical_snapshot(self) -> None:
        """Las dos interfaces NREL SPA deben cerrar en la misma geometría."""

        reda = simulate_physical_step(self.temixco_inputs(solar_method="reda"))
        spa = simulate_physical_step(self.temixco_inputs(solar_method="spa"))

        self.assertNotEqual(reda.solar_position.method, spa.solar_position.method)
        self.assertEqual(reda.ideal_commands, spa.ideal_commands)
        self.assertEqual(reda.limited_commands, spa.limited_commands)
        self.assertEqual(reda.actual_pose, spa.actual_pose)
        self.assertEqual(reda.impact, spa.impact)

    def test_duffie_beckman_is_close_but_not_forced_equal_to_spa(self) -> None:
        """D&B debe resolver la óptica usando sus propios ángulos solares."""

        spa = simulate_physical_step(self.temixco_inputs(solar_method="spa"))
        db = simulate_physical_step(
            self.temixco_inputs(solar_method="duffie_beckman")
        )

        self.assertNotEqual(spa.solar_position.zenith_deg, db.solar_position.zenith_deg)
        self.assertLess(
            abs(spa.solar_position.zenith_deg - db.solar_position.zenith_deg),
            0.2,
        )
        self.assertTrue(db.valid)
        self.assertIsNotNone(db.impact)
        self.assertAlmostEqual(db.impact.radial_error_m, 0.0, places=12)  # type: ignore[union-attr]

    def test_nearby_instants_produce_continuous_motor_commands(self) -> None:
        """Diez segundos de evolución no deben provocar un salto angular."""

        first = simulate_physical_step(
            self.temixco_inputs(when=dt.datetime(2026, 8, 6, 12, 0, 0))
        )
        second = simulate_physical_step(
            self.temixco_inputs(when=dt.datetime(2026, 8, 6, 12, 0, 10))
        )

        self.assertIsNotNone(first.ideal_commands)
        self.assertIsNotNone(second.ideal_commands)
        self.assertLess(  # type: ignore[union-attr]
            abs(second.ideal_commands.azimuth_deg - first.ideal_commands.azimuth_deg),
            0.1,
        )
        self.assertLess(  # type: ignore[union-attr]
            abs(second.ideal_commands.height_deg - first.ideal_commands.height_deg),
            0.1,
        )


if __name__ == "__main__":
    unittest.main()
