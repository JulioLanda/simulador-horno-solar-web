"""Pruebas del nucleo compartible con Pyodide."""

from __future__ import annotations

import datetime as dt
import math
import unittest

from web_app.engine import WebTwinState, solar_position_db


class WebTwinEngineTests(unittest.TestCase):
    def test_solar_position_is_plausible_for_temixco_noon(self) -> None:
        zenith, altitude, azimuth = solar_position_db(
            dt.datetime(2026, 8, 6, 12, 0, 0),
            18.85,
            -99.233333,
            -6.0,
            "D&B",
        )
        self.assertGreater(altitude, 60.0)
        self.assertLess(zenith, 30.0)
        self.assertTrue(-180.0 <= azimuth <= 180.0)

    def test_ideal_normal_centers_the_reflected_ray(self) -> None:
        state = WebTwinState(time_mode="Fecha simulada")
        geometry = state._solar_geometry()
        state.az_angle_deg = float(geometry["ideal_az_deg"])
        state.el_angle_deg = float(geometry["ideal_el_deg"])
        sample = state.snapshot()
        self.assertTrue(sample["spot_valid"])
        self.assertLess(abs(float(sample["spot_radial_mm"])), 1e-6)

    def test_simulated_clock_honors_multiplier(self) -> None:
        state = WebTwinState(time_mode="Fecha simulada", time_scale=60.0, running=True, session_started=True)
        initial = state.simulated_time
        state.step(0.5)
        self.assertEqual((state.simulated_time - initial).total_seconds(), 30.0)

    def test_home_moves_gradually_without_jump(self) -> None:
        state = WebTwinState(
            mode="Home",
            running=True,
            session_started=True,
            az_angle_deg=40.0,
            el_angle_deg=25.0,
        )
        state.step(0.1)
        self.assertGreater(state.az_angle_deg, 39.0)
        self.assertLess(state.az_angle_deg, 40.0)
        self.assertGreater(state.el_angle_deg, 25.0)
        self.assertLess(state.el_angle_deg, 26.0)

    def test_automatic_mode_moves_from_current_pose_without_jump(self) -> None:
        state = WebTwinState(
            mode="Automatico",
            tracking=True,
            running=True,
            session_started=True,
            time_mode="Fecha simulada",
            az_angle_deg=-30.0,
            el_angle_deg=20.0,
        )
        state.step(0.1)
        self.assertLess(abs(state.az_angle_deg + 30.0), 1.0)
        self.assertLess(abs(state.el_angle_deg - 20.0), 1.0)

    def test_facets_keep_requested_count_and_center(self) -> None:
        for shape in ("Cuadrada", "Circular", "Hexagonal"):
            state = WebTwinState(facet_shape=shape, facet_count=17)
            layout = state.facet_layout()
            self.assertEqual(len(layout), 17)
            self.assertAlmostEqual(sum(item[1] for item in layout) / 17, 0.0, places=10)
            self.assertAlmostEqual(sum(item[2] for item in layout) / 17, 0.0, places=10)

    def test_csv_contains_finite_operational_fields(self) -> None:
        state = WebTwinState(time_mode="Fecha simulada")
        geometry = state._solar_geometry()
        state.az_angle_deg = float(geometry["ideal_az_deg"])
        state.el_angle_deg = float(geometry["ideal_el_deg"])
        csv_text = state.export_csv_text()
        self.assertIn("timestamp", csv_text)
        self.assertIn("spot_radial_mm", csv_text)
        self.assertNotIn(str(math.nan), csv_text.lower())

    def test_manual_target_changes_without_moving_instantly(self) -> None:
        state = WebTwinState(mode="Manual", az_angle_deg=10.0, az_target_deg=10.0)
        state.set_manual_target("az", 1.0, 5.0)
        self.assertEqual(state.az_angle_deg, 10.0)
        self.assertEqual(state.az_target_deg, 15.0)

    def test_observed_correction_is_incremental(self) -> None:
        state = WebTwinState(az_offset_deg=1.0, el_offset_deg=-0.5, correction_gain=0.5)
        state.apply_observed_correction()
        self.assertAlmostEqual(state.correction_az_deg, -0.5)
        self.assertAlmostEqual(state.correction_el_deg, 0.25)
        state.apply_observed_correction()
        self.assertAlmostEqual(state.correction_az_deg, -0.75)
        self.assertAlmostEqual(state.correction_el_deg, 0.375)

    def test_minihorno_profile_keeps_real_world_scale(self) -> None:
        state = WebTwinState()
        state.apply_profile({"mirror_size_m": 0.2, "base_width_m": 0.19})
        sample = state.snapshot()
        self.assertAlmostEqual(float(sample["mirror_size_m"]), 0.2)
        self.assertAlmostEqual(float(sample["base_width_m"]), 0.19)


if __name__ == "__main__":
    unittest.main()
