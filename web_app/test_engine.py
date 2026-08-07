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


if __name__ == "__main__":
    unittest.main()
