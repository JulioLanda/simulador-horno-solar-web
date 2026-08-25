"""Orquestación de un instante físico completo del miniheliostato.

Este módulo conecta, en el orden físico correcto, las funciones matemáticas de
``physics_core.py``. No contiene ecuaciones alternativas, estado de Shiny,
JavaScript, animaciones ni lógica de presentación.

La separación tiene dos objetivos:

* ``physics_core.py`` sigue siendo la fuente única de cada cálculo matemático.
* La aplicación dispone de una sola función para obtener todos los resultados
  intermedios de un instante y mostrarlos, exportarlos o diagnosticarlos.

Cadena ejecutada
----------------

1. Posición y vector solar.
2. Comprobación de disponibilidad solar.
3. Dirección desde el heliostato hacia el receptor.
4. Normal ideal del espejo.
5. Cinemática inversa para obtener los comandos ideales.
6. Aplicación de offsets y límites mecánicos independientes.
7. Cinemática directa para reconstruir la pose realmente alcanzada.
8. Reflexión del rayo solar con la normal real.
9. Intersección y error sobre el plano receptor.

Cuando el Sol no supera la altura mínima, la cadena se detiene después del
paso 2. El resultado conserva la posición solar, pero deja en ``None`` todos
los valores que no deben inventarse.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# En pruebas normales el archivo forma parte del paquete ``web_app``. Durante
# la exportación aislada de Shinylive se copia junto a ``physics_core.py`` en la
# raíz de la miniaplicación; el segundo import conserva exactamente el mismo
# código matemático sin duplicarlo dentro del repositorio.
try:
    from .physics_core import (
        AxisCommands,
        LimitedCommands,
        MechanicalLimits,
        MirrorPose,
        ReceiverFrame,
        ReceiverImpact,
        SolarPosition,
        Vector3,
        apply_encoder_offsets,
        apply_mechanical_limits,
        azimuth_height_from_direction,
        ideal_heliostat_normal,
        mirror_pose_from_altaz,
        receiver_frame,
        receiver_impact,
        reflected_direction,
        solar_vector,
        sun_is_operational,
        target_direction,
    )
except ImportError:
    from physics_core import (  # type: ignore[no-redef]
        AxisCommands,
        LimitedCommands,
        MechanicalLimits,
        MirrorPose,
        ReceiverFrame,
        ReceiverImpact,
        SolarPosition,
        Vector3,
        apply_encoder_offsets,
        apply_mechanical_limits,
        azimuth_height_from_direction,
        ideal_heliostat_normal,
        mirror_pose_from_altaz,
        receiver_frame,
        receiver_impact,
        reflected_direction,
        solar_vector,
        sun_is_operational,
        target_direction,
    )


# =============================================================================
# 1. ENTRADAS INMUTABLES DE UN INSTANTE
# =============================================================================

@dataclass(frozen=True)
class PhysicalStepInputs:
    """Datos necesarios para evaluar un solo instante de la simulación.

    Las posiciones geométricas se expresan en metros y en el sistema global
    ``+x`` oeste, ``+y`` sur y ``+z`` cenit. ``receiver_center`` es una
    posición global, no un desplazamiento relativo.

    Los valores geométricos predeterminados corresponden al perfil Minihorno
    IER actualmente documentado:

    * centro de giro a ``2.20 m`` sobre el suelo;
    * receptor ``(0.00, 5.55, -0.40) m`` respecto del centro de giro;
    * por tanto, centro global predeterminado del receptor en ``z = 1.80 m``.

    ``fallback_azimuth_deg`` resuelve el único caso singular de la cinemática
    inversa: cuando la normal ideal es vertical y su acimut es indeterminado.
    Más adelante la aplicación podrá suministrar aquí el acimut del instante
    anterior para conservar continuidad temporal.
    """

    # Fecha y hora civil local del instante que se desea calcular.
    when: dt.datetime

    # Latitud geográfica en grados: norte positivo y sur negativo.
    latitude_deg: float

    # Longitud geográfica en grados: este positivo y oeste negativo.
    longitude_deg: float

    # Diferencia fija entre la hora civil suministrada y UTC, en horas.
    utc_offset_hours: float

    # Centro óptico o pivote del espejo expresado en coordenadas globales.
    heliostat_center: Vector3 = (0.0, 0.0, 2.20)

    # Centro global del receptor: (0, 5.55, -0.40) respecto del pivote.
    receiver_center: Vector3 = (0.0, 5.55, 1.80)

    # Normal opcional del receptor; None usa la línea heliostato-receptor.
    receiver_plane_normal: Vector3 | None = None

    # Método solar explícito: reda, spa o duffie_beckman.
    solar_method: str = "reda"

    # Altitud geográfica del emplazamiento sobre el nivel del mar.
    site_altitude_m: float = 0.0

    # Presión atmosférica usada por NREL SPA para la refracción aparente.
    pressure_pa: float = 101325.0

    # Temperatura ambiente usada por NREL SPA para la refracción aparente.
    temperature_c: float = 12.0

    # Diferencia TT-UT1 opcional; None permite a pvlib estimarla.
    delta_t_s: float | None = None

    # Umbral estricto de operación: el Sol debe estar por encima de este valor.
    minimum_solar_altitude_deg: float = 0.0

    # Error de referencia del motor de acimut, positivo hacia el oeste.
    azimuth_offset_deg: float = 0.0

    # Error de referencia del motor de altura, en grados del eje físico.
    height_offset_deg: float = 0.0

    # Límites cerrados e independientes de los dos motores.
    limits: MechanicalLimits = MechanicalLimits()

    # Acimut que debe conservarse cuando la normal calculada sea vertical.
    fallback_azimuth_deg: float = 0.0


# =============================================================================
# 2. RESULTADO INMUTABLE Y TRAZABLE
# =============================================================================

@dataclass(frozen=True)
class PhysicalStepResult:
    """Resultado completo o parcial de un instante físico.

    ``valid`` indica que el Sol era operativo y que el rayo alcanzó hacia
    delante el plano infinito del receptor. No significa que el impacto esté
    dentro del área útil de una abertura concreta; esa comprobación requerirá
    las dimensiones finales del receptor.

    Los campos opcionales quedan en ``None`` exclusivamente cuando el Sol no
    está disponible. Para un Sol operativo se conservan todos los resultados,
    incluso si la intersección resulta inválida, porque son información útil
    para diagnosticar signos, límites y errores mecánicos.
    """

    # True únicamente cuando existe un impacto válido hacia delante.
    valid: bool

    # True cuando la elevación solar supera estrictamente el umbral configurado.
    operational: bool

    # Etiqueta estable que explica el resultado principal del instante.
    reason: str

    # Posición solar calculada aun cuando el Sol no sea operativo.
    solar_position: SolarPosition

    # Vector unitario que apunta del heliostato hacia el Sol.
    sun_direction: Vector3

    # Vector unitario desde el heliostato hacia el centro del receptor.
    target_direction: Vector3 | None

    # Bisectriz ideal que dirigiría el reflejo al centro del receptor.
    ideal_normal: Vector3 | None

    # Comandos obtenidos de la normal ideal antes de introducir errores.
    ideal_commands: AxisCommands | None

    # Comandos solicitados después de sumar offsets de referencia o encoder.
    offset_commands: AxisCommands | None

    # Comandos realmente aplicables y etiquetas de límites alcanzados.
    limited_commands: LimitedCommands | None

    # Pose real reconstruida desde los comandos ya limitados.
    actual_pose: MirrorPose | None

    # Dirección de propagación del rayo después de reflejarse.
    reflected_direction: Vector3 | None

    # Base local del plano receptor usada para expresar u y v.
    receiver_frame: ReceiverFrame | None

    # Intersección, coordenadas locales y error radial del rayo reflejado.
    impact: ReceiverImpact | None


# =============================================================================
# 3. EVALUACIÓN DE UN INSTANTE FÍSICO
# =============================================================================

def simulate_physical_step(inputs: PhysicalStepInputs) -> PhysicalStepResult:
    """Ejecuta una vez la cadena física utilizando exclusivamente el núcleo.

    La función es pura respecto del estado de la aplicación: no guarda
    historiales ni consulta controles visuales. La misma entrada produce el
    mismo resultado y puede probarse sin iniciar Shiny o un navegador.
    """

    # -------------------------------------------------------------------------
    # 3.1 Posición y vector solar
    # -------------------------------------------------------------------------

    # Delegar el algoritmo astronómico y la conversión de ejes a physics_core.
    solar_position_value, sun_direction_value = solar_vector(
        inputs.when,
        inputs.latitude_deg,
        inputs.longitude_deg,
        inputs.utc_offset_hours,
        method=inputs.solar_method,
        altitude_m=inputs.site_altitude_m,
        pressure_pa=inputs.pressure_pa,
        temperature_c=inputs.temperature_c,
        delta_t_s=inputs.delta_t_s,
    )

    # Evaluar el umbral mediante la misma regla estricta documentada en el core.
    operational = sun_is_operational(
        solar_position_value.altitude_deg,
        minimum_deg=inputs.minimum_solar_altitude_deg,
    )

    # Un Sol no operativo no debe generar comandos, pose ni un impacto ficticio.
    if not operational:
        return PhysicalStepResult(
            valid=False,
            operational=False,
            reason="sol_fuera_de_operacion",
            solar_position=solar_position_value,
            sun_direction=sun_direction_value,
            target_direction=None,
            ideal_normal=None,
            ideal_commands=None,
            offset_commands=None,
            limited_commands=None,
            actual_pose=None,
            reflected_direction=None,
            receiver_frame=None,
            impact=None,
        )

    # -------------------------------------------------------------------------
    # 3.2 Solución óptica y cinemática ideal
    # -------------------------------------------------------------------------

    # Obtener la dirección nominal desde el centro óptico hasta el receptor.
    target_direction_value = target_direction(
        inputs.heliostat_center,
        inputs.receiver_center,
    )

    # Calcular la bisectriz que refleja el rayo solar hacia esa dirección.
    ideal_normal_value = ideal_heliostat_normal(
        sun_direction_value,
        target_direction_value,
    )

    # Convertir la normal ideal en posiciones independientes de ambos motores.
    ideal_commands_value = azimuth_height_from_direction(
        ideal_normal_value,
        fallback_azimuth_deg=inputs.fallback_azimuth_deg,
    )

    # -------------------------------------------------------------------------
    # 3.3 Errores de referencia y límites mecánicos
    # -------------------------------------------------------------------------

    # Sumar cada offset únicamente al motor al cual pertenece.
    offset_commands_value = apply_encoder_offsets(
        ideal_commands_value,
        azimuth_offset_deg=inputs.azimuth_offset_deg,
        height_offset_deg=inputs.height_offset_deg,
    )

    # Saturar ambos ejes de forma independiente y conservar sus etiquetas.
    limited_commands_value = apply_mechanical_limits(
        offset_commands_value,
        inputs.limits,
    )

    # -------------------------------------------------------------------------
    # 3.4 Pose real y reflexión
    # -------------------------------------------------------------------------

    # La cinemática directa usa solo los ángulos que la montura puede alcanzar.
    actual_pose_value = mirror_pose_from_altaz(
        limited_commands_value.applied.azimuth_deg,
        limited_commands_value.applied.height_deg,
    )

    # El vector solar apunta hacia el Sol; el rayo incidente viaja al contrario.
    incident_direction: Vector3 = (
        -sun_direction_value[0],
        -sun_direction_value[1],
        -sun_direction_value[2],
    )

    # Aplicar la ley de reflexión con la normal realmente alcanzada, no la ideal.
    reflected_direction_value = reflected_direction(
        incident_direction,
        actual_pose_value.normal,
    )

    # -------------------------------------------------------------------------
    # 3.5 Plano receptor, impacto y estado final
    # -------------------------------------------------------------------------

    # Construir el plano nominal o respetar la normal explícita configurada.
    receiver_frame_value = receiver_frame(
        inputs.receiver_center,
        heliostat_center=inputs.heliostat_center,
        plane_normal=inputs.receiver_plane_normal,
    )

    # Intersectar el rayo reflejado y expresar el punto en coordenadas u y v.
    impact_value = receiver_impact(
        inputs.heliostat_center,
        reflected_direction_value,
        receiver_frame_value,
    )

    # Propagar sin traducción la razón geométrica producida por physics_core.
    return PhysicalStepResult(
        valid=impact_value.valid,
        operational=True,
        reason=impact_value.reason,
        solar_position=solar_position_value,
        sun_direction=sun_direction_value,
        target_direction=target_direction_value,
        ideal_normal=ideal_normal_value,
        ideal_commands=ideal_commands_value,
        offset_commands=offset_commands_value,
        limited_commands=limited_commands_value,
        actual_pose=actual_pose_value,
        reflected_direction=reflected_direction_value,
        receiver_frame=receiver_frame_value,
        impact=impact_value,
    )


# =============================================================================
# 4. API PÚBLICA DEL ORQUESTADOR
# =============================================================================

# Exponer solamente las dos estructuras de datos y la operación de un instante.
__all__ = [
    "PhysicalStepInputs",
    "PhysicalStepResult",
    "simulate_physical_step",
]
