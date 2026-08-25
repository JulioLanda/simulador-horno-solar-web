"""Pruebas de la frontera entre la aplicación 0.4.0 y el núcleo físico V2."""

from __future__ import annotations

import datetime as dt
import unittest

from web_app.physics_adapter import (
    WebPhysicsRequest,
    WebScenarioRequest,
    evaluate_web_physics,
    solar_method_for_core,
)
from web_app.physics_core import AxisCommands, MechanicalLimits


class PhysicsAdapterTests(unittest.TestCase):
    """Comprueba trazabilidad, límites y pose sin iniciar Shiny."""

    def request(self, **changes: object) -> WebPhysicsRequest:
        values: dict[str, object] = {
            "when": dt.datetime(2026, 8, 6, 12, 0, 0),
            "latitude_deg": 18.85,
            "longitude_deg": -99.233333,
            "utc_offset_hours": -6.0,
            "receiver_offset": (0.0, 5.55, -0.40),
            "current_motor_commands": AxisCommands(0.0, 90.0),
            "scenarios": (
                WebScenarioRequest(
                    "Ideal",
                    AxisCommands(0.0, 90.0),
                    (0.0, 5.55, -0.40),
                ),
            ),
            "selected_scenario": "Ideal",
            "solar_method": "REDA",
        }
        values.update(changes)
        return WebPhysicsRequest(**values)  # type: ignore[arg-type]

    def test_interface_method_names_map_to_explicit_core_methods(self) -> None:
        self.assertEqual(solar_method_for_core("D&B"), "duffie_beckman")
        self.assertEqual(solar_method_for_core("REDA"), "reda")
        self.assertEqual(solar_method_for_core("SPA/PVLIB"), "spa")
        with self.assertRaises(ValueError):
            solar_method_for_core("aproximado")

    def test_control_target_closes_the_ideal_optics(self) -> None:
        initial = evaluate_web_physics(self.request())
        self.assertIsNotNone(initial.control_targets)
        target = initial.control_targets.applied  # type: ignore[union-attr]
        result = evaluate_web_physics(
            self.request(
                current_motor_commands=target,
                scenarios=(
                    WebScenarioRequest("Ideal", target, (0.0, 5.55, -0.40)),
                ),
            )
        )
        self.assertTrue(result.selected.impact.valid)  # type: ignore[union-attr]
        self.assertAlmostEqual(
            result.selected.impact.radial_error_m,  # type: ignore[union-attr]
            0.0,
            places=12,
        )

    def test_pose_keeps_lower_edge_horizontal_for_both_axes(self) -> None:
        for azimuth, height in ((-90.0, 10.0), (-35.0, 42.0), (0.0, 90.0), (90.0, 10.0)):
            with self.subTest(azimuth=azimuth, height=height):
                commands = AxisCommands(azimuth, height)
                result = evaluate_web_physics(
                    self.request(
                        current_motor_commands=commands,
                        scenarios=(
                            WebScenarioRequest("Ideal", commands, (0.0, 5.55, -0.40)),
                        ),
                    )
                )
                self.assertAlmostEqual(result.selected.pose.horizontal_edge[2], 0.0, places=12)

    def test_limits_are_independent_and_report_the_reached_edge(self) -> None:
        result = evaluate_web_physics(
            self.request(
                current_motor_commands=AxisCommands(120.0, 5.0),
                limits=MechanicalLimits(-90.0, 90.0, 10.0, 90.0),
            )
        )
        self.assertEqual(result.current_motor_limits.applied, AxisCommands(90.0, 10.0))
        self.assertEqual(
            result.current_motor_limits.limit_labels,
            ("limite_acimut_oeste", "limite_altura_minimo"),
        )

    def test_night_preserves_pose_without_fabricating_impact(self) -> None:
        result = evaluate_web_physics(
            self.request(when=dt.datetime(2026, 8, 6, 0, 0, 0))
        )
        self.assertFalse(result.ideal_step.operational)
        self.assertIsNone(result.control_targets)
        self.assertIsNone(result.selected.reflected)
        self.assertIsNone(result.selected.impact)
        self.assertAlmostEqual(result.selected.pose.horizontal_edge[2], 0.0, places=12)

    def test_each_scenario_uses_its_own_axis_and_target_errors(self) -> None:
        initial = evaluate_web_physics(self.request())
        target = initial.control_targets.applied  # type: ignore[union-attr]
        scenarios = (
            WebScenarioRequest("Ideal", target, (0.0, 5.55, -0.40)),
            WebScenarioRequest(
                "Con error",
                target,
                (0.02, 5.55, -0.40),
                azimuth_error_deg=0.3,
                height_error_deg=-0.2,
            ),
        )
        result = evaluate_web_physics(
            self.request(
                current_motor_commands=target,
                scenarios=scenarios,
                selected_scenario="Con error",
            )
        )
        self.assertLess(result.scenario("Ideal").impact.radial_error_m, 1.0e-9)  # type: ignore[union-attr]
        self.assertGreater(result.scenario("Con error").impact.radial_error_m, 0.01)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
