"""Pruebas del nucleo compartible con Pyodide."""

from __future__ import annotations

import datetime as dt
import csv
import io
import math
import unittest
import zipfile

from web_app.engine import (
    MINIHORNO_WEB_PROFILE,
    WEB_APP_VERSION,
    WebTwinState,
    solar_position_db,
)
from web_app.physics_core import solar_position


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

    def test_historical_solar_api_delegates_to_exact_core(self) -> None:
        when = dt.datetime(2026, 8, 6, 12, 0, 0)
        actual = solar_position_db(when, 18.85, -99.233333, -6.0, "REDA")
        expected = solar_position(
            when,
            18.85,
            -99.233333,
            -6.0,
            method="reda",
            altitude_m=1280.0,
            pressure_pa=101325.0,
            temperature_c=25.0,
        )
        self.assertEqual(
            actual,
            (expected.zenith_deg, expected.altitude_deg, expected.azimuth_deg),
        )

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

    def test_motor_axes_move_independently(self) -> None:
        state = WebTwinState(
            mode="Manual",
            running=True,
            session_started=True,
            time_mode="Fecha simulada",
            az_angle_deg=0.0,
            el_angle_deg=50.0,
            az_target_deg=30.0,
            el_target_deg=70.0,
            az_motor_on=False,
            el_motor_on=True,
        )
        state.step(0.2)
        self.assertEqual(state.az_angle_deg, 0.0)
        self.assertGreater(state.el_angle_deg, 50.0)

    def test_confirmed_limits_stop_and_emit_visible_label(self) -> None:
        self.assertEqual(MINIHORNO_WEB_PROFILE["az_limit_min"], -90.0)
        self.assertEqual(MINIHORNO_WEB_PROFILE["az_limit_max"], 90.0)
        self.assertEqual(MINIHORNO_WEB_PROFILE["el_limit_min"], 10.0)
        self.assertEqual(MINIHORNO_WEB_PROFILE["el_limit_max"], 90.0)
        state = WebTwinState(
            mode="Manual",
            running=True,
            session_started=True,
            time_mode="Fecha simulada",
            az_angle_deg=89.9,
            az_target_deg=90.0,
            el_angle_deg=45.0,
            el_target_deg=45.0,
        )
        state.step(0.2)
        self.assertEqual(state.az_angle_deg, 90.0)
        sample = state.snapshot()
        self.assertEqual(sample["status"], "LIMITE ALCANZADO: ACIMUT OESTE")
        self.assertTrue(any("ACIMUT OESTE" in item["message"] for item in state.events))

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

    def test_scene_pose_adds_orientation_without_changing_csv_contract(self) -> None:
        state = WebTwinState(
            time_mode="Fecha simulada",
            az_angle_deg=-30.0,
            el_angle_deg=42.0,
        )
        snapshot = state.snapshot()
        payload = state.scene_payload()
        csv_header = next(csv.reader(io.StringIO(state.export_csv_text())))
        self.assertEqual(len(csv_header), 166)
        self.assertNotIn("mirror_horizontal_edge", snapshot)
        self.assertIn("mirror_horizontal_edge", payload)
        self.assertIn("mirror_upper_direction", payload)
        self.assertAlmostEqual(payload["mirror_horizontal_edge"][2], 0.0, places=12)

    def test_manual_target_changes_without_moving_instantly(self) -> None:
        state = WebTwinState(mode="Manual", az_angle_deg=10.0, az_target_deg=10.0)
        state.set_manual_target("az", 1.0, 5.0)
        self.assertEqual(state.az_angle_deg, 10.0)
        self.assertEqual(state.az_target_deg, 15.0)

    def test_observed_correction_is_incremental(self) -> None:
        state = WebTwinState(correction_gain=0.5, time_mode="Fecha simulada")
        geometry = state._solar_geometry()
        state.az_angle_deg = float(geometry["ideal_az_deg"])
        state.el_angle_deg = float(geometry["ideal_el_deg"])
        state.error_config.enable_azimuth_offset = True
        state.error_config.azimuth_offset_deg = 0.25
        before = float(state._solar_geometry()["corrected_spot_radial_m"])
        state.apply_observed_correction()
        first = float(state._solar_geometry()["corrected_spot_radial_m"])
        state.apply_observed_correction()
        second = float(state._solar_geometry()["corrected_spot_radial_m"])
        self.assertLess(first, before)
        self.assertLess(second, first)

    def test_error_scenarios_are_computed_in_parallel(self) -> None:
        state = WebTwinState(time_mode="Fecha simulada")
        geometry = state._solar_geometry()
        state.az_angle_deg = float(geometry["ideal_az_deg"])
        state.el_angle_deg = float(geometry["ideal_el_deg"])
        state.error_config.enable_elevation_offset = True
        state.error_config.elevation_offset_deg = 0.4
        sample = state.snapshot()
        self.assertLess(float(sample["ideal_spot_radial_mm"]), 1e-6)
        self.assertGreater(float(sample["error_spot_radial_mm"]), 1.0)

    def test_tracking_schedule_holds_target_between_updates(self) -> None:
        state = WebTwinState(
            time_mode="Fecha simulada",
            time_scale=60.0,
            running=True,
            session_started=True,
            tracking_update_interval_s=60.0,
        )
        state.step(0.1)
        held = (state.az_target_deg, state.el_target_deg)
        state.step(0.1)
        self.assertEqual((state.az_target_deg, state.el_target_deg), held)
        self.assertEqual(state.tracking_update_count, 1)
        state.step(0.9)
        self.assertEqual(state.tracking_update_count, 2)

    def test_replay_requires_history_and_cycles_samples(self) -> None:
        state = WebTwinState(running=True, session_started=True, time_mode="Fecha simulada")
        self.assertFalse(state.start_replay())
        state.step(0.5)
        state.step(0.5)
        self.assertTrue(state.start_replay())
        first_timestamp = state.snapshot()["timestamp"]
        state.step(0.7)
        self.assertNotEqual(state.snapshot()["timestamp"], first_timestamp)
        state.stop_replay()
        self.assertFalse(state.replay_active)

    def test_minihorno_profile_keeps_real_world_scale(self) -> None:
        state = WebTwinState()
        state.apply_profile({"mirror_size_m": 0.2, "base_width_m": 0.19})
        sample = state.snapshot()
        self.assertAlmostEqual(float(sample["mirror_size_m"]), 0.2)
        self.assertAlmostEqual(float(sample["base_width_m"]), 0.19)

    def test_facet_analysis_traces_rays_and_builds_intensity_map(self) -> None:
        state = WebTwinState(facet_enabled=True, spot_map_enabled=True)
        analysis = state.facet_analysis()
        self.assertEqual(len(analysis["facets"]), 9)
        self.assertEqual(len(analysis["results"]), 9)
        self.assertIsNotNone(analysis["spot_map"])
        self.assertEqual(analysis["spot_map"].resolution, 51)

    def test_selected_facet_can_be_misaligned_and_disabled(self) -> None:
        state = WebTwinState(
            facet_enabled=True,
            facet_selected_id="F1",
            facet_horizontal_misalignment_deg=0.5,
        )
        analysis = state.facet_analysis()
        result = next(item for item in analysis["results"] if item.facet_id == "F1")
        self.assertGreater(result.focus_error_m, 0.001)
        state.set_selected_facet_active(False)
        analysis = state.facet_analysis()
        self.assertEqual(len(analysis["results"]), 8)
        self.assertFalse(next(item for item in analysis["facets"] if item.id == "F1").active)

    def test_requested_odd_spot_resolution_is_preserved(self) -> None:
        state = WebTwinState(
            facet_enabled=True,
            spot_map_enabled=True,
            spot_map_resolution=101,
        )
        self.assertEqual(state.facet_analysis()["spot_map"].resolution, 101)

    def test_experiment_package_contains_history_facets_and_events(self) -> None:
        state = WebTwinState(facet_enabled=True)
        payload = state.export_experiment_zip()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"historial.csv", "facetas.csv", "eventos.csv", "LEEME.txt"},
            )
            self.assertIn("facet_id", archive.read("facetas.csv").decode("utf-8"))
            readme = archive.read("LEEME.txt").decode("utf-8")
            self.assertIn(f"Gemelo digital web {WEB_APP_VERSION}", readme)

    def test_release_version_is_consistent_in_snapshot(self) -> None:
        self.assertEqual(WEB_APP_VERSION, "0.5.0")
        self.assertEqual(WebTwinState().snapshot()["simulator_version"], WEB_APP_VERSION)


if __name__ == "__main__":
    unittest.main()
