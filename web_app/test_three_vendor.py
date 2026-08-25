"""Pruebas de los recursos Three.js distribuidos con la aplicacion."""

from __future__ import annotations

import unittest
from pathlib import Path


WWW_DIR = Path(__file__).resolve().parent / "www"
THREE_DIR = WWW_DIR / "vendor" / "three"


class ThreeVendorTests(unittest.TestCase):
    """Evita reintroducir dependencias CDN en el gemelo tridimensional."""

    def test_scene_imports_three_from_same_site(self) -> None:
        source = (WWW_DIR / "twin3d.js").read_text(encoding="utf-8")
        self.assertIn('./vendor/three/three.module.min.js', source)
        self.assertIn('./vendor/three/OrbitControls.js', source)
        self.assertNotIn("https://esm.sh", source)

    def test_orbit_controls_uses_local_three_module(self) -> None:
        source = (THREE_DIR / "OrbitControls.js").read_text(encoding="utf-8")
        self.assertIn("from './three.module.min.js';", source)
        self.assertNotIn("from 'three';", source)

    def test_vendor_contains_library_controls_and_license(self) -> None:
        self.assertGreater((THREE_DIR / "three.module.min.js").stat().st_size, 300_000)
        self.assertGreater((THREE_DIR / "three.core.min.js").stat().st_size, 350_000)
        self.assertGreater((THREE_DIR / "OrbitControls.js").stat().st_size, 30_000)
        license_text = (THREE_DIR / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)


if __name__ == "__main__":
    unittest.main()
