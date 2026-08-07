"""Edicion web experimental del gemelo digital del mini horno solar."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
from pathlib import Path

from shiny import App, reactive, render, ui

try:
    from .engine import MINIHORNO_WEB_PROFILE, WebTwinState
except ImportError:
    from engine import MINIHORNO_WEB_PROFILE, WebTwinState


APP_DIR = Path(__file__).parent

CSV_COLUMN_DICTIONARY = (
    (
        "Sesión y tiempo",
        "Contexto temporal y estado de ejecución de cada muestra.",
        "blue",
        (
            ("simulator_version", "Versión de la aplicación web que produjo el archivo.", "texto"),
            ("timestamp", "Fecha y hora del reloj del experimento para esta muestra, en formato ISO 8601.", "fecha-hora"),
            ("time_mode", "Origen del reloj: Tiempo real o Fecha simulada.", "texto"),
            ("time_scale", "Multiplicador aplicado al avance del reloj cuando se usa fecha simulada.", "factor ×"),
            ("simulation_step_s", "Cantidad de segundos usada por el boton de avance manual.", "s"),
            ("mode", "Modo de operación del heliostato: Automático, Manual o Home.", "texto"),
            ("tracking", "Indica si el seguimiento solar automatico estaba habilitado.", "True / False"),
            ("session_started", "Indica si la sesion ya habia sido iniciada al menos una vez.", "True / False"),
            ("running", "Indica si la simulación estaba avanzando al crear la muestra.", "True / False"),
            ("replay_active", "Indica si la interfaz estaba mostrando una reproducción del historial.", "True / False"),
            ("iterations", "Número acumulado de actualizaciones ejecutadas desde el inicio de la sesión.", "conteo"),
            ("history_limit", "Maximo de muestras temporales conservadas en memoria.", "conteo"),
        ),
    ),
    (
        "Seguimiento, óptica e impacto",
        "Pose, objetivo, Sol, reflexión, errores y resultado sobre el receptor.",
        "teal",
        (
            ("az_deg", "Ángulo de acimut real del heliostato en la muestra; oeste es positivo.", "grados"),
            ("el_deg", "Ángulo de elevación real del heliostato.", "grados"),
            ("az_target_deg", "Acimut objetivo que el controlador intenta alcanzar.", "grados"),
            ("el_target_deg", "Elevación objetivo que el controlador intenta alcanzar.", "grados"),
            ("az_error_deg", "Diferencia angular envuelta entre acimut objetivo y acimut real.", "grados"),
            ("el_error_deg", "Diferencia entre elevación objetivo y elevación real.", "grados"),
            ("spot_valid", "Indica si el rayo reflejado cruza frontalmente el plano receptor.", "True / False"),
            ("spot_u_mm", "Coordenada horizontal del impacto; positiva hacia el oeste del receptor.", "mm"),
            ("spot_v_mm", "Coordenada vertical del impacto; positiva hacia el cenit.", "mm"),
            ("spot_radial_mm", "Distancia del impacto al centro: raíz cuadrada de u² + v².", "mm"),
            ("ray_distance_m", "Distancia recorrida desde el heliostato hasta la intersección con el receptor.", "m"),
            ("zenith_deg", "Ángulo cenital solar; equivale a 90° menos la altura solar.", "grados"),
            ("altitude_deg", "Altura del Sol sobre el horizonte.", "grados"),
            ("solar_azimuth_deg", "Acimut solar en la convención del laboratorio: este negativo, sur 0° y oeste positivo.", "grados"),
            ("incidence_deg", "Ángulo entre la dirección hacia el Sol y la normal real del espejo.", "grados"),
            ("reflection_deg", "Ángulo entre el rayo reflejado y la normal real del espejo.", "grados"),
            ("target_difference_deg", "Separación angular entre el rayo reflejado y la dirección ideal hacia el target.", "grados"),
            ("effective_az_error_deg", "Error geométrico efectivo de acimut: offset más deriva acumulada.", "grados"),
            ("effective_el_error_deg", "Error geométrico efectivo de elevación: offset más deriva acumulada.", "grados"),
            ("correction_az_deg", "Compensación acumulada que se suma al objetivo de acimut.", "grados"),
            ("correction_el_deg", "Compensación acumulada que se suma al objetivo de elevación.", "grados"),
        ),
    ),
    (
        "Geometría",
        "Dimensiones principales vigentes en el modelo durante la muestra.",
        "gold",
        (
            ("mirror_size_m", "Longitud del lado del espejo del heliostato.", "m"),
            ("base_width_m", "Ancho configurado de la base del heliostato.", "m"),
            ("fork_height_m", "Altura configurada de la horquilla.", "m"),
            ("rail_length_m", "Longitud configurada del riel entre estructuras.", "m"),
            ("receiver_screen_m", "Diámetro de la pantalla o plano receptor.", "m"),
            ("target_tolerance_m", "Radio de tolerancia permitido alrededor del centro del target.", "m"),
        ),
    ),
    (
        "Facetas y mapa",
        "Configuración global del concentrador facetado y del mapa de intensidad.",
        "red",
        (
            ("facet_enabled", "Indica si el modelo de concentrador facetado estaba activo.", "True / False"),
            ("facet_shape", "Forma geométrica seleccionada: cuadrada, circular o hexagonal.", "texto"),
            ("facet_count", "Número total de facetas generado por el acomodo automático.", "conteo"),
            ("facet_size_m", "Lado, diámetro o ancho entre caras, según la forma seleccionada.", "m"),
            ("facet_gap_m", "Separación libre configurada entre facetas adyacentes.", "m"),
            ("facet_focal_distance_m", "Distancia focal utilizada para orientar las facetas hacia el foco.", "m"),
            ("facet_selected_id", "Identificador de la faceta seleccionada para edición, por ejemplo F5.", "texto"),
            ("facet_active_count", "Cantidad de facetas que contribuyen activamente al cálculo.", "conteo"),
            ("facet_active_ids", "Lista separada por comas de las facetas activas.", "texto"),
            ("facet_misalignment_h_deg", "Desalineación horizontal aplicada a la faceta seleccionada.", "grados"),
            ("facet_misalignment_v_deg", "Desalineación vertical aplicada a la faceta seleccionada.", "grados"),
            ("spot_map_enabled", "Indica si estaba activado el cálculo del mapa de intensidad.", "True / False"),
            ("spot_map_resolution", "Cantidad de puntos por lado de la cuadrícula del mapa; siempre debe ser impar.", "puntos/lado"),
            ("spot_normalization", "Regla de escala del mapa: total, pico o sin normalizar.", "texto"),
            ("spot_base_sigma_m", "Sigma base usada para cada contribucion gaussiana.", "m"),
            ("spot_map_half_size_m", "Semiancho fisico cubierto por el mapa de intensidad.", "m"),
        ),
    ),
    (
        "Comparacion de escenarios",
        "Resultados simultaneos del caso ideal, el caso perturbado y el caso corregido.",
        "green",
        (
            ("error_mode", "Escenario elegido para alimentar el gemelo 3D y la lectura principal.", "texto"),
            ("active_errors", "Lista legible de las fuentes de error habilitadas.", "texto"),
            ("ideal_spot_u_mm", "Componente horizontal del impacto sin errores.", "mm"),
            ("ideal_spot_v_mm", "Componente vertical del impacto sin errores.", "mm"),
            ("ideal_spot_radial_mm", "Distancia radial del impacto ideal al centro.", "mm"),
            ("error_spot_u_mm", "Componente horizontal con errores y sin compensacion.", "mm"),
            ("error_spot_v_mm", "Componente vertical con errores y sin compensacion.", "mm"),
            ("error_spot_radial_mm", "Distancia radial con errores y sin compensacion.", "mm"),
            ("corrected_spot_u_mm", "Componente horizontal despues de aplicar la correccion.", "mm"),
            ("corrected_spot_v_mm", "Componente vertical despues de aplicar la correccion.", "mm"),
            ("corrected_spot_radial_mm", "Distancia radial despues de aplicar la correccion.", "mm"),
        ),
    ),
    (
        "Configuracion de errores",
        "Interruptores y magnitudes exactas usadas para perturbar el modelo.",
        "red",
        (
            ("error_enable_azimuth_offset", "Activa el offset fijo de acimut.", "True / False"),
            ("error_azimuth_offset_deg", "Magnitud del offset fijo de acimut.", "grados"),
            ("error_enable_elevation_offset", "Activa el offset fijo de elevacion.", "True / False"),
            ("error_elevation_offset_deg", "Magnitud del offset fijo de elevacion.", "grados"),
            ("error_enable_north_south", "Activa la desalineacion del marco norte-sur.", "True / False"),
            ("error_north_south_deg", "Magnitud angular de la desalineacion norte-sur.", "grados"),
            ("error_enable_target_xyz", "Activa el desplazamiento XYZ del receptor.", "True / False"),
            ("error_target_x_m", "Desplazamiento del receptor sobre X, oeste positivo.", "m"),
            ("error_target_y_m", "Desplazamiento del receptor sobre Y, sur positivo.", "m"),
            ("error_target_z_m", "Desplazamiento del receptor sobre Z, cenit positivo.", "m"),
            ("error_enable_heliostat_xyz", "Activa el error XYZ de posicion del heliostato.", "True / False"),
            ("error_heliostat_x_m", "Error de posicion del heliostato sobre X.", "m"),
            ("error_heliostat_y_m", "Error de posicion del heliostato sobre Y.", "m"),
            ("error_heliostat_z_m", "Error de posicion del heliostato sobre Z.", "m"),
            ("error_enable_peralte", "Activa un error adicional de peralte.", "True / False"),
            ("error_peralte_deg", "Magnitud del error adicional de peralte.", "grados"),
            ("error_enable_backlash", "Activa el juego mecanico al cambiar la orden.", "True / False"),
            ("error_backlash_deg", "Magnitud angular del backlash.", "grados"),
            ("error_enable_directional", "Activa errores distintos para subida y bajada.", "True / False"),
            ("error_upward_deg", "Error aplicado cuando la elevacion aumenta.", "grados"),
            ("error_downward_deg", "Error aplicado cuando la elevacion disminuye.", "grados"),
            ("error_enable_noise", "Activa ruido aleatorio reproducible.", "True / False"),
            ("error_noise_std_deg", "Desviacion estandar del ruido angular.", "grados"),
            ("error_noise_seed", "Semilla usada para repetir la misma secuencia de ruido.", "entero"),
            ("drift_az_deg_per_hour", "Tasa de deriva temporal en acimut.", "grados/h"),
            ("drift_el_deg_per_hour", "Tasa de deriva temporal en elevacion.", "grados/h"),
        ),
    ),
    (
        "Seguimiento y correccion",
        "Programador de actualizaciones, estadisticas por intervalo y compensacion aplicada.",
        "blue",
        (
            ("tracking_update_interval_s", "Intervalo solar entre capturas del objetivo o texto manual.", "s / texto"),
            ("seconds_since_tracking_update_s", "Tiempo solar transcurrido desde la ultima captura.", "s"),
            ("tracking_update_count", "Numero de objetivos solares capturados en la sesion.", "conteo"),
            ("tracking_error_max_mm", "Mayor error radial observado en el ultimo intervalo cerrado.", "mm"),
            ("tracking_error_average_mm", "Promedio del error radial del ultimo intervalo cerrado.", "mm"),
            ("tracking_error_rms_mm", "Valor RMS del error radial del ultimo intervalo cerrado.", "mm"),
            ("correction_enabled", "Indica si el modelo de correccion estaba habilitado.", "True / False"),
            ("correction_strategy", "Estrategia de correccion seleccionada.", "texto"),
            ("correction_update_count", "Numero de veces que la compensacion fue modificada.", "conteo"),
            ("correction_constant_az_deg", "Termino constante de correccion en acimut.", "grados"),
            ("correction_constant_el_deg", "Termino constante de correccion en elevacion.", "grados"),
            ("correction_rate_az_deg_per_hour", "Tasa temporal de correccion en acimut.", "grados/h"),
            ("correction_rate_el_deg_per_hour", "Tasa temporal de correccion en elevacion.", "grados/h"),
            ("correction_poly_az_c0", "Coeficiente c0 del polinomio de acimut.", "grados"),
            ("correction_poly_az_c1", "Coeficiente c1 del polinomio de acimut.", "grados/h"),
            ("correction_poly_az_c2", "Coeficiente c2 del polinomio de acimut.", "grados/h2"),
            ("correction_poly_el_c0", "Coeficiente c0 del polinomio de elevacion.", "grados"),
            ("correction_poly_el_c1", "Coeficiente c1 del polinomio de elevacion.", "grados/h"),
            ("correction_poly_el_c2", "Coeficiente c2 del polinomio de elevacion.", "grados/h2"),
            ("correction_gain", "Ganancia aplicada a la correccion basada en impacto.", "0 a 1"),
            ("correction_max_step_deg", "Cambio angular maximo permitido por observacion.", "grados"),
            ("correction_camera_interval_s", "Periodo entre observaciones de la camara periodica.", "s"),
        ),
    ),
    (
        "Ubicacion, control y encoders",
        "Calibracion solar, limites y estado de los actuadores simulados.",
        "gold",
        (
            ("lat_deg", "Latitud geografica usada por el calculo solar.", "grados"),
            ("lon_deg", "Longitud geografica usada por el calculo solar.", "grados"),
            ("utc_offset_hours", "Diferencia de la hora civil respecto de UTC.", "h"),
            ("solar_method", "Metodo solar elegido para la muestra.", "texto"),
            ("target_x_m", "Coordenada X efectiva del receptor.", "m"),
            ("target_y_m", "Coordenada Y efectiva del receptor.", "m"),
            ("target_z_m", "Coordenada Z efectiva del receptor.", "m"),
            ("peralte_deg", "Peralte calibrado entre la lectura mecanica y la normal optica.", "grados"),
            ("cdr_deg", "Banda muerta angular del controlador.", "grados"),
            ("camera_offset_az_deg", "Offset de calibracion de camara en acimut.", "grados"),
            ("camera_offset_el_deg", "Offset de calibracion de camara en elevacion.", "grados"),
            ("control_delay_s", "Retardo nominal configurado para el lazo de control.", "s"),
            ("az_limit_min_deg", "Limite mecanico minimo permitido en acimut.", "grados"),
            ("az_limit_max_deg", "Limite mecanico maximo permitido en acimut.", "grados"),
            ("el_limit_min_deg", "Limite mecanico minimo permitido en elevacion.", "grados"),
            ("el_limit_max_deg", "Limite mecanico maximo permitido en elevacion.", "grados"),
            ("az_motor_on", "Estado habilitado del motor de acimut.", "True / False"),
            ("el_motor_on", "Estado habilitado del motor de elevacion.", "True / False"),
            ("az_pwm", "Fraccion PWM aplicada al motor de acimut.", "0 a 1"),
            ("el_pwm", "Fraccion PWM aplicada al motor de elevacion.", "0 a 1"),
            ("az_speed_deg_s", "Velocidad maxima configurada en acimut.", "grados/s"),
            ("el_speed_deg_s", "Velocidad maxima configurada en elevacion.", "grados/s"),
            ("az_encoder_counts", "Lectura simulada del encoder de acimut.", "conteos"),
            ("el_encoder_counts", "Lectura simulada del encoder de elevacion.", "conteos"),
            ("az_counts_per_degree", "Factor de conversion del encoder de acimut.", "conteos/grado"),
            ("el_counts_per_degree", "Factor de conversion del encoder de elevacion.", "conteos/grado"),
        ),
    ),
    (
        "Vectores y presentacion 3D",
        "Componentes numericas de los vectores y visibilidad elegida en el gemelo.",
        "teal",
        (
            ("sun_x", "Componente X del vector unitario hacia el Sol.", "adimensional"),
            ("sun_y", "Componente Y del vector unitario hacia el Sol.", "adimensional"),
            ("sun_z", "Componente Z del vector unitario hacia el Sol.", "adimensional"),
            ("normal_x", "Componente X de la normal optica mostrada.", "adimensional"),
            ("normal_y", "Componente Y de la normal optica mostrada.", "adimensional"),
            ("normal_z", "Componente Z de la normal optica mostrada.", "adimensional"),
            ("reflected_x", "Componente X del rayo reflejado.", "adimensional"),
            ("reflected_y", "Componente Y del rayo reflejado.", "adimensional"),
            ("reflected_z", "Componente Z del rayo reflejado.", "adimensional"),
            ("show_sun_vector", "Indica si el vector solar era visible en 3D.", "True / False"),
            ("show_normal_vector", "Indica si la normal era visible en 3D.", "True / False"),
            ("show_reflected_vector", "Indica si el reflejado era visible en 3D.", "True / False"),
            ("show_target_direction", "Indica si la flecha corta hacia el objetivo era visible.", "True / False"),
            ("show_target_line", "Indica si la linea completa al receptor era visible.", "True / False"),
            ("show_mechanical_guides", "Indica si las guias mecanicas auxiliares estaban habilitadas.", "True / False"),
        ),
    ),
    (
        "Metricas de facetas e intensidad",
        "Resultados agregados del trazado de facetas y del mapa calculado.",
        "red",
        (
            ("facet_error_max_mm", "Mayor distancia de un impacto de faceta respecto del foco.", "mm"),
            ("facet_error_average_mm", "Promedio de las distancias de impacto respecto del foco.", "mm"),
            ("spot_centroid_u_mm", "Coordenada horizontal del centroide del mapa.", "mm"),
            ("spot_centroid_v_mm", "Coordenada vertical del centroide del mapa.", "mm"),
            ("spot_centroid_error_mm", "Distancia radial del centroide respecto del foco.", "mm"),
            ("spot_maximum_intensity", "Mayor intensidad numerica de una celda.", "segun normalizacion"),
            ("spot_total_intensity", "Suma de intensidades de todas las celdas.", "segun normalizacion"),
            ("spot_equivalent_diameter_mm", "Diametro equivalente estimado del spot.", "mm"),
            ("spot_shape", "Clasificacion descriptiva de la forma del spot.", "texto"),
        ),
    ),
    (
        "Estado operacional",
        "Resultado resumido que la interfaz mostraba en ese instante.",
        "green",
        (
            ("status", "Mensaje visible del estado: en objetivo, moviendo, pausada, Sol bajo o sin impacto.", "texto"),
            ("status_kind", "Categoría interna usada para color y presentación: config, paused, alert, ok o moving.", "texto"),
        ),
    ),
)


def number(value: object, digits: int = 2) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{numeric:.{digits}f}" if math.isfinite(numeric) else "--"


def json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def svg_document(content: str, width: int = 1000, height: int = 520, dark: bool = False) -> str:
    background = "#0b1620" if dark else "#f8fafc"
    return (
        f'<svg class="sim-svg" viewBox="0 0 {width} {height}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" style="background:{background}">'
        f"{content}</svg>"
    )


def scene_svg(sample: dict[str, object]) -> str:
    target = tuple(float(value) for value in sample["target"])
    sun = tuple(float(value) for value in sample["sun"])
    normal = tuple(float(value) for value in sample["normal"])

    def project(point: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = point
        return 210.0 + x * 54.0 + y * 72.0, 350.0 - z * 72.0 - y * 24.0

    origin = project((0.0, 0.0, 0.0))
    target_point = project(target)
    grid_lines: list[str] = []
    for longitudinal in range(0, 8):
        start = project((-2.2, longitudinal * 0.8, -1.4))
        end = project((2.2, longitudinal * 0.8, -1.4))
        grid_lines.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" />'
        )
    for transverse in range(-2, 3):
        start = project((transverse * 0.8, 0.0, -1.4))
        end = project((transverse * 0.8, 6.4, -1.4))
        grid_lines.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" />'
        )
    mirror_center = project((0.0, 0.0, 0.0))
    azimuth = math.radians(float(sample["az_deg"]))
    elevation = math.radians(float(sample["el_deg"]))
    half_width = 78.0
    half_height = max(12.0, 58.0 * abs(math.sin(elevation)) + 8.0)
    skew = 25.0 * math.sin(azimuth)
    mirror_points = (
        (mirror_center[0] - half_width + skew, mirror_center[1] - half_height),
        (mirror_center[0] + half_width + skew, mirror_center[1] - half_height),
        (mirror_center[0] + half_width - skew, mirror_center[1] + half_height),
        (mirror_center[0] - half_width - skew, mirror_center[1] + half_height),
    )
    mirror_polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in mirror_points)
    sun_end = project(v_scale(sun, 2.4))
    normal_end = project(v_scale(normal, 1.35))
    status = html.escape(str(sample["status"]))
    content = f"""
    <defs>
      <linearGradient id="mirror" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#eefaff"/><stop offset="1" stop-color="#91c6d8"/>
      </linearGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <g stroke="#23475d" stroke-width="1" opacity=".72">{''.join(grid_lines)}</g>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{target_point[0]:.1f}" y2="{target_point[1]:.1f}" stroke="#6f8798" stroke-width="5"/>
    <g stroke="#6d879c" stroke-width="5" fill="none">
      <line x1="{origin[0]-50:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+18:.1f}"/>
      <line x1="{origin[0]+50:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+18:.1f}"/>
      <line x1="{origin[0]:.1f}" y1="{origin[1]+116:.1f}" x2="{origin[0]:.1f}" y2="{origin[1]+12:.1f}"/>
    </g>
    <polygon points="{mirror_polygon}" fill="url(#mirror)" stroke="#d9f4ff" stroke-width="3"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{sun_end[0]:.1f}" y2="{sun_end[1]:.1f}" stroke="#ffd93d" stroke-width="5" filter="url(#glow)"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{normal_end[0]:.1f}" y2="{normal_end[1]:.1f}" stroke="#ff9f43" stroke-width="4" stroke-dasharray="8 6"/>
    <line x1="{origin[0]:.1f}" y1="{origin[1]:.1f}" x2="{target_point[0]:.1f}" y2="{target_point[1]:.1f}" stroke="#7de3ef" stroke-width="3" stroke-dasharray="7 7"/>
    <g transform="translate({target_point[0]:.1f} {target_point[1]:.1f})">
      <rect x="-20" y="-68" width="40" height="136" rx="7" fill="#c28d32" stroke="#f5d776" stroke-width="3"/>
      <circle cx="0" cy="0" r="13" fill="#fff3bd" stroke="#fff" stroke-width="2"/>
    </g>
    <g transform="translate(28 28)">
      <rect width="265" height="82" rx="8" fill="#102638" stroke="#31536a"/>
      <text x="16" y="27" fill="#f4d35e" font-size="15" font-weight="700">GEMELO WEB · VISTA ISOMETRICA</text>
      <text x="16" y="52" fill="#d7e7f2" font-size="13">AZ {number(sample['az_deg'])}° · EL {number(sample['el_deg'])}°</text>
      <text x="16" y="72" fill="#75e6a4" font-size="12">{status}</text>
    </g>
    <g transform="translate(785 420)" font-size="12" font-weight="700">
      <line x1="0" y1="40" x2="75" y2="40" stroke="#ff6b6b" stroke-width="3"/><text x="82" y="44" fill="#ffb0b0">+X oeste</text>
      <line x1="0" y1="40" x2="-32" y2="5" stroke="#75e6a4" stroke-width="3"/><text x="-75" y="0" fill="#75e6a4">+Y sur</text>
      <line x1="0" y1="40" x2="0" y2="-35" stroke="#8ebcff" stroke-width="3"/><text x="8" y="4" fill="#8ebcff">+Z cenit</text>
    </g>
    """
    return svg_document(content, dark=True)


def v_scale(vector: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return vector[0] * scalar, vector[1] * scalar, vector[2] * scalar


def spot_svg(sample: dict[str, object], history: list[dict[str, object]], tolerance_mm: float) -> str:
    valid = bool(sample["spot_valid"])
    u_mm = float(sample["spot_u_mm"])
    v_mm = float(sample["spot_v_mm"])
    radial_mm = float(sample["spot_radial_mm"])
    scenarios = (
        ("Ideal", float(sample.get("ideal_spot_u_mm", u_mm)), float(sample.get("ideal_spot_v_mm", v_mm)), float(sample.get("ideal_spot_radial_mm", radial_mm)), "#16a34a"),
        ("Con error", float(sample.get("error_spot_u_mm", u_mm)), float(sample.get("error_spot_v_mm", v_mm)), float(sample.get("error_spot_radial_mm", radial_mm)), "#ef4444"),
        ("Corregido", float(sample.get("corrected_spot_u_mm", u_mm)), float(sample.get("corrected_spot_v_mm", v_mm)), float(sample.get("corrected_spot_radial_mm", radial_mm)), "#2563eb"),
    )
    finite_radius = max((item[3] for item in scenarios if math.isfinite(item[3])), default=0.0)
    half_range = max(100.0, tolerance_mm * 4.0, finite_radius * 1.20)
    left, top, size = 95.0, 58.0, 410.0
    center_x, center_y = left + size / 2.0, top + size / 2.0

    def map_point(u_value: float, v_value: float) -> tuple[float, float]:
        return (
            center_x + u_value / half_range * size / 2.0,
            center_y - v_value / half_range * size / 2.0,
        )

    trail_points: list[str] = []
    for item in history[-100:]:
        if not bool(item.get("spot_valid", False)):
            continue
        item_u = float(item.get("spot_u_mm", 0.0))
        item_v = float(item.get("spot_v_mm", 0.0))
        if math.isfinite(item_u) and math.isfinite(item_v):
            x, y = map_point(item_u, item_v)
            trail_points.append(f"{x:.1f},{y:.1f}")
    markers: list[str] = []
    for label, scenario_u, scenario_v, _scenario_r, color in scenarios:
        if not (math.isfinite(scenario_u) and math.isfinite(scenario_v)):
            continue
        marker_x, marker_y = map_point(scenario_u, scenario_v)
        markers.append(
            f'<circle cx="{marker_x:.1f}" cy="{marker_y:.1f}" r="9" fill="{color}" '
            f'stroke="#ffffff" stroke-width="3"><title>{html.escape(label)}</title></circle>'
        )
    marker = "".join(markers)
    tolerance_px = tolerance_mm / half_range * size / 2.0
    grid = []
    for tick in range(-4, 5):
        position = left + (tick + 4) * size / 8.0
        grid.append(f'<line x1="{position:.1f}" y1="{top}" x2="{position:.1f}" y2="{top+size}"/>')
        position_y = top + (tick + 4) * size / 8.0
        grid.append(f'<line x1="{left}" y1="{position_y:.1f}" x2="{left+size}" y2="{position_y:.1f}"/>')
    trail = f'<polyline points="{" ".join(trail_points)}" fill="none" stroke="#60a5fa" stroke-width="2" opacity=".7"/>' if len(trail_points) > 1 else ""
    content = f"""
    <text x="34" y="32" fill="#102a43" font-size="22" font-weight="700">Pantalla / spot</text>
    <rect x="{left}" y="{top}" width="{size}" height="{size}" fill="#fffdf5" stroke="#8b6f2b" stroke-width="2"/>
    <g stroke="#d9cfb5" stroke-width="1">{''.join(grid)}</g>
    <line x1="{center_x}" y1="{top}" x2="{center_x}" y2="{top+size}" stroke="#6b5b35" stroke-width="2"/>
    <line x1="{left}" y1="{center_y}" x2="{left+size}" y2="{center_y}" stroke="#6b5b35" stroke-width="2"/>
    <circle cx="{center_x}" cy="{center_y}" r="{tolerance_px:.1f}" fill="none" stroke="#16a34a" stroke-width="3" stroke-dasharray="6 5"/>
    {trail}{marker}
    <text x="{center_x}" y="{top+size+34}" text-anchor="middle" fill="#334155" font-size="13">u [mm] · oeste positivo · rango ±{half_range:.1f}</text>
    <text x="34" y="{center_y}" transform="rotate(-90 34 {center_y})" text-anchor="middle" fill="#334155" font-size="13">v [mm] · cenit positivo</text>
    <g transform="translate(560 70)">
      <rect width="395" height="380" rx="14" fill="#ffffff" stroke="#cad5df"/>
      <text x="24" y="42" fill="#102a43" font-size="21" font-weight="700">Lectura actual</text>
      <text x="24" y="84" fill="#334155" font-size="16">Horizontal u</text><text x="365" y="84" text-anchor="end" fill="#0f4c5c" font-size="18" font-weight="700">{number(u_mm)} mm</text>
      <text x="24" y="120" fill="#334155" font-size="16">Vertical v</text><text x="365" y="120" text-anchor="end" fill="#0f4c5c" font-size="18" font-weight="700">{number(v_mm)} mm</text>
      <text x="24" y="156" fill="#334155" font-size="16">Error radial</text><text x="365" y="156" text-anchor="end" fill="#dc2626" font-size="18" font-weight="700">{number(radial_mm)} mm</text>
      <text x="24" y="192" fill="#334155" font-size="16">Tolerancia</text><text x="365" y="192" text-anchor="end" fill="#16834f" font-size="18" font-weight="700">{tolerance_mm:.2f} mm</text>
      <text x="24" y="224" fill="#16a34a" font-size="15" font-weight="700">Ideal</text><text x="365" y="224" text-anchor="end" fill="#16a34a" font-size="15">{number(scenarios[0][3])} mm</text>
      <text x="24" y="252" fill="#ef4444" font-size="15" font-weight="700">Con error</text><text x="365" y="252" text-anchor="end" fill="#ef4444" font-size="15">{number(scenarios[1][3])} mm</text>
      <text x="24" y="280" fill="#2563eb" font-size="15" font-weight="700">Corregido</text><text x="365" y="280" text-anchor="end" fill="#2563eb" font-size="15">{number(scenarios[2][3])} mm</text>
      <rect x="24" y="306" width="341" height="48" rx="8" fill="{'#16834f' if valid and radial_mm <= tolerance_mm else '#b42318'}"/>
      <text x="194" y="336" text-anchor="middle" fill="#ffffff" font-size="15" font-weight="700">{html.escape(str(sample['status']))}</text>
    </g>
    """
    return svg_document(content)


def solar_svg(sample: dict[str, object], path: list[tuple[float, float]]) -> str:
    left, top, width, height = 80.0, 70.0, 820.0, 365.0

    def map_point(azimuth: float, altitude: float) -> tuple[float, float]:
        return left + (azimuth + 180.0) / 360.0 * width, top + (90.0 - altitude) / 90.0 * height

    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (map_point(az, alt) for az, alt in path))
    current_x, current_y = map_point(float(sample["solar_azimuth_deg"]), float(sample["altitude_deg"]))
    grid: list[str] = []
    labels: list[str] = []
    for altitude in range(0, 91, 15):
        _x, y = map_point(-180.0, float(altitude))
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+width}" y2="{y:.1f}"/>')
        labels.append(f'<text x="{left-15}" y="{y+4:.1f}" text-anchor="end">{altitude}</text>')
    for azimuth in range(-180, 181, 45):
        x, _y = map_point(float(azimuth), 0.0)
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+height}"/>')
        labels.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle">{azimuth}</text>')
    content = f"""
    <text x="30" y="34" fill="#102a43" font-size="22" font-weight="700">Trayectoria solar del dia</text>
    <rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#ffffff" stroke="#cbd5e1"/>
    <g stroke="#e2e8f0">{''.join(grid)}</g>
    <g fill="#475569" font-size="12">{''.join(labels)}</g>
    <polyline points="{points}" fill="none" stroke="#d98b00" stroke-width="4"/>
    <line x1="{current_x:.1f}" y1="{top}" x2="{current_x:.1f}" y2="{top+height}" stroke="#ef4444" stroke-dasharray="5 5" opacity=".7"/>
    <line x1="{left}" y1="{current_y:.1f}" x2="{left+width}" y2="{current_y:.1f}" stroke="#ef4444" stroke-dasharray="5 5" opacity=".7"/>
    <circle cx="{current_x:.1f}" cy="{current_y:.1f}" r="8" fill="#ef4444" stroke="#fff" stroke-width="3"/>
    <text x="{left+width/2}" y="{top+height+52}" text-anchor="middle" fill="#334155" font-size="13">Acimut de laboratorio [deg]: este − · sur 0 · oeste +</text>
    <g transform="translate(625 18)"><rect width="305" height="42" rx="8" fill="#102638"/><text x="16" y="27" fill="#ffffff" font-size="13">Alt {number(sample['altitude_deg'])}° · Az {number(sample['solar_azimuth_deg'])}° · Zenit {number(sample['zenith_deg'])}°</text></g>
    """
    return svg_document(content)


def spot_heat_color(value: float, maximum: float) -> str:
    ratio = max(0.0, min(1.0, value / maximum if maximum > 1e-18 else 0.0))
    stops = (
        (0.00, (3, 7, 18)),
        (0.25, (20, 76, 124)),
        (0.50, (18, 160, 151)),
        (0.75, (250, 204, 21)),
        (1.00, (239, 68, 68)),
    )
    for index in range(len(stops) - 1):
        left, left_color = stops[index]
        right, right_color = stops[index + 1]
        if ratio <= right:
            fraction = (ratio - left) / max(1e-9, right - left)
            rgb = tuple(round(a + (b - a) * fraction) for a, b in zip(left_color, right_color))
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return "#ef4444"


def facet_shape_svg(x: float, y: float, radius: float, shape: str, fill: str) -> str:
    radius = max(3.0, min(13.0, radius))
    if shape == "Circular":
        body = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" />'
    elif shape == "Hexagonal":
        points = []
        for vertex in range(6):
            angle = math.radians(-90.0 + vertex * 60.0)
            points.append(f"{x + radius * math.cos(angle):.1f},{y + radius * math.sin(angle):.1f}")
        body = f'<polygon points="{" ".join(points)}" />'
    else:
        body = f'<rect x="{x-radius:.1f}" y="{y-radius:.1f}" width="{2*radius:.1f}" height="{2*radius:.1f}" rx="2" />'
    return f'<g fill="{fill}" stroke="#f8fafc" stroke-width="1.2">{body}</g>'


def facets_svg(
    state: WebTwinState,
    analysis: dict[str, object],
    view_mode: str,
    display_mode: str,
) -> str:
    if not state.facet_enabled:
        return svg_document(
            '<text x="500" y="230" text-anchor="middle" fill="#64748b" font-size="22" font-weight="700">Modelo de facetas desactivado</text>'
            '<text x="500" y="270" text-anchor="middle" fill="#94a3b8" font-size="14">Activa el modelo para calcular geometria, rayos, impactos e intensidad.</text>'
        )

    facets = list(analysis["facets"])
    results = list(analysis["results"])
    result_by_id = {result.facet_id: result for result in results}
    spot_map = analysis["spot_map"]
    metrics = analysis["spot_metrics"]
    active_count = sum(1 for facet in facets if facet.active)
    header = (
        f"{state.facet_shape} | activas {active_count}/{len(facets)} | "
        f"foco {state.facet_focal_distance_m:.3f} m | "
        f"error max {float(analysis['error_max_m']) * 1000.0:.3f} mm"
    )
    content = [
        '<text x="24" y="30" fill="#102a43" font-size="21" font-weight="700">Facetas: geometria, rayos, foco e intensidad</text>',
        f'<text x="24" y="54" fill="#475569" font-size="12" font-family="monospace">{header}</text>',
    ]

    schematic_box = (24.0, 72.0, 490.0, 342.0)
    receiver_box = (510.0, 72.0, 976.0, 342.0)
    if display_mode == "Esquema ampliado":
        schematic_box = (24.0, 72.0, 976.0, 500.0)
        receiver_box = (0.0, 0.0, 0.0, 0.0)
    elif display_mode == "Receptor ampliado":
        schematic_box = (0.0, 0.0, 0.0, 0.0)
        receiver_box = (24.0, 72.0, 976.0, 500.0)

    if schematic_box[2] > schematic_box[0]:
        x0, y0, x1, y1 = schematic_box
        content.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="10" fill="#0b1722" stroke="#31536a"/>')
        content.append(f'<text x="{x0+14}" y="{y0+24}" fill="#ffffff" font-size="13" font-weight="700">Esquema de rayos · {view_mode}</text>')
        focus = analysis["focus"]
        world_points = [(0.0, 0.0, 0.0), focus]
        world_points.extend(facet.center for facet in facets)
        world_points.extend(result.impact_point for result in results if result.impact_point is not None)

        if view_mode == "Resumen":
            center_y = (y0 + y1) / 2.0 + 8.0
            heliostat_x = x0 + 70.0
            concentrator_x = x1 - 64.0
            focus_x = heliostat_x + (concentrator_x - heliostat_x) * 0.64
            content.append(f'<polygon points="{heliostat_x-34},{center_y+8} {heliostat_x+34},{center_y-8} {heliostat_x+37},{center_y+2} {heliostat_x-31},{center_y+18}" fill="#b9dbea" stroke="#ffffff"/>')
            content.append(f'<line x1="{heliostat_x}" y1="{center_y+12}" x2="{heliostat_x}" y2="{center_y+72}" stroke="#7892a5" stroke-width="5"/>')
            for offset in (-22.0, 0.0, 22.0):
                content.append(f'<line x1="{heliostat_x-34}" y1="{center_y+offset}" x2="{heliostat_x+16}" y2="{center_y+offset}" stroke="#ffb454" stroke-width="2" marker-end="url(#arrow-orange)"/>')
            max_extent = max([max(abs(f.layout_u_m), abs(f.layout_v_m)) for f in facets] + [state.facet_size_m])
            layout_scale = min(130.0, (y1-y0-90.0) / max(0.01, 2.0 * max_extent))
            for facet in facets:
                fx = concentrator_x + facet.layout_u_m * layout_scale
                fy = center_y - facet.layout_v_m * layout_scale
                content.append(facet_shape_svg(fx, fy, state.facet_size_m * layout_scale * 0.43, facet.shape, "#d6b95f" if facet.active else "#5f6570"))
                if facet.active:
                    result = result_by_id.get(facet.id)
                    impact_offset = 0.0 if result is None or not math.isfinite(result.impact_v_m) else max(-55.0, min(55.0, result.impact_v_m * 1200.0))
                    content.append(f'<line x1="{fx:.1f}" y1="{fy:.1f}" x2="{focus_x:.1f}" y2="{center_y-impact_offset:.1f}" stroke="#66d9ef" stroke-width="1.2"/>')
            content.append(f'<line x1="{focus_x}" y1="{center_y-58}" x2="{focus_x}" y2="{center_y+58}" stroke="#58d6e7" stroke-width="2"/>')
            content.append(f'<text x="{heliostat_x}" y="{center_y+94}" text-anchor="middle" fill="#dbeafe" font-size="10">Heliostato móvil</text>')
            content.append(f'<text x="{focus_x}" y="{center_y-66}" text-anchor="middle" fill="#8ce8f2" font-size="10">Plano receptor / foco</text>')
        else:
            def raw_projection(point: tuple[float, float, float]) -> tuple[float, float]:
                px, py, pz = point
                if view_mode == "Superior X-Y":
                    return py, px
                if view_mode == "Lateral Y-Z":
                    return py, pz
                return px - 0.65 * py, pz - 0.25 * px - 0.22 * py

            projected = [raw_projection(point) for point in world_points]
            min_x = min(point[0] for point in projected)
            max_x = max(point[0] for point in projected)
            min_y = min(point[1] for point in projected)
            max_y = max(point[1] for point in projected)
            scale = min((x1-x0-70.0) / max(0.05, max_x-min_x), (y1-y0-70.0) / max(0.05, max_y-min_y))
            middle_x = (min_x + max_x) / 2.0
            middle_y = (min_y + max_y) / 2.0
            def project(point: tuple[float, float, float]) -> tuple[float, float]:
                raw_x, raw_y = raw_projection(point)
                return ((x0+x1)/2.0 + (raw_x-middle_x)*scale, (y0+y1)/2.0 - (raw_y-middle_y)*scale + 10.0)

            hx, hy = project((0.0, 0.0, 0.0))
            focus_x, focus_y = project(focus)
            content.append(f'<rect x="{hx-24}" y="{hy-8}" width="48" height="16" fill="#b9dbea" stroke="#ffffff" transform="rotate(-12 {hx} {hy})"/>')
            content.append(f'<line x1="{hx}" y1="{hy+7}" x2="{hx}" y2="{hy+38}" stroke="#7892a5" stroke-width="4"/>')
            for offset in (-14.0, 0.0, 14.0):
                content.append(f'<line x1="{hx-24}" y1="{hy+offset}" x2="{hx+20}" y2="{hy+offset}" stroke="#ffb454" stroke-width="2"/>')
            content.append(f'<circle cx="{focus_x}" cy="{focus_y}" r="6" fill="#58d6e7" stroke="#ffffff"/>')
            for facet in facets:
                fx, fy = project(facet.center)
                content.append(facet_shape_svg(fx, fy, facet.size * scale * 0.42, facet.shape, "#d6b95f" if facet.active else "#5f6570"))
                result = result_by_id.get(facet.id)
                if facet.active and result is not None:
                    endpoint = result.impact_point or focus
                    ex, ey = project(endpoint)
                    content.append(f'<line x1="{fx}" y1="{fy}" x2="{ex}" y2="{ey}" stroke="#66d9ef" stroke-width="1.1"/>')
            content.append(f'<text x="{x0+14}" y="{y1-14}" fill="#cbd5e1" font-size="10">n/facetas: dorado activo, gris inactivo · incidente naranja · reflejado cian</text>')

    if receiver_box[2] > receiver_box[0]:
        x0, y0, x1, y1 = receiver_box
        content.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="10" fill="#fffdf5" stroke="#8a7b58"/>')
        content.append(f'<text x="{x0+14}" y="{y0+24}" fill="#102a43" font-size="13" font-weight="700">Plano receptor / foco e intensidad</text>')
        map_size = min(y1-y0-68.0, (x1-x0)*0.58)
        left = x0 + 24.0
        top = y0 + 42.0
        center_x = left + map_size/2.0
        center_y = top + map_size/2.0
        half_range = spot_map.half_size_m if spot_map is not None else max(0.005, float(analysis["error_max_m"])*1.25)
        if spot_map is not None:
            display_resolution = min(31, spot_map.resolution)
            cell = map_size / display_resolution
            maximum = max(spot_map.intensity, default=0.0)
            for row in range(display_resolution):
                source_row = round(row * (spot_map.resolution-1) / max(1, display_resolution-1))
                for column in range(display_resolution):
                    source_column = round(column * (spot_map.resolution-1) / max(1, display_resolution-1))
                    value = spot_map.value(source_row, source_column)
                    draw_x = left + column*cell
                    draw_y = top + map_size - (row+1)*cell
                    content.append(f'<rect x="{draw_x:.1f}" y="{draw_y:.1f}" width="{cell+0.6:.1f}" height="{cell+0.6:.1f}" fill="{spot_heat_color(value, maximum)}"/>')
        else:
            content.append(f'<rect x="{left}" y="{top}" width="{map_size}" height="{map_size}" fill="#f8fafc"/>')
        content.append(f'<rect x="{left}" y="{top}" width="{map_size}" height="{map_size}" fill="none" stroke="#334155"/>')
        content.append(f'<line x1="{left}" y1="{center_y}" x2="{left+map_size}" y2="{center_y}" stroke="#a89b78"/>')
        content.append(f'<line x1="{center_x}" y1="{top}" x2="{center_x}" y2="{top+map_size}" stroke="#a89b78"/>')
        pixels_per_m = map_size / (2.0*half_range)
        for result in results:
            if not (math.isfinite(result.impact_u_m) and math.isfinite(result.impact_v_m)):
                continue
            px = max(left, min(left+map_size, center_x + result.impact_u_m*pixels_per_m))
            py = max(top, min(top+map_size, center_y - result.impact_v_m*pixels_per_m))
            content.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#ffffff" stroke="#b42318"/>')
            if len(facets) <= 18 or result.facet_id == state.facet_selected_id:
                content.append(f'<text x="{px+6:.1f}" y="{py-5:.1f}" fill="#b42318" font-size="8">{result.facet_id}</text>')
        details_x = left + map_size + 20.0
        if spot_map is None:
            detail_lines = ["Mapa desactivado", f"Impactos: {len(results)}", f"Rango: +/- {half_range*1000.0:.1f} mm"]
        else:
            detail_lines = [
                f"Activas: {active_count}/{len(facets)}",
                f"Centroide u: {metrics.centroid_u_m*1000.0:+.3f} mm",
                f"Centroide v: {metrics.centroid_v_m*1000.0:+.3f} mm",
                f"Error centroide: {metrics.centroid_error_m*1000.0:.3f} mm",
                f"Diametro eq.: {metrics.equivalent_diameter_m*1000.0:.3f} mm",
                f"Sigma mayor: {metrics.major_sigma_m*1000.0:.3f} mm",
                f"Sigma menor: {metrics.minor_sigma_m*1000.0:.3f} mm",
                f"Orientacion: {metrics.orientation_deg:+.2f} deg",
                f"Forma: {metrics.shape}",
                f"Normalizacion: {spot_map.normalization}",
            ]
        for index, line in enumerate(detail_lines):
            content.append(f'<text x="{details_x}" y="{top+18+index*20}" fill="#334155" font-size="10" font-family="monospace">{line}</text>')
        content.append(f'<text x="{center_x}" y="{top+map_size+18}" text-anchor="middle" fill="#475569" font-size="9">u [mm] oeste + · v [mm] cenit +</text>')

    if display_mode == "Vista general":
        table_y = 374.0
        content.append(f'<text x="24" y="{table_y}" fill="#102a43" font-size="13" font-weight="700">Resultados por faceta</text>')
        visible = facets[:18]
        for index, facet in enumerate(visible):
            column = index // 6
            row = index % 6
            x = 24.0 + column*320.0
            y = table_y + 24.0 + row*24.0
            result = result_by_id.get(facet.id)
            if not facet.active:
                detail, color = "INACTIVA · sin contribucion", "#64748b"
            elif result is None or not math.isfinite(result.focus_error_m):
                detail, color = "sin cruce con receptor", "#b42318"
            else:
                detail = f"u {result.impact_u_m*1000.0:+7.3f} | v {result.impact_v_m*1000.0:+7.3f} | err {result.focus_error_m*1000.0:7.3f} mm"
                color = "#16834f" if result.focus_error_m < 1e-6 else "#b42318"
            content.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="9" font-family="monospace">{facet.id}: {detail}</text>')
        if len(facets) > len(visible):
            content.append(f'<text x="976" y="{table_y}" text-anchor="end" fill="#64748b" font-size="9">Se muestran 18 de {len(facets)}; todos se calculan.</text>')

    defs = '<defs><marker id="arrow-orange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#ffb454"/></marker></defs>'
    return svg_document(defs + "".join(content), width=1000, height=540)


def control_section(title: str, *children: object, opened: bool = False) -> object:
    attributes = {"class": "control-section"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(title),
        ui.div(*children, class_="control-section-body"),
        **attributes,
    )


def manual_chapter(title: str, *children: object, opened: bool = False) -> object:
    attributes = {"class": "manual-chapter"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(title),
        ui.div(*children, class_="manual-chapter-body"),
        **attributes,
    )


def manual_visual_overview() -> object:
    steps = (
        ("01", "Reloj", "Fecha, hora y zona UTC"),
        ("02", "Sol", "Altura, acimut y vector S"),
        ("03", "Objetivo", "Vector R hacia el receptor"),
        ("04", "Orientación", "Normal ideal y motores"),
        ("05", "Reflexión", "Rayo reflejado por N"),
        ("06", "Impacto", "Coordenadas u, v y error"),
        ("07", "Facetas", "Rayos e intensidad"),
        ("08", "Resultados", "Gráficas, diagnóstico y CSV"),
    )
    return ui.div(
        ui.div(
            ui.h3("Cómo fluye la simulación"),
            ui.p("El programa transforma las entradas en resultados siguiendo siempre esta cadena."),
            class_="manual-section-heading",
        ),
        ui.div(
            *(
                ui.div(
                    ui.span(number_text, class_="flow-number"),
                    ui.strong(title),
                    ui.tags.small(description),
                    class_="flow-step",
                )
                for number_text, title, description in steps
            ),
            class_="manual-flow",
        ),
        ui.div(
            ui.div(
                ui.div(
                    ui.span("Z", class_="axis-letter axis-z-letter"),
                    ui.span("+ cenit", class_="axis-label axis-z-label"),
                    ui.span("X", class_="axis-letter axis-x-letter"),
                    ui.span("+ oeste / − este", class_="axis-label axis-x-label"),
                    ui.span("Y", class_="axis-letter axis-y-letter"),
                    ui.span("+ sur / − norte", class_="axis-label axis-y-label"),
                    ui.span(class_="axis-origin"),
                    ui.span(class_="axis-line axis-x"),
                    ui.span(class_="axis-line axis-y"),
                    ui.span(class_="axis-line axis-z"),
                    class_="axis-diagram",
                ),
                ui.div(
                    ui.h4("Orientación local"),
                    ui.p("La misma convención se usa en el modelo 3D, el target, las facetas y los impactos."),
                ),
                class_="visual-card orientation-card",
            ),
            ui.div(
                ui.h4("Lectura rápida de estados"),
                ui.div(ui.span(class_="status-dot status-green"), ui.span("Verde · cálculo estable o en objetivo")),
                ui.div(ui.span(class_="status-dot status-blue"), ui.span("Azul · configuración o referencia")),
                ui.div(ui.span(class_="status-dot status-gold"), ui.span("Dorado · movimiento o advertencia")),
                ui.div(ui.span(class_="status-dot status-red"), ui.span("Rojo · pausa o condición no válida")),
                class_="visual-card state-legend-card",
            ),
            ui.div(
                ui.h4("Tres lecturas esenciales"),
                ui.div(ui.strong("AZ / EL"), ui.span("Pose y objetivo del heliostato"), class_="reading-row"),
                ui.div(ui.strong("u / v"), ui.span("Posición del impacto en el receptor"), class_="reading-row"),
                ui.div(ui.strong("r"), ui.span("Distancia radial al centro"), class_="reading-row"),
                class_="visual-card",
            ),
            class_="manual-visual-grid",
        ),
        class_="manual-visual-overview",
    )


def formula_card(title: str, formula_html: str, explanation: str, variables: str) -> object:
    return ui.div(
        ui.div(title, class_="formula-title"),
        ui.div(ui.HTML(formula_html), class_="formula-expression"),
        ui.p(explanation, class_="formula-explanation"),
        ui.div(variables, class_="formula-variables"),
        class_="formula-card",
    )


def mathematics_panel() -> object:
    return ui.div(
        ui.div(
            ui.div("REFERENCIA MATEMÁTICA", class_="manual-kicker"),
            ui.h2("Ecuaciones que realmente ejecuta el simulador"),
            ui.p("Las expresiones siguen la convención +X oeste, +Y sur y +Z cenit. Los vectores con sombrero son unitarios."),
            class_="manual-hero math-hero",
        ),
        ui.div(
            ui.span("Reloj solar"), ui.span("→"), ui.span("Vectores"), ui.span("→"),
            ui.span("Normal"), ui.span("→"), ui.span("Reflexión"), ui.span("→"),
            ui.span("Impacto"), ui.span("→"), ui.span("Facetas e intensidad"),
            class_="math-process-strip",
        ),
        ui.h3("1. Posición solar"),
        ui.div(
            formula_card(
                "Ángulo anual auxiliar",
                '<math display="block" aria-label="B igual a dos pi por n menos 81 entre 364"><mi>B</mi><mo>=</mo><mfrac><mrow><mn>2</mn><mi>π</mi><mo>(</mo><mi>n</mi><mo>−</mo><mn>81</mn><mo>)</mo></mrow><mn>364</mn></mfrac></math>',
                "Transforma el número de día del año en una fase anual usada por la ecuación del tiempo.",
                "n: día del año · B: radianes",
            ),
            formula_card(
                "Ecuación del tiempo",
                '<math display="block" aria-label="E T igual a 9.87 seno de 2B menos 7.53 coseno B menos 1.5 seno B"><mi>E</mi><mi>T</mi><mo>=</mo><mn>9.87</mn><mi>sin</mi><mo>(</mo><mn>2</mn><mi>B</mi><mo>)</mo><mo>−</mo><mn>7.53</mn><mi>cos</mi><mo>(</mo><mi>B</mi><mo>)</mo><mo>−</mo><mn>1.5</mn><mi>sin</mi><mo>(</mo><mi>B</mi><mo>)</mo></math>',
                "Corrige la diferencia entre hora civil y hora solar aparente.",
                "ET: minutos",
            ),
            formula_card(
                "Declinación solar",
                '<math display="block" aria-label="delta igual a 23.45 grados por seno"><mi>δ</mi><mo>=</mo><mn>23.45</mn><mo>°</mo><mi>sin</mi><mrow><mo>[</mo><mfrac><mrow><mn>2</mn><mi>π</mi><mo>(</mo><mn>284</mn><mo>+</mo><mi>n</mi><mo>)</mo></mrow><mn>365</mn></mfrac><mo>]</mo></mrow></math>',
                "Aproxima la inclinación aparente del Sol respecto al ecuador terrestre.",
                "δ: grados solares",
            ),
            formula_card(
                "Altura solar",
                '<math display="block" aria-label="seno de alfa"><mi>sin</mi><mi>α</mi><mo>=</mo><mi>sin</mi><mi>φ</mi><mi>sin</mi><mi>δ</mi><mo>+</mo><mi>cos</mi><mi>φ</mi><mi>cos</mi><mi>δ</mi><mi>cos</mi><mi>ω</mi></math>',
                "Calcula la altura sobre el horizonte usando latitud, declinación y ángulo horario.",
                "α: altura · φ: latitud · ω: ángulo horario",
            ),
            class_="formula-grid",
        ),
        ui.p("D&B usa estas aproximaciones. REDA conserva la misma estructura y agrega pequeñas correcciones armónicas para comparación.", class_="math-note"),
        ui.h3("2. Geometría óptica del heliostato"),
        ui.div(
            formula_card(
                "Vector solar",
                '<math display="block" aria-label="vector S"><mover><mi>S</mi><mo>^</mo></mover><mo>=</mo><mo>(</mo><mi>cos</mi><mi>α</mi><mi>sin</mi><mi>A</mi><mo>,</mo><mi>cos</mi><mi>α</mi><mi>cos</mi><mi>A</mi><mo>,</mo><mi>sin</mi><mi>α</mi><mo>)</mo></math>',
                "Convierte altura y acimut solar al sistema cartesiano del laboratorio.",
                "A: acimut, 0° sur y positivo al oeste",
            ),
            formula_card(
                "Dirección al target",
                '<math display="block" aria-label="T unitario igual a R sobre norma de R"><mover><mi>T</mi><mo>^</mo></mover><mo>=</mo><mfrac><mover><mi>R</mi><mo>→</mo></mover><mrow><mo>‖</mo><mover><mi>R</mi><mo>→</mo></mover><mo>‖</mo></mrow></mfrac><mo>,</mo><mover><mi>R</mi><mo>→</mo></mover><mo>=</mo><mo>(</mo><mi>RX</mi><mo>,</mo><mi>RY</mi><mo>,</mo><mi>RZ</mi><mo>)</mo></math>',
                "Normaliza las coordenadas del receptor medidas desde el centro óptico del espejo.",
                "R: metros · T: vector unitario",
            ),
            formula_card(
                "Normal ideal",
                '<math display="block" aria-label="N unitario igual a S más T normalizado"><mover><mi>N</mi><mo>^</mo></mover><mo>=</mo><mfrac><mrow><mover><mi>S</mi><mo>^</mo></mover><mo>+</mo><mover><mi>T</mi><mo>^</mo></mover></mrow><mrow><mo>‖</mo><mover><mi>S</mi><mo>^</mo></mover><mo>+</mo><mover><mi>T</mi><mo>^</mo></mover><mo>‖</mo></mrow></mfrac></math>',
                "La bisectriz entre la dirección solar y el objetivo determina la orientación ideal del espejo.",
                "N: normal óptica unitaria",
            ),
            formula_card(
                "Normal desde AZ/EL",
                '<math display="block" aria-label="normal desde acimut y elevación"><mover><mi>N</mi><mo>^</mo></mover><mo>=</mo><mo>(</mo><mi>cos</mi><mi>EL</mi><mi>sin</mi><mi>AZ</mi><mo>,</mo><mi>cos</mi><mi>EL</mi><mi>cos</mi><mi>AZ</mi><mo>,</mo><mi>sin</mi><mi>EL</mi><mo>)</mo></math>',
                "Reconstruye la normal real a partir de la pose simulada y de los errores activos.",
                "AZ, EL: grados convertidos internamente a radianes",
            ),
            formula_card(
                "Ley de reflexión",
                '<math display="block" aria-label="dirección reflejada"><msub><mover><mi>d</mi><mo>→</mo></mover><mi>r</mi></msub><mo>=</mo><msub><mover><mi>d</mi><mo>→</mo></mover><mi>i</mi></msub><mo>−</mo><mn>2</mn><mo>(</mo><msub><mover><mi>d</mi><mo>→</mo></mover><mi>i</mi></msub><mo>·</mo><mover><mi>N</mi><mo>^</mo></mover><mo>)</mo><mover><mi>N</mi><mo>^</mo></mover></math>',
                "Refleja la dirección incidente di = −S sobre la normal real del espejo.",
                "dr: rayo reflejado · di: rayo incidente",
            ),
            class_="formula-grid",
        ),
        ui.h3("3. Intersección con el receptor"),
        ui.div(
            formula_card(
                "Parámetro de intersección",
                '<math display="block" aria-label="lambda de intersección"><mi>λ</mi><mo>=</mo><mfrac><mrow><mo>(</mo><mover><mi>R</mi><mo>→</mo></mover><mo>−</mo><mover><mi>O</mi><mo>→</mo></mover><mo>)</mo><mo>·</mo><msub><mover><mi>n</mi><mo>^</mo></mover><mi>r</mi></msub></mrow><mrow><msub><mover><mi>d</mi><mo>→</mo></mover><mi>r</mi></msub><mo>·</mo><msub><mover><mi>n</mi><mo>^</mo></mover><mi>r</mi></msub></mrow></mfrac></math>',
                "Encuentra dónde el rayo cruza el plano receptor. Si el denominador es casi cero o λ ≤ 0, no existe impacto frontal válido.",
                "O: origen del rayo · nr = R/‖R‖",
            ),
            formula_card(
                "Punto de impacto",
                '<math display="block" aria-label="P de lambda"><mover><mi>P</mi><mo>→</mo></mover><mo>(</mo><mi>λ</mi><mo>)</mo><mo>=</mo><mover><mi>O</mi><mo>→</mo></mover><mo>+</mo><mi>λ</mi><msub><mover><mi>d</mi><mo>→</mo></mover><mi>r</mi></msub></math>',
                "El punto se proyecta sobre dos ejes del plano: u horizontal hacia el oeste y v vertical hacia el cenit.",
                "P, O: metros",
            ),
            formula_card(
                "Error radial",
                '<math display="block" aria-label="error radial"><msub><mi>e</mi><mi>r</mi></msub><mo>=</mo><msqrt><mrow><msup><mi>u</mi><mn>2</mn></msup><mo>+</mo><msup><mi>v</mi><mn>2</mn></msup></mrow></msqrt></math>',
                "Resume en una sola magnitud la distancia entre el impacto y el centro nominal.",
                "u, v, er: metros; la interfaz los muestra en milímetros",
            ),
            class_="formula-grid",
        ),
        ui.h3("4. Movimiento y corrección"),
        ui.div(
            formula_card(
                "Velocidad del eje",
                '<math display="block" aria-label="omega igual PWM por omega máxima"><mi>ω</mi><mo>=</mo><mi>PWM</mi><mo>·</mo><msub><mi>ω</mi><mi>máx</mi></msub></math>',
                "Cada paso se limita para no rebasar el objetivo ni los límites mecánicos.",
                "PWM: 0 a 1 · ω: grados por segundo",
            ),
            formula_card(
                "Corrección incremental",
                '<math display="block" aria-label="corrección nueva"><msub><mi>c</mi><mi>nueva</mi></msub><mo>=</mo><msub><mi>c</mi><mi>actual</mi></msub><mo>+</mo><mi>g</mi><mo>(</mo><mo>−</mo><mi>e</mi><mo>−</mo><msub><mi>c</mi><mi>actual</mi></msub><mo>)</mo></math>',
                "CORREGIR AHORA elimina una fracción g del error restante; por eso converge progresivamente.",
                "g: ganancia de 0 a 1 · e: offset más deriva acumulada",
            ),
            class_="formula-grid",
        ),
        ui.h3("5. Facetas y mapa de intensidad"),
        ui.div(
            formula_card(
                "Foco del concentrador",
                '<math display="block" aria-label="foco igual R menos focal por normal"><mover><mi>F</mi><mo>→</mo></mover><mo>=</mo><mover><mi>R</mi><mo>→</mo></mover><mo>−</mo><mi>f</mi><msub><mover><mi>n</mi><mo>^</mo></mover><mi>r</mi></msub></math>',
                "Sitúa el plano de enfoque a una distancia focal f hacia el heliostato.",
                "f: distancia focal en metros",
            ),
            formula_card(
                "Normal de cada faceta",
                '<math display="block" aria-label="normal de faceta"><msub><mover><mi>N</mi><mo>^</mo></mover><mi>k</mi></msub><mo>=</mo><mfrac><mrow><msub><mover><mi>d</mi><mo>^</mo></mover><mi>i</mi></msub><mo>−</mo><msub><mover><mi>a</mi><mo>^</mo></mover><mi>k</mi></msub></mrow><mrow><mo>‖</mo><msub><mover><mi>d</mi><mo>^</mo></mover><mi>i</mi></msub><mo>−</mo><msub><mover><mi>a</mi><mo>^</mo></mover><mi>k</mi></msub><mo>‖</mo></mrow></mfrac></math>',
                "Orienta el rayo central de la faceta k hacia el foco; después pueden aplicarse desalineaciones H/V.",
                "ak: dirección desde la faceta k al foco",
            ),
            formula_card(
                "Gaussiana elíptica",
                '<math display="block" aria-label="intensidad gaussiana"><mi>I</mi><mo>(</mo><mi>u</mi><mo>,</mo><mi>v</mi><mo>)</mo><mo>=</mo><mi>w</mi><mi>exp</mi><mrow><mo>{</mo><mo>−</mo><mfrac><mn>1</mn><mn>2</mn></mfrac><mo>[</mo><msup><mrow><mo>(</mo><mfrac><mi>a</mi><msub><mi>σ</mi><mi>mayor</mi></msub></mfrac><mo>)</mo></mrow><mn>2</mn></msup><mo>+</mo><msup><mrow><mo>(</mo><mfrac><mi>b</mi><msub><mi>σ</mi><mi>menor</mi></msub></mfrac><mo>)</mo></mrow><mn>2</mn></msup><mo>]</mo><mo>}</mo></mrow></math>',
                "Cada impacto aporta una mancha; el programa suma todas las contribuciones activas hasta 3.5σ.",
                "σmenor = σbase · σmayor = σbase/|cos(incidencia)|",
            ),
            formula_card(
                "Centroide energético",
                '<math display="block" aria-label="centroide u"><mover><mi>u</mi><mo>¯</mo></mover><mo>=</mo><mfrac><mrow><mo>∑</mo><mi>I</mi><mi>u</mi></mrow><mrow><mo>∑</mo><mi>I</mi></mrow></mfrac><mo>,</mo><mover><mi>v</mi><mo>¯</mo></mover><mo>=</mo><mfrac><mrow><mo>∑</mo><mi>I</mi><mi>v</mi></mrow><mrow><mo>∑</mo><mi>I</mi></mrow></mfrac></math>',
                "La covarianza alrededor del centroide produce sigma mayor, sigma menor y orientación del spot.",
                "La forma se clasifica como circular, elíptica o alargada",
            ),
            class_="formula-grid",
        ),
        ui.div(
            ui.strong("Supuestos del modelo"),
            ui.span("Óptica geométrica con rayos centrales, receptor plano, facetas rígidas y spot gaussiano aproximado. No se modelan sombras, clima, deformación térmica ni potencia radiométrica absoluta."),
            class_="math-warning",
        ),
        class_="manual-panel mathematics-panel",
    )


def about_panel() -> object:
    capabilities = (
        ("SOL", "Posición solar D&B y canal REDA aproximado"),
        ("3D", "Heliostato, receptor, riel, vectores y cámara libre"),
        ("SPOT", "Impacto u/v, tolerancia y error radial"),
        ("FACETAS", "Acomodo, rayos, desalineación e intensidad"),
        ("TIEMPO", "Reloj real o simulado con multiplicador"),
        ("DATOS", "Historial local, diagnóstico y exportación CSV"),
    )
    return ui.div(
        ui.div(
            ui.div("ACERCA DEL PROGRAMA", class_="manual-kicker"),
            ui.h2("Gemelo digital didáctico del mini horno solar"),
            ui.p("La edición web ejecuta la física y los gráficos en la máquina que abre la página mediante Python en WebAssembly. No requiere instalar el programa de escritorio ni envía la simulación a un servidor."),
            class_="manual-hero about-hero",
        ),
        ui.div(
            *(ui.div(ui.strong(code), ui.span(description), class_="capability-card") for code, description in capabilities),
            class_="capability-grid",
        ),
        ui.div(
            ui.div(
                ui.h3("Propósito"),
                ui.p("Estudiar la geometría solar, el seguimiento de dos ejes, los errores de puntería, la corrección y el comportamiento de un concentrador facetado antes de realizar pruebas físicas."),
            ),
            ui.div(
                ui.h3("Arquitectura"),
                ui.p("El núcleo matemático está escrito en Python. Shiny coordina controles y resultados. Three.js representa el gemelo 3D. Shinylive/Pyodide ejecuta todo localmente dentro del navegador."),
            ),
            ui.div(
                ui.h3("Unidades y convención"),
                ui.p("Metros, grados, grados por segundo y milímetros en las lecturas del receptor. +X oeste, +Y sur, +Z cenit; AZ 0° al sur."),
            ),
            ui.div(
                ui.h3("Alcance"),
                ui.p("Es un simulador educativo y de ingeniería preliminar. No sustituye medición experimental, análisis estructural, trazado radiométrico ni validación de seguridad."),
            ),
            class_="about-grid",
        ),
        ui.div(
            ui.h3("Flujo conceptual"),
            manual_visual_overview(),
            class_="about-flow-block",
        ),
        ui.div(
            ui.strong("Versión web 0.4.0"),
            ui.span("Guía ilustrada, manual completo y referencia matemática integrados."),
            class_="version-card",
        ),
        class_="manual-panel about-panel",
    )


def guide_stage(number_text: str, icon: str, title: str, caption: str, tone: str) -> object:
    return ui.div(
        ui.div(
            ui.span(number_text, class_="guide-stage-number"),
            ui.span(icon, class_="guide-stage-icon", **{"aria-hidden": "true"}),
            class_="guide-stage-top",
        ),
        ui.strong(title),
        ui.span(caption),
        class_=f"guide-stage guide-stage-{tone}",
    )


def guide_screen_card(title: str, caption: str, preview: object, badge: str) -> object:
    return ui.div(
        ui.div(preview, ui.span(badge, class_="screen-badge"), class_="screen-preview"),
        ui.div(ui.strong(title), ui.span(caption), class_="screen-card-copy"),
        class_="guide-screen-card",
    )


def csv_dictionary_section(
    title: str,
    description: str,
    tone: str,
    columns: tuple[tuple[str, str, str], ...],
    opened: bool = False,
) -> object:
    attributes = {"class": f"csv-dictionary-section csv-dictionary-{tone}"}
    if opened:
        attributes["open"] = "open"
    return ui.tags.details(
        ui.tags.summary(
            ui.div(ui.strong(title), ui.span(description)),
            ui.tags.small(f"{len(columns)} columnas"),
        ),
        ui.div(
            ui.div(ui.span("Columna"), ui.span("Qué significa"), ui.span("Unidad / tipo"), class_="csv-dictionary-row csv-dictionary-head"),
            *(
                ui.div(
                    ui.tags.code(name),
                    ui.span(meaning),
                    ui.span(unit, class_="csv-dictionary-unit"),
                    class_="csv-dictionary-row",
                )
                for name, meaning, unit in columns
            ),
            class_="csv-dictionary-table",
        ),
        **attributes,
    )


def csv_guide_panel() -> object:
    column_groups = tuple(
        (
            f"{index:02}",
            title,
            f"{len(columns)} columnas",
            description,
            tone,
        )
        for index, (title, description, tone, columns) in enumerate(CSV_COLUMN_DICTIONARY, 1)
    )
    return ui.div(
        ui.div(
            ui.div(
                ui.span("UNA FILA", class_="csv-flow-badge"),
                ui.strong("Muestra del simulador"),
                ui.span("≈ cada 0.5 s de tiempo real"),
                class_="csv-flow-step",
            ),
            ui.span("→", class_="csv-flow-arrow"),
            ui.div(
                ui.span("166 DATOS", class_="csv-flow-badge"),
                ui.strong("Estado completo de la muestra"),
                ui.span("tiempo · seguimiento · spot · geometría"),
                class_="csv-flow-step",
            ),
            ui.span("→", class_="csv-flow-arrow"),
            ui.div(
                ui.span("HASTA 1,200", class_="csv-flow-badge"),
                ui.strong("Historial descargable"),
                ui.span("las muestras más recientes"),
                class_="csv-flow-step",
            ),
            class_="csv-flow",
        ),
        ui.div(
            ui.div(
                ui.div(ui.span("timestamp"), ui.span("mode"), ui.span("az_deg"), ui.span("el_deg"), ui.span("spot_u_mm"), ui.span("spot_v_mm"), ui.span("status"), class_="csv-table-row csv-table-head"),
                ui.div(ui.span("12:00:00"), ui.span("Auto"), ui.span("0.00"), ui.span("90.00"), ui.span("0.00"), ui.span("0.00"), ui.span("EN OBJETIVO"), class_="csv-table-row"),
                ui.div(ui.span("12:00:30"), ui.span("Auto"), ui.span("0.04"), ui.span("89.97"), ui.span("−1.12"), ui.span("+0.64"), ui.span("MOVIENDO"), class_="csv-table-row"),
                ui.div(ui.span("12:01:00"), ui.span("Auto"), ui.span("0.08"), ui.span("89.94"), ui.span("−0.21"), ui.span("+0.09"), ui.span("EN OBJETIVO"), class_="csv-table-row"),
                class_="csv-table",
            ),
            ui.div(
                ui.strong("Ejemplo simplificado"),
                ui.p("El archivo real contiene 166 columnas documentadas. Cada fila es una fotografía numérica del simulador en ese instante; no es una imagen."),
                ui.div(ui.span("SIN HISTORIAL"), ui.span("Se exporta la lectura actual como una sola fila."), class_="csv-single-row-note"),
                class_="csv-table-caption",
            ),
            class_="csv-table-card",
        ),
        ui.div(
            *(
                ui.div(
                    ui.span(number_text, class_="csv-group-number"),
                    ui.div(ui.strong(title), ui.tags.small(count)),
                    ui.p(description),
                    class_=f"csv-group-card csv-group-{tone}",
                )
                for number_text, title, count, description, tone in column_groups
            ),
            class_="csv-group-grid",
        ),
        ui.div(
            ui.div(
                ui.div("DICCIONARIO DE DATOS", class_="guide-section-kicker"),
                ui.h4("Significado de cada columna"),
                ui.p("Abre cada grupo para consultar el nombre escrito en el archivo, su interpretación y la unidad o tipo de dato."),
                class_="csv-dictionary-heading",
            ),
            *(
                csv_dictionary_section(title, description, tone, columns, opened=index == 0)
                for index, (title, description, tone, columns) in enumerate(CSV_COLUMN_DICTIONARY)
            ),
            class_="csv-dictionary",
        ),
        ui.div(
            ui.strong("El CSV no guarda"),
            ui.span("gráficas o capturas · la malla de la escena 3D · cada celda individual del mapa · cada rayo individual por faceta · la bitácora de eventos"),
            class_="csv-not-included",
        ),
        ui.div(
            ui.strong("EXPORTAR PAQUETE"),
            ui.span("crea un ZIP con historial.csv, facetas.csv, eventos.csv y un archivo LEEME. Es la opción recomendada para conservar un experimento completo."),
            class_="csv-not-included",
        ),
        class_="csv-guide-panel",
    )


def visual_guide_panel() -> object:
    interface_map = ui.div(
        ui.div(
            ui.div(
                ui.span("GEMELO DIGITAL", class_="anatomy-kicker"),
                ui.strong("Mini horno solar"),
                class_="anatomy-brand",
            ),
            ui.div(
                ui.span("RELOJ DEL EXPERIMENTO"),
                ui.strong("12:00:00"),
                ui.tags.small("FECHA SIMULADA · ×60"),
                class_="anatomy-clock",
            ),
            class_="anatomy-header",
        ),
        ui.div(
            ui.div(
                ui.div(ui.span("1"), ui.strong("AJUSTES"), class_="anatomy-zone-label anatomy-zone-one"),
                ui.div(
                    ui.strong("MODO DE OPERACIÓN"),
                    ui.div(ui.span(class_="fake-radio active"), ui.span("Automático"), ui.span(class_="fake-radio"), ui.span("Manual"), class_="fake-options"),
                    class_="anatomy-control-group",
                ),
                ui.div(
                    ui.strong("TIEMPO DEL EXPERIMENTO"),
                    ui.div(ui.span(class_="fake-radio"), ui.span("Real"), ui.span(class_="fake-radio active"), ui.span("Simulado"), class_="fake-options"),
                    ui.div(ui.span("2026-08-06"), ui.span("12:00"), class_="fake-input-row"),
                    class_="anatomy-control-group",
                ),
                ui.div(
                    ui.strong("CALIBRACIÓN Y PERFIL"),
                    ui.div("Minihorno IER", ui.span("⌄"), class_="fake-select"),
                    class_="anatomy-control-group",
                ),
                ui.div(
                    ui.strong("FACETAS Y ERRORES"),
                    ui.div(ui.span("Modelo de facetas"), ui.span("ON", class_="fake-switch"), class_="fake-switch-row"),
                    class_="anatomy-control-group",
                ),
                class_="anatomy-sidebar",
            ),
            ui.div(
                ui.div(
                    ui.div(ui.span(class_="anatomy-status-dot"), ui.strong("LISTO PARA CONFIGURAR"), class_="anatomy-status"),
                    ui.div(
                        ui.span("INICIAR", class_="anatomy-action primary"),
                        ui.span("CONFIGURAR", class_="anatomy-action"),
                        ui.span("EXPORTAR CSV", class_="anatomy-action"),
                        class_="anatomy-actions",
                    ),
                    ui.div(ui.span("2"), ui.strong("SESIÓN"), class_="anatomy-zone-label anatomy-zone-two"),
                    class_="anatomy-toolbar",
                ),
                ui.div(
                    ui.div(
                        ui.span("Gemelo 3D", class_="active"),
                        ui.span("Pantalla / spot"),
                        ui.span("Trayectoria solar"),
                        ui.span("Facetas"),
                        ui.span("Diagnóstico"),
                        class_="anatomy-tabs",
                    ),
                    ui.div(
                        ui.div(ui.span("3"), ui.strong("RESULTADOS"), class_="anatomy-zone-label anatomy-zone-three"),
                        ui.span(class_="anatomy-sun"),
                        ui.span("SOL", class_="anatomy-sun-label"),
                        ui.span(class_="anatomy-incoming-ray"),
                        ui.span(class_="anatomy-base"),
                        ui.span(class_="anatomy-pedestal"),
                        ui.span(class_="anatomy-fork anatomy-fork-left"),
                        ui.span(class_="anatomy-fork anatomy-fork-right"),
                        ui.span(class_="anatomy-mirror"),
                        ui.span(class_="anatomy-pivot"),
                        ui.span(class_="anatomy-normal-vector"),
                        ui.span(class_="anatomy-reflected-ray"),
                        ui.span(class_="anatomy-rail anatomy-rail-one"),
                        ui.span(class_="anatomy-rail anatomy-rail-two"),
                        ui.div(*(ui.span(class_="anatomy-facet") for _index in range(12)), class_="anatomy-receiver"),
                        ui.span(class_="anatomy-receiver-stand"),
                        ui.span("HELIOSTATO", class_="anatomy-object-label anatomy-heliostat-label"),
                        ui.span("CONCENTRADOR", class_="anatomy-object-label anatomy-concentrator-label"),
                        ui.div(ui.strong("VISTA ISOMÉTRICA"), ui.span("Clic izquierdo: mover · derecho: girar"), class_="anatomy-scene-note"),
                        class_="anatomy-scene",
                    ),
                    class_="anatomy-workspace",
                ),
                ui.div(
                    ui.div(ui.span("4"), ui.strong("LECTURAS"), class_="anatomy-zone-label anatomy-zone-four"),
                    ui.div(ui.span("ACIMUT"), ui.strong("0.00°"), class_="anatomy-metric"),
                    ui.div(ui.span("ELEVACIÓN"), ui.strong("90.00°"), class_="anatomy-metric"),
                    ui.div(ui.span("ERROR SPOT"), ui.strong("0.00 mm"), class_="anatomy-metric"),
                    ui.div(ui.span("ESTADO"), ui.strong("EN OBJETIVO", class_="metric-good"), class_="anatomy-metric"),
                    class_="anatomy-readouts",
                ),
                class_="anatomy-main",
            ),
            class_="anatomy-body",
        ),
        class_="interface-anatomy",
        **{"aria-label": "Mapa visual de las zonas principales de la aplicación"},
    )

    screen_cards = (
        guide_screen_card(
            "Gemelo 3D",
            "Comprueba pose, orientación y trayectoria óptica.",
            ui.div(
                ui.span(class_="mini-sun"),
                ui.span(class_="mini-ray mini-ray-in"),
                ui.span(class_="mini-mirror"),
                ui.span(class_="mini-ray mini-ray-out"),
                ui.span(class_="mini-target"),
                ui.span(class_="mini-ground"),
                class_="preview-3d",
            ),
            "MOVER · GIRAR · ZOOM",
        ),
        guide_screen_card(
            "Pantalla / spot",
            "Lee u, v y la distancia radial al centro.",
            ui.div(
                ui.span("v", class_="target-v"),
                ui.span("u", class_="target-u"),
                ui.span(class_="target-ring"),
                ui.span(class_="target-center"),
                ui.span(class_="target-hit"),
                ui.span("r", class_="target-radius-label"),
                class_="preview-target",
            ),
            "CENTRO · TOLERANCIA · IMPACTO",
        ),
        guide_screen_card(
            "Trayectoria solar",
            "Relaciona la hora con el acimut y la altura del Sol.",
            ui.div(
                *(ui.span(class_=f"solar-dot solar-dot-{index}") for index in range(1, 10)),
                ui.span(class_="solar-now"),
                ui.span("altura", class_="solar-axis-y"),
                ui.span("acimut", class_="solar-axis-x"),
                class_="preview-solar",
            ),
            "ACIMUT ↔ ALTURA",
        ),
        guide_screen_card(
            "Facetas",
            "Compara acomodo, rayos, impactos e intensidad.",
            ui.div(
                ui.div(*(ui.span(str(index)) for index in range(1, 8)), class_="facet-cluster"),
                ui.div(*(ui.span(class_=f"heat-cell heat-{index}") for index in range(1, 10)), class_="heat-grid"),
                class_="preview-facets",
            ),
            "GEOMETRÍA + MAPA",
        ),
        guide_screen_card(
            "Deriva y corrección",
            "Observa el error acumulado y su convergencia.",
            ui.div(
                ui.span(class_="drift-zero"),
                *(ui.span(class_=f"drift-bar drift-bar-{index}") for index in range(1, 8)),
                ui.span("CORREGIR", class_="drift-action"),
                class_="preview-drift",
            ),
            "ERROR → CORRECCIÓN",
        ),
        guide_screen_card(
            "Diagnóstico",
            "Confirma estado, motores y calidad del seguimiento.",
            ui.div(
                ui.div(ui.span("AZ"), ui.strong("0.03°"), ui.span(class_="diag-good")),
                ui.div(ui.span("EL"), ui.strong("−0.07°"), ui.span(class_="diag-good")),
                ui.div(ui.span("SPOT"), ui.strong("11.18 mm"), ui.span(class_="diag-warn")),
                class_="preview-diagnostics",
            ),
            "ESTADO OPERACIONAL",
        ),
    )

    target_demo = ui.div(
        ui.div(
            ui.span("+v · cenit", class_="demo-v-label"),
            ui.span("+u · oeste", class_="demo-u-label"),
            ui.span(class_="demo-axis demo-axis-h"),
            ui.span(class_="demo-axis demo-axis-v"),
            ui.span(class_="demo-tolerance"),
            ui.span(class_="demo-center"),
            ui.span(class_="demo-impact"),
            ui.span(class_="demo-radius"),
            ui.span("impacto", class_="demo-impact-label"),
            class_="target-demo",
        ),
        ui.div(
            ui.div(ui.strong("u"), ui.span("desplazamiento horizontal"), class_="target-reading target-reading-blue"),
            ui.div(ui.strong("v"), ui.span("desplazamiento vertical"), class_="target-reading target-reading-teal"),
            ui.div(ui.strong("r"), ui.span("distancia total al centro"), class_="target-reading target-reading-red"),
            ui.div(ui.span(class_="status-dot status-green"), ui.span("Dentro del círculo: en tolerancia"), class_="target-legend"),
            ui.div(ui.span(class_="status-dot status-red"), ui.span("Fuera del círculo: revisar seguimiento"), class_="target-legend"),
            class_="target-demo-copy",
        ),
        class_="target-demo-layout",
    )

    return ui.div(
        ui.div(
            ui.div("GUÍA VISUAL", class_="manual-kicker"),
            ui.h2("Aprende el simulador siguiendo la imagen"),
            ui.p("Ubica cada zona, reconoce qué debes observar y realiza tus primeras pruebas con recorridos cortos."),
            class_="manual-hero guide-hero",
        ),
        ui.div(
            guide_stage("01", "◷", "Elige el tiempo", "Tiempo real o una fecha simulada.", "blue"),
            guide_stage("02", "☷", "Configura", "Perfil, geometría, modo y errores.", "teal"),
            guide_stage("03", "▶", "Inicia", "Los cálculos comienzan solo al pulsar.", "green"),
            guide_stage("04", "◎", "Observa", "3D, spot, facetas y diagnóstico.", "gold"),
            guide_stage("05", "⇩", "Compara", "Corrige, repite y guarda CSV.", "red"),
            class_="guide-stages",
        ),
        ui.div(
            ui.div("MAPA DE LA APLICACIÓN", class_="guide-section-kicker"),
            ui.h3("Así se organiza la pantalla principal"),
            ui.p("Los rótulos están colocados sobre la zona que explican; sigue la secuencia del 1 al 4."),
            class_="guide-section-heading",
        ),
        ui.div(
            interface_map,
            ui.div(
                ui.div(ui.span("1"), ui.div(ui.tags.small("ANTES DE INICIAR"), ui.strong("Prepara"), ui.p("Elige tiempo, perfil, modo y condiciones.")), class_="anatomy-key-item anatomy-key-one"),
                ui.div(ui.span("2"), ui.div(ui.tags.small("DURANTE LA SESIÓN"), ui.strong("Controla"), ui.p("Inicia, pausa, reanuda o reconfigura.")), class_="anatomy-key-item anatomy-key-two"),
                ui.div(ui.span("3"), ui.div(ui.tags.small("ANÁLISIS VISUAL"), ui.strong("Explora"), ui.p("Cambia de pestaña para estudiar cada resultado.")), class_="anatomy-key-item anatomy-key-three"),
                ui.div(ui.span("4"), ui.div(ui.tags.small("COMPROBACIÓN"), ui.strong("Confirma"), ui.p("Verifica pose, impacto y estado operacional.")), class_="anatomy-key-item anatomy-key-four"),
                class_="anatomy-key",
            ),
            class_="anatomy-layout",
        ),
        ui.div(
            ui.div("PESTAÑAS DE RESULTADOS", class_="guide-section-kicker"),
            ui.h3("Qué debes mirar en cada pantalla"),
            ui.p("Estas miniaturas usan los mismos colores y conceptos del simulador."),
            class_="guide-section-heading",
        ),
        ui.div(*screen_cards, class_="guide-screen-grid"),
        ui.div(
            ui.div(
                ui.div("CONTROLES ESENCIALES", class_="guide-section-kicker"),
                ui.h3("La sesión se maneja con cuatro acciones"),
                ui.div(
                    ui.div(ui.span("▶", class_="control-symbol"), ui.strong("INICIAR"), ui.tags.small("Comienza con los parámetros preparados."), class_="control-demo control-start"),
                    ui.div(ui.span("Ⅱ", class_="control-symbol"), ui.strong("PAUSAR"), ui.tags.small("Congela reloj y movimiento."), class_="control-demo control-pause"),
                    ui.div(ui.span("↻", class_="control-symbol"), ui.strong("REANUDAR"), ui.tags.small("Continúa la misma sesión."), class_="control-demo control-resume"),
                    ui.div(ui.span("⚙", class_="control-symbol"), ui.strong("CONFIGURAR"), ui.tags.small("Detiene y permite nuevos ajustes."), class_="control-demo control-config"),
                    class_="control-demo-grid",
                ),
                class_="guide-controls-block",
            ),
            ui.div(
                ui.div("LECTURA DEL RECEPTOR", class_="guide-section-kicker"),
                ui.h3("El centro ideal es el origen u = 0, v = 0"),
                target_demo,
                class_="guide-target-block",
            ),
            class_="guide-two-column",
        ),
        ui.div(
            ui.div("EXPORTACIÓN DE DATOS", class_="guide-section-kicker"),
            ui.h3("Qué contiene exactamente el archivo CSV"),
            ui.p("El archivo sirve para analizar la evolución temporal del experimento en una hoja de cálculo o programa estadístico."),
            class_="guide-section-heading",
        ),
        csv_guide_panel(),
        ui.div(
            ui.div("PRIMEROS EXPERIMENTOS", class_="guide-section-kicker"),
            ui.h3("Cuatro recorridos para entender el modelo"),
            ui.p("En cada tarjeta sigue la secuencia de izquierda a derecha."),
            class_="guide-section-heading",
        ),
        ui.div(
            ui.div(ui.span("01", class_="experiment-number"), ui.strong("Seguimiento nominal"), ui.div(ui.span("Minihorno IER"), ui.span("12:00"), ui.span("Automático"), class_="experiment-inputs"), ui.div("INICIAR", class_="experiment-arrow"), ui.p("El spot debe permanecer cerca del centro."), class_="experiment-card experiment-green"),
            ui.div(ui.span("02", class_="experiment-number"), ui.strong("Transitorio de movimiento"), ui.div(ui.span("Manual"), ui.span("Mover AZ/EL"), ui.span("Automático"), class_="experiment-inputs"), ui.div("OBSERVAR", class_="experiment-arrow"), ui.p("La pose viaja gradualmente al objetivo."), class_="experiment-card experiment-blue"),
            ui.div(ui.span("03", class_="experiment-number"), ui.strong("Deriva y corrección"), ui.div(ui.span("0.2°/h"), ui.span("Tiempo ×60"), ui.span("Corregir"), class_="experiment-inputs"), ui.div("COMPARAR", class_="experiment-arrow"), ui.p("Cada pulsación reduce una fracción del error."), class_="experiment-card experiment-gold"),
            ui.div(ui.span("04", class_="experiment-number"), ui.strong("Faceta desalineada"), ui.div(ui.span("Facetas ON"), ui.span("Elegir F1"), ui.span("Desalinear"), class_="experiment-inputs"), ui.div("ANALIZAR", class_="experiment-arrow"), ui.p("Compara el impacto y el mapa de intensidad."), class_="experiment-card experiment-red"),
            class_="experiment-board",
        ),
        ui.div(
            ui.div("REFERENCIA COMPLETA", class_="guide-section-kicker"),
            ui.h3("Detalles para cuando necesites profundizar"),
            ui.p("La guía principal termina aquí. Abre solo el tema que quieras consultar."),
            class_="guide-section-heading reference-heading",
        ),
        ui.div(
            manual_chapter(
                "Operación, reloj y modos",
                ui.p("INICIAR comienza una sesión. PAUSAR congela reloj y movimiento. REANUDAR continúa la misma sesión. VOLVER A CONFIGURAR detiene la sesión y devuelve el heliostato a 0°/90°. REPRODUCIR recorre las muestras guardadas sin generar datos nuevos."),
                ui.p("Tiempo real usa la hora civil del equipo. Fecha simulada usa el día, hora, zona UTC y multiplicador elegidos; estando pausada permite avanzar un paso exacto o reiniciar el reloj. Automático captura el objetivo cada 1, 5, 10, 30 o 60 segundos solares, o únicamente bajo orden."),
            ),
            manual_chapter(
                "Calibración, geometría y cámara 3D",
                ui.p("Minihorno IER restaura la geometría precargada; Diseño propio conserva tus medidas. RX, RY y RZ se expresan en metros desde el centro óptico: +X oeste, +Y sur, +Z cenit."),
                ui.p("Las vistas fijas restablecen la cámara. En vista libre, clic izquierdo desplaza, clic derecho gira y la rueda controla el zoom. El espejo, base, receptor, riel y vectores se actualizan con el estado."),
            ),
            manual_chapter(
                "Spot, facetas, intensidad y corrección",
                ui.p("En el receptor, u es horizontal hacia el oeste, v vertical hacia el cenit y r la distancia radial. Verde representa Ideal, rojo Con error y azul Corregido; el círculo verde punteado es la tolerancia."),
                ui.p("Forma admite cuadrada, circular y hexagonal. Cantidad crea un acomodo compacto. Tamaño significa lado, diámetro o ancho entre caras. Puedes desalinear o desactivar una faceta y comparar su impacto en el mapa."),
                ui.p("Las fuentes de error pueden habilitarse por separado: offsets, desalineación, posiciones XYZ, peralte, backlash, sentido de movimiento y ruido con semilla. La corrección admite offset constante, dependencia temporal, polinomio, impacto observado y cámara periódica."),
                ui.p("Deriva y corrección reúne seis gráficas. Haz clic en cualquiera para ampliarla y usa Vista de 6 gráficas para regresar al resumen."),
            ),
            manual_chapter(
                "Diagnóstico, CSV y solución de problemas",
                ui.p("Diagnóstico muestra error AZ/EL, comparación de escenarios, estadística del seguimiento, encoders, correcciones y vectores. EXPORTAR HISTORIAL CSV descarga hasta 1,200 muestras con 166 columnas; si no existe historial, descarga únicamente la lectura actual."),
                ui.p("Eventos conserva una bitácora de inicio, pausas, cambios de modo, actualizaciones del objetivo, correcciones, reloj y replay. Limpiar historial no altera la calibración; limpiar bitácora inicia un registro nuevo."),
                ui.tags.ul(
                    ui.tags.li("Sin movimiento: inicia la sesión y revisa modo, PWM y límites."),
                    ui.tags.li("Sin spot: confirma que el Sol esté sobre el horizonte y exista intersección frontal."),
                    ui.tags.li("Sin mapa: activa modelo, mapa y al menos una faceta; revisa el rango."),
                    ui.tags.li("Rendimiento lento: reduce facetas o resolución del mapa."),
                ),
            ),
            class_="manual-reference-grid",
        ),
        class_="manual-panel visual-guide-panel",
    )


def manual_panel() -> object:
    return ui.div(
        ui.navset_card_tab(
            ui.nav_panel("Guía visual", visual_guide_panel()),
            ui.nav_panel("Matemáticas", mathematics_panel()),
            ui.nav_panel("Acerca de", about_panel()),
            id="manual_section",
        ),
        class_="manual-shell",
    )


def twin_3d_panel() -> object:
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.button("Isometrica", type="button", class_="view-button active", **{"data-twin-view": "iso"}),
                ui.tags.button("Frontal", type="button", class_="view-button", **{"data-twin-view": "front"}),
                ui.tags.button("Lateral", type="button", class_="view-button", **{"data-twin-view": "side"}),
                ui.tags.button("Superior", type="button", class_="view-button", **{"data-twin-view": "top"}),
                class_="camera-toolbar",
            ),
            ui.div(
                ui.strong("Camara libre"),
                ui.span("Click izquierdo: desplazar · Click derecho: girar · Rueda: zoom"),
                class_="camera-help",
            ),
            class_="twin-toolbar",
        ),
        ui.div(
            ui.tags.canvas(id="twin3d-canvas", **{"aria-label": "Gemelo tridimensional interactivo del heliostato"}),
            ui.div("Preparando escena 3D...", id="twin3d-status", class_="twin-status"),
            ui.div(
                ui.strong("Orientacion local"),
                ui.span("X rojo: oeste · Z verde: sur · Y azul: cenit"),
                class_="orientation-card",
            ),
            ui.div("", id="twin3d-warning", class_="twin-warning", hidden=True),
            class_="twin-stage",
        ),
        ui.div(ui.output_ui("scene_state"), class_="scene-state-host", **{"aria-hidden": "true"}),
        class_="twin-panel",
    )


def drift_panel() -> object:
    return ui.div(
        ui.div(
            ui.output_ui("correction_readout"),
            ui.input_select(
                "drift_display",
                "Grafica mostrada",
                choices={
                    "overview": "Vista de 6 graficas",
                    "az_error": "Error de acimut",
                    "el_error": "Error de elevacion",
                    "az_correction": "Correccion de acimut",
                    "el_correction": "Correccion de elevacion",
                    "error_spot": "Spot con error",
                    "corrected_spot": "Spot corregido",
                },
                selected="overview",
            ),
            ui.input_action_button(
                "correct_now",
                "CORREGIR DESDE IMPACTO",
                class_="correction-action",
            ),
            class_="drift-toolbar",
        ),
        ui.output_ui("drift_chart"),
        class_="drift-panel",
    )


def drift_svg(state: WebTwinState, display: str = "overview") -> str:
    samples = (state.history or [state.snapshot()])[-180:]
    width, height = 1000, 600

    def finite(value: object) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return result if math.isfinite(result) else 0.0

    series = {
        "az_error": ("Error de acimut", "deg", "#178ca4", [finite(item.get("effective_az_error_deg")) for item in samples]),
        "el_error": ("Error de elevacion", "deg", "#8b5cf6", [finite(item.get("effective_el_error_deg")) for item in samples]),
        "az_correction": ("Correccion de acimut", "deg", "#2563eb", [finite(item.get("correction_az_deg")) for item in samples]),
        "el_correction": ("Correccion de elevacion", "deg", "#0f766e", [finite(item.get("correction_el_deg")) for item in samples]),
        "error_spot": ("Spot con error", "mm", "#dc2626", [finite(item.get("error_spot_radial_mm")) for item in samples]),
        "corrected_spot": ("Spot corregido", "mm", "#16a34a", [finite(item.get("corrected_spot_radial_mm")) for item in samples]),
    }

    def plot(values: list[float], left: float, right: float, top: float, bottom: float) -> tuple[str, float, float, float | None]:
        minimum = min(values, default=0.0)
        maximum = max(values, default=0.0)
        if abs(maximum - minimum) < 1e-9:
            padding = max(0.001, abs(maximum) * 0.15)
            minimum -= padding
            maximum += padding
        points = []
        denominator = max(1, len(values) - 1)
        for index, value in enumerate(values):
            x = left + (right - left) * index / denominator
            y = bottom - (bottom - top) * (value - minimum) / (maximum - minimum)
            points.append(f"{x:.1f},{y:.1f}")
        zero_y = None
        if minimum <= 0.0 <= maximum:
            zero_y = bottom - (bottom - top) * (0.0 - minimum) / (maximum - minimum)
        return " ".join(points), minimum, maximum, zero_y

    content: list[str] = [
        '<rect width="1000" height="600" fill="#f8fafc"/>',
        '<text x="28" y="34" fill="#102a43" font-size="20" font-weight="700">Deriva temporal, escenarios y correccion</text>',
    ]
    if display in series:
        layouts = [(display, 78.0, 966.0, 82.0, 520.0)]
    else:
        layouts = []
        for index, key in enumerate(series):
            column = index % 2
            row = index // 2
            left = 62.0 + column * 472.0
            layouts.append((key, left, left + 410.0, 68.0 + row * 172.0, 198.0 + row * 172.0))

    for key, left, right, top, bottom in layouts:
        label, unit, color, values = series[key]
        points, minimum, maximum, zero_y = plot(values, left, right, top, bottom)
        click = f"if(window.Shiny) Shiny.setInputValue('drift_chart_pick','{key}',{{priority:'event'}})"
        content.extend(
            [
                f'<g onclick="{click}" style="cursor:pointer">',
                f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" rx="7" fill="#ffffff" stroke="#cbd5df"/>',
                f'<text x="{left+8}" y="{top+19}" fill="#334155" font-size="13" font-weight="700">{label} [{unit}]</text>',
                f'<text x="{left-7}" y="{top+5}" text-anchor="end" fill="#64748b" font-size="11">{maximum:.3f}</text>',
                f'<text x="{left-7}" y="{bottom+4}" text-anchor="end" fill="#64748b" font-size="11">{minimum:.3f}</text>',
                (f'<line x1="{left}" y1="{zero_y:.1f}" x2="{right}" y2="{zero_y:.1f}" stroke="#cbd5df" stroke-dasharray="4 4"/>' if zero_y is not None else ""),
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>',
                '</g>',
            ]
        )
    hint = "Haz clic en una grafica para ampliarla" if display not in series else "Selecciona Vista de 6 graficas para regresar"
    content.append(f'<text x="500" y="578" text-anchor="middle" fill="#64748b" font-size="13">{hint} · X = muestras en orden temporal · {len(samples)} visibles</text>')
    return svg_document("".join(content), width, height)


app_ui = ui.page_fluid(
    ui.head_content(
        ui.include_js(
            APP_DIR / "www" / "twin3d.js",
            method="inline",
            type="module",
        ),
    ),
    ui.include_css(APP_DIR / "www" / "styles.css"),
    ui.div(
        ui.div(
            ui.div("GEMELO DIGITAL", class_="eyebrow"),
            ui.h1("Mini horno solar · Web 0.4.0"),
            ui.p("Gemelo tridimensional y simulacion local en el navegador"),
            class_="brand-block",
        ),
        ui.output_ui("clock_card"),
        class_="topbar",
    ),
    ui.div(
        ui.tags.aside(
            control_section(
                "Modo de operacion",
                ui.input_radio_buttons(
                    "mode",
                    None,
                    choices=("Automatico", "Manual", "Home"),
                    selected="Automatico",
                    inline=True,
                ),
                ui.panel_conditional(
                    "input.mode === 'Automatico'",
                    ui.input_checkbox("tracking", "Seguimiento solar", True),
                    ui.input_select(
                        "tracking_interval",
                        "Actualizar objetivo solar",
                        choices={"1": "Cada 1 s solar", "5": "Cada 5 s solares", "10": "Cada 10 s solares", "30": "Cada 30 s solares", "60": "Cada 60 s solares", "manual": "Solo bajo orden"},
                        selected="1",
                    ),
                    ui.input_action_button("tracking_now", "ACTUALIZAR OBJETIVO AHORA", class_="secondary-action full"),
                    ui.p("Entre actualizaciones, el objetivo queda retenido y los motores llegan gradualmente.", class_="field-help"),
                ),
                ui.panel_conditional(
                    "input.mode === 'Manual'",
                    ui.input_numeric("manual_step", "Paso objetivo [deg]", value=2.0, min=0.1, max=20.0, step=0.5),
                    ui.div(
                        ui.input_action_button("jog_east", "< ESTE", class_="jog-button"),
                        ui.input_action_button("stop_manual", "DETENER", class_="stop-button"),
                        ui.input_action_button("jog_west", "OESTE >", class_="jog-button"),
                        class_="jog-row",
                    ),
                    ui.div(
                        ui.input_action_button("jog_down", "< BAJAR", class_="jog-button"),
                        ui.input_action_button("jog_up", "SUBIR >", class_="jog-button"),
                        class_="jog-row two",
                    ),
                    ui.p("Los botones cambian el objetivo; los motores se desplazan gradualmente segun el PWM.", class_="field-help"),
                ),
                ui.panel_conditional(
                    "input.mode === 'Home'",
                    ui.p("Al iniciar, el heliostato regresara gradualmente a AZ 0° y EL 90°.", class_="field-help home-note"),
                ),
                opened=True,
            ),
            control_section(
                "Tiempo del experimento",
                ui.input_radio_buttons(
                    "time_mode",
                    None,
                    choices=("Tiempo real", "Fecha simulada"),
                    selected="Tiempo real",
                ),
                ui.input_date("sim_date", "Fecha simulada", value="2026-08-06"),
                ui.input_text("sim_time", "Hora", value="12:00:00"),
                ui.input_select("time_scale", "Velocidad", choices=("1", "10", "60", "120", "600"), selected="60"),
                ui.input_action_button("apply_time", "APLICAR FECHA Y HORA", class_="secondary-action full"),
                ui.input_numeric("simulation_step", "Paso manual [s]", value=60, min=0, max=86400, step=1),
                ui.div(
                    ui.input_action_button("step_time", "AVANZAR UN PASO", class_="secondary-action"),
                    ui.input_action_button("reset_time", "REINICIAR RELOJ", class_="secondary-action"),
                    class_="two-columns",
                ),
                ui.p("El paso manual solo actua con Fecha simulada y la sesion pausada.", class_="field-help"),
                opened=True,
            ),
            control_section(
                "Calibracion y perfiles",
                ui.input_select(
                    "geometry_profile",
                    "Perfil geometrico",
                    choices=("Minihorno IER", "Diseno personalizado"),
                    selected="Minihorno IER",
                ),
                ui.input_action_button("load_profile", "CARGAR PERFIL SELECCIONADO", class_="profile-action full"),
                ui.h4("Ubicacion y objetivo"),
                ui.div(
                    ui.input_numeric("lat", "Latitud [deg]", value=MINIHORNO_WEB_PROFILE["lat_deg"], step=0.01),
                    ui.input_numeric("lon", "Longitud [deg]", value=MINIHORNO_WEB_PROFILE["lon_deg"], step=0.01),
                    class_="two-columns",
                ),
                ui.input_numeric("utc", "Zona UTC [h]", value=MINIHORNO_WEB_PROFILE["utc_offset_hours"], step=1),
                ui.div(
                    ui.input_numeric("rx", "RX [m]", value=MINIHORNO_WEB_PROFILE["rx"], step=0.01),
                    ui.input_numeric("ry", "RY [m]", value=MINIHORNO_WEB_PROFILE["ry"], step=0.01),
                    ui.input_numeric("rz", "RZ [m]", value=MINIHORNO_WEB_PROFILE["rz"], step=0.01),
                    class_="three-columns",
                ),
                ui.input_select("method", "Metodo solar", choices=("D&B", "REDA"), selected="D&B"),
                ui.h4("Heliostato"),
                ui.div(
                    ui.input_numeric("mirror_size", "Espejo lado [m]", value=MINIHORNO_WEB_PROFILE["mirror_size_m"], min=0.05, step=0.05),
                    ui.input_numeric("base_width", "Base ancho [m]", value=MINIHORNO_WEB_PROFILE["base_width_m"], min=0.10, step=0.05),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("fork_height", "Horquilla alto [m]", value=MINIHORNO_WEB_PROFILE["fork_height_m"], min=0.10, step=0.05),
                    ui.input_numeric("rail_length", "Riel largo [m]", value=MINIHORNO_WEB_PROFILE["rail_length_m"], min=0.10, step=0.05),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("receiver_screen", "Pantalla diam. [m]", value=MINIHORNO_WEB_PROFILE["receiver_screen_m"], min=0.03, step=0.05),
                    ui.input_numeric("target_tolerance", "Tolerancia [m]", value=MINIHORNO_WEB_PROFILE["target_tolerance_m"], min=0.0001, step=0.001),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("peralte", "Peralte [deg]", value=MINIHORNO_WEB_PROFILE["peralte_deg"], step=0.01),
                    ui.input_numeric("cdr", "Banda muerta CDR [deg]", value=MINIHORNO_WEB_PROFILE["cdr_deg"], min=0, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("camera_offset_az", "Offset camara AZ [deg]", value=0.0, step=0.01),
                    ui.input_numeric("camera_offset_el", "Offset camara EL [deg]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("az_limit_min", "Limite AZ min [deg]", value=MINIHORNO_WEB_PROFILE["az_limit_min"], step=1),
                    ui.input_numeric("az_limit_max", "Limite AZ max [deg]", value=MINIHORNO_WEB_PROFILE["az_limit_max"], step=1),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("el_limit_min", "Limite EL min [deg]", value=MINIHORNO_WEB_PROFILE["el_limit_min"], step=1),
                    ui.input_numeric("el_limit_max", "Limite EL max [deg]", value=MINIHORNO_WEB_PROFILE["el_limit_max"], step=1),
                    class_="two-columns",
                ),
                ui.p("RX, RY y RZ se miden desde el centro optico del espejo.", class_="field-help"),
                opened=True,
            ),
            control_section(
                "Motores, errores y correccion",
                ui.input_select("error_mode", "Escenario mostrado", choices=("Ideal", "Con error", "Corregido"), selected="Corregido"),
                ui.div(
                    ui.input_checkbox("az_motor_on", "Motor AZ habilitado", True),
                    ui.input_checkbox("el_motor_on", "Motor EL habilitado", True),
                    class_="two-columns",
                ),
                ui.input_slider("az_pwm", "PWM acimut", min=0, max=100, value=55, step=1, post=" %"),
                ui.input_slider("el_pwm", "PWM elevacion", min=0, max=100, value=55, step=1, post=" %"),
                ui.div(
                    ui.input_numeric("az_speed", "Vel. AZ [deg/s]", value=MINIHORNO_WEB_PROFILE["az_deg_per_second"], min=0.1, step=0.5),
                    ui.input_numeric("el_speed", "Vel. EL [deg/s]", value=MINIHORNO_WEB_PROFILE["el_deg_per_second"], min=0.1, step=0.5),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("az_counts", "Encoder AZ [conteos/deg]", value=MINIHORNO_WEB_PROFILE["az_counts_per_degree"], min=0, step=1),
                    ui.input_numeric("el_counts", "Encoder EL [conteos/deg]", value=MINIHORNO_WEB_PROFILE["el_counts_per_degree"], min=0, step=1),
                    class_="two-columns",
                ),
                ui.tags.details(
                    ui.tags.summary("Errores geometricos y mecanicos"),
                    ui.input_checkbox("enable_az_offset", "Offset de acimut", False),
                    ui.input_numeric("az_offset", "Offset AZ [deg]", value=0.0, step=0.01),
                    ui.input_checkbox("enable_el_offset", "Offset de elevacion", False),
                    ui.input_numeric("el_offset", "Offset EL [deg]", value=0.0, step=0.01),
                    ui.input_checkbox("enable_ns_error", "Desalineacion norte-sur", False),
                    ui.input_numeric("ns_error", "Desalineacion N-S [deg]", value=0.0, step=0.01),
                    ui.input_checkbox("enable_target_xyz", "Error de posicion del receptor", False),
                    ui.div(
                        ui.input_numeric("target_error_x", "Target dX [m]", value=0.0, step=0.001),
                        ui.input_numeric("target_error_y", "Target dY [m]", value=0.0, step=0.001),
                        ui.input_numeric("target_error_z", "Target dZ [m]", value=0.0, step=0.001),
                        class_="three-columns",
                    ),
                    ui.input_checkbox("enable_heliostat_xyz", "Error de posicion del heliostato", False),
                    ui.div(
                        ui.input_numeric("heliostat_error_x", "Heliostato dX [m]", value=0.0, step=0.001),
                        ui.input_numeric("heliostat_error_y", "Heliostato dY [m]", value=0.0, step=0.001),
                        ui.input_numeric("heliostat_error_z", "Heliostato dZ [m]", value=0.0, step=0.001),
                        class_="three-columns",
                    ),
                    ui.input_checkbox("enable_peralte_error", "Error de peralte", False),
                    ui.input_numeric("peralte_error", "Error peralte [deg]", value=0.0, step=0.01),
                    ui.input_checkbox("enable_backlash", "Backlash", False),
                    ui.input_numeric("backlash", "Backlash [deg]", value=0.0, min=0, step=0.01),
                    ui.input_checkbox("enable_directional", "Error diferente al subir y bajar", False),
                    ui.div(
                        ui.input_numeric("upward_error", "Subida [deg]", value=0.0, step=0.01),
                        ui.input_numeric("downward_error", "Bajada [deg]", value=0.0, step=0.01),
                        class_="two-columns",
                    ),
                    ui.input_checkbox("enable_noise", "Ruido aleatorio reproducible", False),
                    ui.div(
                        ui.input_numeric("noise_std", "Sigma ruido [deg]", value=0.0, min=0, step=0.001),
                        ui.input_numeric("noise_seed", "Semilla", value=12345, step=1),
                        class_="two-columns",
                    ),
                    class_="nested-controls",
                ),
                ui.div(
                    ui.input_numeric("drift_az", "Deriva AZ [deg/h]", value=0.0, step=0.01),
                    ui.input_numeric("drift_el", "Deriva EL [deg/h]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.tags.details(
                    ui.tags.summary("Estrategia de correccion"),
                    ui.input_checkbox("correction_enabled", "Activar correccion", False),
                    ui.input_select("correction_strategy", "Estrategia", choices=("Ninguna", "Offset constante", "Dependiente del tiempo", "Polinomial", "Impacto observado", "Camara periodica"), selected="Ninguna"),
                    ui.div(
                        ui.input_numeric("correction_constant_az", "Constante AZ [deg]", value=0.0, step=0.01),
                        ui.input_numeric("correction_constant_el", "Constante EL [deg]", value=0.0, step=0.01),
                        class_="two-columns",
                    ),
                    ui.div(
                        ui.input_numeric("correction_rate_az", "Tasa AZ [deg/h]", value=0.0, step=0.01),
                        ui.input_numeric("correction_rate_el", "Tasa EL [deg/h]", value=0.0, step=0.01),
                        class_="two-columns",
                    ),
                    ui.strong("Polinomio c0 + c1*t + c2*t^2 (t en horas)"),
                    ui.div(
                        ui.input_numeric("poly_az_c0", "AZ c0", value=0.0, step=0.01),
                        ui.input_numeric("poly_az_c1", "AZ c1", value=0.0, step=0.01),
                        ui.input_numeric("poly_az_c2", "AZ c2", value=0.0, step=0.01),
                        class_="three-columns",
                    ),
                    ui.div(
                        ui.input_numeric("poly_el_c0", "EL c0", value=0.0, step=0.01),
                        ui.input_numeric("poly_el_c1", "EL c1", value=0.0, step=0.01),
                        ui.input_numeric("poly_el_c2", "EL c2", value=0.0, step=0.01),
                        class_="three-columns",
                    ),
                    ui.input_slider("correction_gain", "Ganancia desde impacto", min=0, max=100, value=50, step=5, post=" %"),
                    ui.div(
                        ui.input_numeric("correction_max_step", "Paso maximo [deg]", value=1.0, min=0, step=0.05),
                        ui.input_numeric("camera_interval", "Intervalo camara [s]", value=60.0, min=0.001, step=1),
                        class_="two-columns",
                    ),
                    ui.input_action_button("reset_correction", "REINICIAR CORRECCION", class_="secondary-action full"),
                    class_="nested-controls",
                ),
            ),
            control_section(
                "Vectores y referencias 3D",
                ui.input_checkbox("show_sun", "Solar incidente", True),
                ui.input_checkbox("show_normal", "Normal del heliostato", True),
                ui.input_checkbox("show_reflected", "Rayo reflejado", True),
                ui.input_checkbox("show_target_direction", "Direccion objetivo", True),
                ui.input_checkbox("show_target_line", "Linea heliostato-target", True),
                ui.input_checkbox("show_guides", "Guias mecanicas", False),
            ),
            control_section(
                "Facetas: geometria, rayos e intensidad",
                ui.input_checkbox("facet_enabled", "Activar modelo", False),
                ui.input_checkbox("spot_map_enabled", "Activar mapa de intensidad", False),
                ui.input_select("facet_shape", "Forma", choices=("Cuadrada", "Circular", "Hexagonal"), selected="Cuadrada"),
                ui.div(
                    ui.input_numeric("facet_count", "Cantidad", value=9, min=1, max=200, step=1),
                    ui.input_numeric("facet_size", "Tamano [m]", value=0.30, min=0.001, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("facet_gap", "Separacion [m]", value=0.03, min=0, step=0.005),
                    ui.input_numeric("facet_focal", "Focal [m]", value=2.50, min=0.01, step=0.05),
                    class_="two-columns",
                ),
                ui.hr(),
                ui.strong("Control por faceta"),
                ui.input_text("facet_selected", "ID seleccionada", value="F5", placeholder="Ej. F12"),
                ui.div(
                    ui.input_numeric("facet_misalign_h", "Desalineacion H [deg]", value=0.0, step=0.01),
                    ui.input_numeric("facet_misalign_v", "Desalineacion V [deg]", value=0.0, step=0.01),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_action_button("facet_on", "ACTIVAR SELECCIONADA", class_="secondary-action facet-action"),
                    ui.input_action_button("facet_off", "DESACTIVAR SELECCIONADA", class_="secondary-action facet-action"),
                    class_="facet-action-grid",
                ),
                ui.div(
                    ui.input_action_button("facets_all_on", "TODAS ON", class_="secondary-action facet-action"),
                    ui.input_action_button("facets_all_off", "TODAS OFF", class_="secondary-action facet-action"),
                    class_="facet-action-grid",
                ),
                ui.hr(),
                ui.strong("Visualizacion y mapa"),
                ui.input_select(
                    "facet_view_mode",
                    "Vista de rayos",
                    choices=("Resumen", "Superior X-Y", "Lateral Y-Z", "3D isometrica"),
                    selected="Resumen",
                ),
                ui.input_select(
                    "facet_display_mode",
                    "Panel mostrado",
                    choices=("Vista general", "Esquema ampliado", "Receptor ampliado"),
                    selected="Vista general",
                ),
                ui.div(
                    ui.input_numeric("spot_sigma_mm", "Sigma base [mm]", value=3.0, min=0.01, step=0.1),
                    ui.input_numeric("spot_half_mm", "Rango +/- [mm]", value=50.0, min=1.0, step=1.0),
                    class_="two-columns",
                ),
                ui.div(
                    ui.input_numeric("spot_resolution", "Resolucion impar", value=51, min=21, max=121, step=2),
                    ui.input_select("spot_normalization", "Normalizacion", choices=("Total = 1", "Pico = 1", "Sin normalizar"), selected="Total = 1"),
                    class_="two-columns",
                ),
            ),
            class_="sidebar-panel",
        ),
        ui.tags.main(
            ui.div(
                ui.output_ui("operation_badge"),
                ui.div(
                    ui.input_action_button("toggle_run", "INICIAR SIMULACION", class_="primary-action"),
                    ui.input_action_button("reset", "VOLVER A CONFIGURAR", class_="secondary-action"),
                    ui.input_action_button("toggle_replay", "REPRODUCIR", class_="secondary-action"),
                    ui.download_button("download_csv", "EXPORTAR HISTORIAL CSV", class_="secondary-action csv-download-action"),
                    ui.download_button("download_package", "EXPORTAR PAQUETE", class_="secondary-action csv-download-action"),
                    class_="action-row",
                ),
                class_="operation-row",
            ),
            ui.div(
                ui.navset_card_tab(
                    ui.nav_panel("Gemelo 3D", twin_3d_panel()),
                    ui.nav_panel("Pantalla / spot", ui.output_ui("spot_view")),
                    ui.nav_panel("Trayectoria solar", ui.output_ui("solar_view")),
                    ui.nav_panel("Facetas", ui.output_ui("facet_view")),
                    ui.nav_panel("Deriva y correccion", drift_panel()),
                    ui.nav_panel("Diagnostico", ui.output_ui("diagnostic_view")),
                    ui.nav_panel(
                        "Eventos",
                        ui.div(
                            ui.div(
                                ui.input_action_button("clear_history", "LIMPIAR HISTORIAL", class_="secondary-action"),
                                ui.input_action_button("clear_events", "LIMPIAR BITACORA", class_="secondary-action"),
                                class_="event-actions",
                            ),
                            ui.output_ui("events_view"),
                            class_="events-panel",
                        ),
                    ),
                    ui.nav_panel("Manual", manual_panel()),
                    id="main_view",
                ),
                class_="view-tabs",
            ),
            ui.output_ui("readout_strip"),
            class_="workspace-panel",
        ),
        class_="app-grid",
    ),
    title="Gemelo digital del mini horno solar",
)


def server(input, output, session) -> None:  # type: ignore[no-untyped-def]
    state = WebTwinState()
    revision = reactive.value(0)
    revision_counter = [0]

    def bump() -> None:
        revision_counter[0] += 1
        revision.set(revision_counter[0])

    @reactive.effect
    def sync_controls() -> None:
        selected_mode = str(input.mode())
        if selected_mode != state.mode:
            if selected_mode == "Manual":
                state.stop_manual_motion()
            if selected_mode == "Automatico":
                state.reset_tracking_schedule()
            if selected_mode == "Home":
                state.resample_motion_errors(
                    -state.az_angle_deg,
                    90.0 - state.el_angle_deg,
                )
            state.add_event("Modo", f"Modo seleccionado: {selected_mode}")
        state.mode = selected_mode
        state.tracking = bool(input.tracking())
        state.configure_tracking_updates(str(input.tracking_interval()))
        state.time_mode = str(input.time_mode())
        state.time_scale = float(input.time_scale())
        state.simulation_step_s = float(input.simulation_step())
        state.lat_deg = float(input.lat())
        state.lon_deg = float(input.lon())
        state.utc_offset_hours = float(input.utc())
        state.rx = float(input.rx())
        state.ry = float(input.ry())
        state.rz = float(input.rz())
        state.mirror_size_m = float(input.mirror_size())
        state.base_width_m = float(input.base_width())
        state.fork_height_m = float(input.fork_height())
        state.rail_length_m = float(input.rail_length())
        state.receiver_screen_m = float(input.receiver_screen())
        state.target_tolerance_m = float(input.target_tolerance())
        state.peralte_deg = float(input.peralte())
        state.cdr_deg = max(0.0, float(input.cdr()))
        state.camera_offset_az_deg = float(input.camera_offset_az())
        state.camera_offset_el_deg = float(input.camera_offset_el())
        state.az_limit_min = float(input.az_limit_min())
        state.az_limit_max = float(input.az_limit_max())
        state.el_limit_min = float(input.el_limit_min())
        state.el_limit_max = float(input.el_limit_max())
        state.method = str(input.method())
        state.error_mode = str(input.error_mode())
        state.az_motor_on = bool(input.az_motor_on())
        state.el_motor_on = bool(input.el_motor_on())
        state.az_pwm = float(input.az_pwm()) / 100.0
        state.el_pwm = float(input.el_pwm()) / 100.0
        state.az_deg_per_second = float(input.az_speed())
        state.el_deg_per_second = float(input.el_speed())
        state.az_counts_per_degree = max(0.0, float(input.az_counts()))
        state.el_counts_per_degree = max(0.0, float(input.el_counts()))
        state.az_offset_deg = float(input.az_offset())
        state.el_offset_deg = float(input.el_offset())
        error = state.error_config
        error.enable_azimuth_offset = bool(input.enable_az_offset())
        error.azimuth_offset_deg = state.az_offset_deg
        error.enable_elevation_offset = bool(input.enable_el_offset())
        error.elevation_offset_deg = state.el_offset_deg
        error.enable_north_south_misalignment = bool(input.enable_ns_error())
        error.north_south_misalignment_deg = float(input.ns_error())
        error.enable_target_position_error = bool(input.enable_target_xyz())
        error.target_error_x_m = float(input.target_error_x())
        error.target_error_y_m = float(input.target_error_y())
        error.target_error_z_m = float(input.target_error_z())
        error.enable_heliostat_position_error = bool(input.enable_heliostat_xyz())
        error.heliostat_error_x_m = float(input.heliostat_error_x())
        error.heliostat_error_y_m = float(input.heliostat_error_y())
        error.heliostat_error_z_m = float(input.heliostat_error_z())
        error.enable_peralte_error = bool(input.enable_peralte_error())
        error.peralte_error_deg = float(input.peralte_error())
        error.enable_backlash = bool(input.enable_backlash())
        error.backlash_deg = max(0.0, float(input.backlash()))
        error.enable_directional_error = bool(input.enable_directional())
        error.upward_error_deg = float(input.upward_error())
        error.downward_error_deg = float(input.downward_error())
        error.enable_random_noise = bool(input.enable_noise())
        error.random_noise_std_deg = max(0.0, float(input.noise_std()))
        error.random_seed = int(input.noise_seed())
        state.drift_az_deg_per_hour = float(input.drift_az())
        state.drift_el_deg_per_hour = float(input.drift_el())
        state.correction_gain = float(input.correction_gain()) / 100.0
        correction = state.correction_config
        correction.enabled = bool(input.correction_enabled())
        correction.strategy = str(input.correction_strategy())
        correction.constant_az_deg = float(input.correction_constant_az())
        correction.constant_el_deg = float(input.correction_constant_el())
        correction.time_az_rate_deg_per_hour = float(input.correction_rate_az())
        correction.time_el_rate_deg_per_hour = float(input.correction_rate_el())
        correction.polynomial_az_c0 = float(input.poly_az_c0())
        correction.polynomial_az_c1 = float(input.poly_az_c1())
        correction.polynomial_az_c2 = float(input.poly_az_c2())
        correction.polynomial_el_c0 = float(input.poly_el_c0())
        correction.polynomial_el_c1 = float(input.poly_el_c1())
        correction.polynomial_el_c2 = float(input.poly_el_c2())
        correction.image_max_step_deg = max(0.0, float(input.correction_max_step()))
        correction.camera_interval_s = max(0.001, float(input.camera_interval()))
        state.show_sun_vector = bool(input.show_sun())
        state.show_normal_vector = bool(input.show_normal())
        state.show_reflected_vector = bool(input.show_reflected())
        state.show_target_direction = bool(input.show_target_direction())
        state.show_target_line = bool(input.show_target_line())
        state.show_mechanical_guides = bool(input.show_guides())
        state.facet_enabled = bool(input.facet_enabled())
        state.facet_shape = str(input.facet_shape())
        state.facet_count = int(input.facet_count())
        state.facet_size_m = float(input.facet_size())
        state.facet_gap_m = float(input.facet_gap())
        state.facet_focal_distance_m = float(input.facet_focal())
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.facet_horizontal_misalignment_deg = float(input.facet_misalign_h())
        state.facet_vertical_misalignment_deg = float(input.facet_misalign_v())
        state.spot_map_enabled = bool(input.spot_map_enabled())
        state.spot_base_sigma_m = float(input.spot_sigma_mm()) / 1000.0
        state.spot_map_half_size_m = float(input.spot_half_mm()) / 1000.0
        state.spot_map_resolution = int(input.spot_resolution())
        state.spot_normalization = str(input.spot_normalization())
        bump()

    @reactive.effect
    @reactive.event(input.load_profile)
    def load_profile() -> None:
        if str(input.geometry_profile()) != "Minihorno IER":
            return
        profile = MINIHORNO_WEB_PROFILE
        updates = {
            "lat": "lat_deg",
            "lon": "lon_deg",
            "utc": "utc_offset_hours",
            "rx": "rx",
            "ry": "ry",
            "rz": "rz",
            "mirror_size": "mirror_size_m",
            "base_width": "base_width_m",
            "fork_height": "fork_height_m",
            "rail_length": "rail_length_m",
            "receiver_screen": "receiver_screen_m",
            "target_tolerance": "target_tolerance_m",
            "peralte": "peralte_deg",
            "cdr": "cdr_deg",
            "camera_offset_az": "camera_offset_az_deg",
            "camera_offset_el": "camera_offset_el_deg",
            "az_limit_min": "az_limit_min",
            "az_limit_max": "az_limit_max",
            "el_limit_min": "el_limit_min",
            "el_limit_max": "el_limit_max",
            "az_speed": "az_deg_per_second",
            "el_speed": "el_deg_per_second",
            "az_counts": "az_counts_per_degree",
            "el_counts": "el_counts_per_degree",
            "facet_count": "facet_count",
            "facet_size": "facet_size_m",
            "facet_gap": "facet_gap_m",
            "facet_focal": "facet_focal_distance_m",
        }
        for input_id, profile_name in updates.items():
            ui.update_numeric(input_id, value=profile[profile_name], session=session)
        ui.update_select("facet_shape", selected=str(profile["facet_shape"]), session=session)
        state.apply_profile(profile)
        state.set_all_facets_active(True)
        bump()

    @reactive.effect
    @reactive.event(input.toggle_run)
    def toggle_run() -> None:
        state.pause_or_resume()
        bump()

    def manual_step() -> float:
        return max(0.1, float(input.manual_step()))

    @reactive.effect
    @reactive.event(input.jog_west)
    def jog_west() -> None:
        state.set_manual_target("az", 1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_east)
    def jog_east() -> None:
        state.set_manual_target("az", -1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_up)
    def jog_up() -> None:
        state.set_manual_target("el", 1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.jog_down)
    def jog_down() -> None:
        state.set_manual_target("el", -1.0, manual_step())
        bump()

    @reactive.effect
    @reactive.event(input.stop_manual)
    def stop_manual() -> None:
        state.stop_manual_motion()
        bump()

    @reactive.effect
    @reactive.event(input.correct_now)
    def correct_now() -> None:
        state.apply_observed_correction()
        bump()

    @reactive.effect
    @reactive.event(input.reset_correction)
    def reset_correction() -> None:
        state.reset_correction()
        bump()

    @reactive.effect
    @reactive.event(input.tracking_now)
    def tracking_now() -> None:
        state.request_tracking_update()
        bump()

    @reactive.effect
    @reactive.event(input.step_time)
    def step_time() -> None:
        state.step_simulated_time(float(input.simulation_step()))
        bump()

    @reactive.effect
    @reactive.event(input.reset_time)
    def reset_time() -> None:
        state.reset_simulated_time()
        bump()

    @reactive.effect
    @reactive.event(input.toggle_replay)
    def toggle_replay() -> None:
        if state.replay_active:
            state.stop_replay()
        else:
            state.start_replay()
        bump()

    @reactive.effect
    @reactive.event(input.clear_history)
    def clear_history() -> None:
        state.history.clear()
        state.add_event("Historial", "Muestras eliminadas")
        bump()

    @reactive.effect
    @reactive.event(input.clear_events)
    def clear_events() -> None:
        state.clear_events()
        bump()

    @reactive.effect
    @reactive.event(input.facet_on)
    def facet_on() -> None:
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.set_selected_facet_active(True)
        ui.update_text("facet_selected", value=state.facet_selected_id, session=session)
        bump()

    @reactive.effect
    @reactive.event(input.facet_off)
    def facet_off() -> None:
        state.facet_selected_id = str(input.facet_selected()).strip().upper() or "F1"
        state.set_selected_facet_active(False)
        ui.update_text("facet_selected", value=state.facet_selected_id, session=session)
        bump()

    @reactive.effect
    @reactive.event(input.facets_all_on)
    def facets_all_on() -> None:
        state.set_all_facets_active(True)
        bump()

    @reactive.effect
    @reactive.event(input.facets_all_off)
    def facets_all_off() -> None:
        state.set_all_facets_active(False)
        bump()

    @reactive.effect
    @reactive.event(input.reset)
    def reset_state() -> None:
        state.reset()
        bump()

    @reactive.effect
    @reactive.event(input.apply_time)
    def apply_time() -> None:
        try:
            date_value = input.sim_date()
            date_text = date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value)
            state.apply_simulated_time(date_text, str(input.sim_time()))
        except ValueError:
            pass
        bump()

    @reactive.effect
    def simulation_clock() -> None:
        reactive.invalidate_later(0.15)
        state.step(0.15)
        bump()

    @output
    @render.ui
    def clock_card() -> object:
        revision.get()
        sample = state.snapshot()
        when = dt.datetime.fromisoformat(str(sample["timestamp"]))
        multiplier = f"{state.time_scale:g}x" if state.time_mode == "Fecha simulada" else "1x"
        return ui.div(
            ui.div("RELOJ DEL EXPERIMENTO", class_="clock-label"),
            ui.div(
                ui.span(when.strftime("%Y-%m-%d"), class_="clock-date"),
                ui.span(when.strftime("%H:%M:%S"), class_="clock-time"),
                class_="clock-value",
            ),
            ui.div(f"{state.time_mode.upper()} · UTC {state.utc_offset_hours:+g} · {multiplier}", class_="clock-mode"),
            class_="clock-card",
        )

    @reactive.effect
    def update_run_button() -> None:
        revision.get()
        if state.running:
            label = "PAUSAR"
        elif state.session_started:
            label = "REANUDAR"
        else:
            label = "INICIAR SIMULACION"
        ui.update_action_button("toggle_run", label=label, session=session)
        ui.update_action_button(
            "toggle_replay",
            label="SALIR DE REPLAY" if state.replay_active else "REPRODUCIR",
            session=session,
        )

    @output
    @render.ui
    def operation_badge() -> object:
        revision.get()
        sample = state.snapshot()
        return ui.div(
            ui.span(str(sample["status"]), class_=f"status-chip {sample['status_kind']}"),
            ui.span(
                f"Modo {state.mode} · AZ {number(sample['az_deg'])}° / {number(sample['az_target_deg'])}° · "
                f"EL {number(sample['el_deg'])}° / {number(sample['el_target_deg'])}°",
                class_="status-context",
            ),
            class_="status-block",
        )

    @output
    @render.ui
    def scene_state() -> object:
        current_revision = revision.get()
        sample = state.snapshot()
        sample["revision"] = current_revision
        analysis = state.facet_analysis()
        sample["facets"] = [
            [facet.id, facet.layout_u_m, facet.layout_v_m, facet.active]
            for facet in analysis["facets"]
        ]
        sample["facet_focus"] = analysis["focus"]
        sample["facet_rays"] = [
            [result.facet_id, result.facet_center, result.impact_point]
            for result in analysis["results"]
            if result.impact_point is not None
        ]
        return ui.div(
            json.dumps(json_safe(sample), ensure_ascii=False, allow_nan=False),
            class_="twin-state-payload",
        )

    @output
    @render.ui
    def spot_view() -> object:
        revision.get()
        return ui.HTML(
            spot_svg(
                state.snapshot(),
                state.history,
                state.target_tolerance_m * 1000.0,
            )
        )

    @output
    @render.ui
    def solar_view() -> object:
        revision.get()
        return ui.HTML(solar_svg(state.snapshot(), state.solar_path()))

    @output
    @render.ui
    def facet_view() -> object:
        revision.get()
        return ui.HTML(
            facets_svg(
                state,
                state.facet_analysis(),
                str(input.facet_view_mode()),
                str(input.facet_display_mode()),
            )
        )

    @output
    @render.ui
    def correction_readout() -> object:
        revision.get()
        sample = state.snapshot()
        return ui.div(
            ui.strong("Correccion acumulada"),
            ui.span(
                f"AZ {number(sample['correction_az_deg'], 4)}° · "
                f"EL {number(sample['correction_el_deg'], 4)}°"
            ),
            class_="correction-readout",
        )

    @output
    @render.ui
    def drift_chart() -> object:
        revision.get()
        return ui.HTML(drift_svg(state, str(input.drift_display())))

    @reactive.effect
    @reactive.event(input.drift_chart_pick)
    def drift_chart_pick() -> None:
        selected = str(input.drift_chart_pick())
        if selected:
            ui.update_select("drift_display", selected=selected, session=session)

    @output
    @render.ui
    def diagnostic_view() -> object:
        revision.get()
        sample = state.snapshot()
        diagnostics = (
            ("Error acimut", number(sample["az_error_deg"], 3), "deg"),
            ("Error elevacion", number(sample["el_error_deg"], 3), "deg"),
            ("Error spot", number(sample["spot_radial_mm"], 3), "mm"),
            ("Altura solar", number(sample["altitude_deg"], 3), "deg"),
            ("Incidencia", number(sample["incidence_deg"], 3), "deg"),
            ("Reflejado vs target", number(sample["target_difference_deg"], 4), "deg"),
            ("Correccion AZ", number(sample["correction_az_deg"], 4), "deg"),
            ("Correccion EL", number(sample["correction_el_deg"], 4), "deg"),
            ("Error max. intervalo", number(sample["tracking_error_max_mm"], 3), "mm"),
            ("Error RMS intervalo", number(sample["tracking_error_rms_mm"], 3), "mm"),
            ("Encoder AZ", str(sample["az_encoder_counts"]), "conteos"),
            ("Encoder EL", str(sample["el_encoder_counts"]), "conteos"),
        )
        return ui.div(
            ui.h2("Diagnostico de seguimiento"),
            ui.div(
                *(
                    ui.div(
                        ui.div(label, class_="metric-label"),
                        ui.div(f"{value} {unit}", class_="metric-value"),
                        class_="metric-card",
                    )
                    for label, value, unit in diagnostics
                ),
                class_="diagnostic-grid",
            ),
            ui.div(
                ui.h3("Vectores geometricos"),
                ui.pre(
                    f"Sol S       {sample['sun']}\n"
                    f"Normal N    {sample['normal']}\n"
                    f"Reflejado   {sample['reflected']}\n"
                    f"Target R    {sample['target']}"
                ),
                class_="vector-card",
            ),
            ui.div(
                ui.h3("Configuracion experimental activa"),
                ui.p(f"Escenario: {sample['error_mode']} · Errores: {sample['active_errors']}"),
                ui.p(
                    f"Correccion: {sample['correction_strategy']} · actualizaciones {sample['correction_update_count']} · "
                    f"seguimiento {sample['tracking_update_interval_s']} s · capturas {sample['tracking_update_count']}"
                ),
                ui.p(
                    f"Motores AZ {'ON' if sample['az_motor_on'] else 'OFF'} / EL {'ON' if sample['el_motor_on'] else 'OFF'}"
                ),
                class_="vector-card",
            ),
            class_="diagnostic-panel",
        )

    @output
    @render.ui
    def events_view() -> object:
        revision.get()
        recent = list(reversed(state.events[-100:]))
        if not recent:
            return ui.div(ui.h2("Eventos y validaciones"), ui.p("No hay eventos registrados."), class_="diagnostic-panel")
        rows = [
            ui.tags.tr(
                ui.tags.td(item["timestamp"]),
                ui.tags.td(item["category"]),
                ui.tags.td(item["message"]),
            )
            for item in recent
        ]
        return ui.div(
            ui.h2("Eventos y validaciones"),
            ui.p("La bitacora conserva cambios operativos, correcciones, reloj, replay y actualizaciones de seguimiento."),
            ui.tags.table(
                ui.tags.thead(ui.tags.tr(ui.tags.th("Fecha y hora"), ui.tags.th("Tipo"), ui.tags.th("Detalle"))),
                ui.tags.tbody(*rows),
                class_="events-table",
            ),
            class_="diagnostic-panel",
        )

    @output
    @render.ui
    def readout_strip() -> object:
        revision.get()
        sample = state.snapshot()
        values = (
            ("Acimut", f"{number(sample['az_deg'])}°"),
            ("Elevacion", f"{number(sample['el_deg'])}°"),
            ("Impacto u / v", f"{number(sample['spot_u_mm'])} / {number(sample['spot_v_mm'])} mm"),
            ("Error radial", f"{number(sample['spot_radial_mm'])} mm"),
            ("Sol", f"Alt {number(sample['altitude_deg'])}° · Az {number(sample['solar_azimuth_deg'])}°"),
            ("Escenario", str(sample["error_mode"])),
            ("Muestras", str(len(state.history))),
        )
        return ui.div(
            *(ui.div(ui.span(label), ui.strong(value), class_="readout-item") for label, value in values),
            class_="readout-strip",
        )

    @output
    @render.download_button(filename=lambda: f"gemelo_web_{state.active_datetime():%Y%m%d_%H%M%S}.csv")
    def download_csv():  # type: ignore[no-untyped-def]
        yield state.export_csv_text()

    @output
    @render.download_button(filename=lambda: f"experimento_gemelo_{state.active_datetime():%Y%m%d_%H%M%S}.zip")
    def download_package():  # type: ignore[no-untyped-def]
        yield state.export_experiment_zip()


app = App(app_ui, server, static_assets=APP_DIR / "www")
