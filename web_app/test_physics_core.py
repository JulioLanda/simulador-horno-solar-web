"""Pruebas independientes del núcleo matemático v2."""

from __future__ import annotations

import datetime as dt
import unittest

import numpy as np

from web_app.physics_core import (
    AxisCommands,
    MechanicalLimits,
    angle_between,
    apply_encoder_offsets,
    apply_mechanical_limits,
    azimuth_height_from_direction,
    direction_from_azimuth_height,
    home_commands,
    ideal_heliostat_normal,
    mirror_edge_centers,
    mirror_pose_from_altaz,
    ray_plane_intersection,
    receiver_frame,
    receiver_impact,
    reflected_direction,
    rotate_about_axis,
    solar_position,
    solar_position_duffie_beckman,
    solar_position_reda,
    solar_position_spa,
    solar_vector,
    sun_is_operational,
    target_direction,
    validate_mirror_basis,
)


class PhysicsCoreTests(unittest.TestCase):
    def assertVectorAlmostEqual(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
        places: int = 10,
    ) -> None:
        for value, reference in zip(actual, expected, strict=True):
            self.assertAlmostEqual(value, reference, places=places)

    def test_angle_between_ignores_scale_and_rejects_zero_vector(self) -> None:
        self.assertAlmostEqual(angle_between((3.0, 4.0, 0.0), (0.6, 0.8, 0.0)), 0.0)
        with self.assertRaises(ValueError):
            angle_between((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))

    def test_public_geometry_rejects_bad_shapes_and_nonfinite_values(self) -> None:
        with self.assertRaises(ValueError):
            angle_between((1.0, 2.0), (1.0, 0.0, 0.0))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            target_direction((0.0, 0.0, 0.0), (1.0, float("nan"), 3.0))

    def test_scipy_rotation_has_expected_direction_and_preserves_norm(self) -> None:
        rotated = rotate_about_axis((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), -90.0)
        self.assertVectorAlmostEqual(rotated, (1.0, 0.0, 0.0))
        self.assertAlmostEqual(float(np.linalg.norm(rotated)), 1.0, places=12)

    def test_direction_convention_points_west_and_south(self) -> None:
        self.assertVectorAlmostEqual(direction_from_azimuth_height(0.0, 0.0), (0.0, 1.0, 0.0))
        self.assertVectorAlmostEqual(direction_from_azimuth_height(90.0, 0.0), (1.0, 0.0, 0.0))
        self.assertVectorAlmostEqual(direction_from_azimuth_height(-90.0, 0.0), (-1.0, 0.0, 0.0))
        self.assertVectorAlmostEqual(direction_from_azimuth_height(20.0, 90.0), (0.0, 0.0, 1.0))

    def test_altaz_pose_keeps_lower_edge_horizontal_over_full_range(self) -> None:
        for azimuth_deg in (-90.0, -45.0, 0.0, 45.0, 90.0):
            for height_deg in (10.0, 25.0, 50.0, 75.0, 90.0):
                with self.subTest(azimuth=azimuth_deg, height=height_deg):
                    pose = mirror_pose_from_altaz(azimuth_deg, height_deg)
                    self.assertTrue(validate_mirror_basis(pose))
                    self.assertAlmostEqual(pose.horizontal_edge[2], 0.0, places=12)
                    self.assertAlmostEqual(
                        float(np.dot(pose.horizontal_edge, pose.normal)),
                        0.0,
                        places=12,
                    )
                    self.assertGreaterEqual(pose.upper_direction[2], -1.0e-12)

    def test_home_pose_is_horizontal_and_preserves_azimuth_orientation(self) -> None:
        home = home_commands()
        pose = mirror_pose_from_altaz(home.azimuth_deg, home.height_deg)
        self.assertEqual(home, AxisCommands(0.0, 90.0))
        self.assertVectorAlmostEqual(pose.normal, (0.0, 0.0, 1.0))
        self.assertVectorAlmostEqual(pose.horizontal_edge, (-1.0, 0.0, 0.0))

    def test_mirror_lower_edge_is_physically_below_upper_edge(self) -> None:
        pose = mirror_pose_from_altaz(0.0, 10.0)
        lower, upper = mirror_edge_centers((0.0, 0.0, 2.20), 2.0, pose)
        self.assertLess(lower[2], upper[2])
        self.assertAlmostEqual(lower[2] + upper[2], 4.40, places=12)

    def test_inverse_and_direct_altaz_are_consistent(self) -> None:
        for azimuth_deg in (-90.0, -30.0, 0.0, 30.0, 90.0):
            for height_deg in (10.0, 35.0, 65.0, 89.0):
                direction = direction_from_azimuth_height(azimuth_deg, height_deg)
                commands = azimuth_height_from_direction(direction)
                reconstructed = mirror_pose_from_altaz(commands.azimuth_deg, commands.height_deg)
                self.assertLess(angle_between(reconstructed.normal, direction), 1.0e-8)

    def test_vertical_direction_uses_fallback_azimuth_without_flip(self) -> None:
        commands = azimuth_height_from_direction((0.0, 0.0, 1.0), fallback_azimuth_deg=37.0)
        pose = mirror_pose_from_altaz(commands.azimuth_deg, commands.height_deg)
        self.assertAlmostEqual(commands.azimuth_deg, 37.0)
        self.assertAlmostEqual(commands.height_deg, 90.0)
        self.assertAlmostEqual(pose.horizontal_edge[2], 0.0)

    def test_ideal_normal_reflects_sun_to_receiver(self) -> None:
        sun_array = np.array((0.25, -0.20, 0.95), dtype=float)
        target_array = np.array((0.0, 5.55, -0.40), dtype=float)
        sun = tuple(sun_array / np.linalg.norm(sun_array))
        target = tuple(target_array / np.linalg.norm(target_array))
        normal = ideal_heliostat_normal(sun, target)
        reflected = reflected_direction(tuple(-np.asarray(sun)), normal)
        self.assertLess(angle_between(reflected, target), 1.0e-8)

    def test_target_direction_uses_relative_positions(self) -> None:
        direction = target_direction((1.0, 2.0, 3.0), (1.0, 7.0, 3.0))
        self.assertVectorAlmostEqual(direction, (0.0, 1.0, 0.0))

    def test_receiver_frame_has_west_u_and_up_v(self) -> None:
        frame = receiver_frame((0.0, 5.55, 0.0))
        self.assertVectorAlmostEqual(frame.normal, (0.0, 1.0, 0.0))
        self.assertVectorAlmostEqual(frame.u_axis, (1.0, 0.0, 0.0))
        self.assertVectorAlmostEqual(frame.v_axis, (0.0, 0.0, 1.0))

    def test_receiver_impact_reports_local_coordinates(self) -> None:
        frame = receiver_frame((0.0, 5.55, -0.40))
        aimed_point = (
            frame.center[0] + 0.10 * frame.u_axis[0] + 0.20 * frame.v_axis[0],
            frame.center[1] + 0.10 * frame.u_axis[1] + 0.20 * frame.v_axis[1],
            frame.center[2] + 0.10 * frame.u_axis[2] + 0.20 * frame.v_axis[2],
        )
        impact = receiver_impact((0.0, 0.0, 0.0), aimed_point, frame)
        self.assertTrue(impact.valid)
        self.assertAlmostEqual(float(impact.u_m), 0.10, places=10)
        self.assertAlmostEqual(float(impact.v_m), 0.20, places=10)
        self.assertAlmostEqual(float(impact.radial_error_m), np.hypot(0.10, 0.20), places=10)

    def test_ray_plane_rejects_parallel_and_backward_intersections(self) -> None:
        parallel = ray_plane_intersection(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 5.0, 0.0),
            (0.0, 1.0, 0.0),
        )
        backward = ray_plane_intersection(
            (0.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 5.0, 0.0),
            (0.0, 1.0, 0.0),
        )
        self.assertFalse(parallel.valid)
        self.assertEqual(parallel.reason, "rayo_paralelo_al_plano")
        self.assertFalse(backward.valid)
        self.assertEqual(backward.reason, "interseccion_detras_del_origen")

    def test_encoder_offsets_are_explicit_and_do_not_apply_limits(self) -> None:
        offset = apply_encoder_offsets(
            AxisCommands(20.0, 40.0),
            azimuth_offset_deg=1.5,
            height_offset_deg=-0.5,
        )
        self.assertEqual(offset, AxisCommands(21.5, 39.5))

    def test_mechanical_limits_stop_and_label_each_axis(self) -> None:
        limited = apply_mechanical_limits(AxisCommands(-120.0, 100.0))
        self.assertEqual(limited.applied, AxisCommands(-90.0, 90.0))
        self.assertEqual(
            limited.limit_labels,
            ("limite_acimut_este", "limite_altura_home"),
        )
        opposite = apply_mechanical_limits(AxisCommands(120.0, 0.0))
        self.assertEqual(opposite.applied, AxisCommands(90.0, 10.0))
        self.assertEqual(
            opposite.limit_labels,
            ("limite_acimut_oeste", "limite_altura_minimo"),
        )

    def test_exact_limits_also_emit_labels(self) -> None:
        at_home = apply_mechanical_limits(home_commands())
        self.assertEqual(at_home.applied, AxisCommands(0.0, 90.0))
        self.assertEqual(at_home.limit_labels, ("limite_altura_home",))
        at_west = apply_mechanical_limits(AxisCommands(90.0, 50.0))
        self.assertEqual(at_west.limit_labels, ("limite_acimut_oeste",))

    def test_invalid_mechanical_limit_order_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MechanicalLimits(azimuth_min_deg=90.0, azimuth_max_deg=-90.0)

    def test_reda_spa_matches_reference_case_for_temixco(self) -> None:
        when = dt.datetime(2026, 8, 6, 12, 0, 0)
        position = solar_position_reda(
            when,
            18.85,
            -99.233333,
            -6.0,
            altitude_m=1280.0,
            pressure_pa=101325.0,
            temperature_c=25.0,
        )
        self.assertAlmostEqual(position.zenith_deg, 10.450896240468026, places=9)
        self.assertAlmostEqual(position.altitude_deg, 79.54910375953197, places=9)
        self.assertAlmostEqual(position.azimuth_deg, -78.91263660086224, places=9)
        self.assertAlmostEqual(float(position.equation_of_time_min), -5.879282766392862, places=9)
        self.assertEqual(position.method, "reda_andreas_spa_python")

    def test_reda_matches_published_nrel_spa_reference_case(self) -> None:
        position = solar_position_reda(
            dt.datetime(2003, 10, 17, 12, 30, 30),
            39.742476,
            -105.1786,
            -7.0,
            altitude_m=1830.14,
            pressure_pa=82000.0,
            temperature_c=11.0,
            delta_t_s=67.0,
        )
        self.assertAlmostEqual(position.zenith_deg, 50.11162, places=5)
        # NREL publica 194.34024° desde el norte; en el proyecto son
        # +14.34024° desde el sur hacia el oeste.
        self.assertAlmostEqual(position.azimuth_deg, 14.34024, places=5)

    def test_spa_pvlib_and_reda_are_two_interfaces_to_same_algorithm(self) -> None:
        when = dt.datetime(2026, 8, 6, 12, 0, 0)
        arguments = (when, 18.85, -99.233333, -6.0)
        environment = {
            "altitude_m": 1280.0,
            "pressure_pa": 101325.0,
            "temperature_c": 25.0,
        }
        reda = solar_position_reda(*arguments, **environment)
        spa = solar_position_spa(*arguments, **environment)
        self.assertAlmostEqual(reda.zenith_deg, spa.zenith_deg, places=12)
        self.assertAlmostEqual(reda.altitude_deg, spa.altitude_deg, places=12)
        self.assertAlmostEqual(reda.azimuth_deg, spa.azimuth_deg, places=12)
        self.assertNotEqual(reda.method, spa.method)

    def test_duffie_beckman_uses_pvlib_analytical_routines(self) -> None:
        position = solar_position_duffie_beckman(
            dt.datetime(2026, 8, 6, 12, 0, 0),
            18.85,
            -99.233333,
            -6.0,
        )
        self.assertAlmostEqual(position.zenith_deg, 10.52003977800949, places=9)
        self.assertAlmostEqual(position.altitude_deg, 79.47996022199051, places=9)
        self.assertAlmostEqual(position.azimuth_deg, -79.03123259216223, places=9)
        self.assertEqual(position.method, "duffie_beckman_pvlib")

    def test_solar_selector_defaults_to_reda_and_never_falls_back(self) -> None:
        when = dt.datetime(2026, 8, 6, 12, 0, 0)
        position = solar_position(when, 18.85, -99.233333, -6.0)
        self.assertEqual(position.method, "reda_andreas_spa_python")
        self.assertEqual(
            solar_position(when, 18.85, -99.233333, -6.0, method="D&B").method,
            "duffie_beckman_pvlib",
        )
        with self.assertRaises(ValueError):
            solar_position(when, 18.85, -99.233333, -6.0, method="inventado")

    def test_solar_vector_uses_selected_method_and_is_unitary(self) -> None:
        when = dt.datetime(2026, 8, 6, 12, 0, 0)
        vector_position, vector = solar_vector(
            when,
            18.85,
            -99.233333,
            -6.0,
            method="spa",
            altitude_m=1280.0,
            temperature_c=25.0,
        )
        self.assertEqual(vector_position.method, "spa_pvlib_nrel_numpy")
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=12)

    def test_solar_operating_boundary_is_strict(self) -> None:
        self.assertFalse(sun_is_operational(-0.1))
        self.assertFalse(sun_is_operational(0.0))
        self.assertTrue(sun_is_operational(0.1))
        self.assertFalse(sun_is_operational(5.0, minimum_deg=5.0))
        self.assertTrue(sun_is_operational(5.1, minimum_deg=5.0))


if __name__ == "__main__":
    unittest.main()
