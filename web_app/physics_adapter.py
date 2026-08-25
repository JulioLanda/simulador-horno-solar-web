"""Adaptador entre el estado histórico de la aplicación y el núcleo físico V2.

La interfaz web conserva nombres, controles, historial y exportaciones creados
para la versión 0.4.0. El núcleo V2, en cambio, trabaja con entradas y resultados
inmutables. Este módulo es la única frontera entre ambos contratos.

No contiene fórmulas alternativas. La posición solar y la solución ideal se
obtienen de :mod:`physics_pipeline`; las poses alcanzadas, la reflexión y el
receptor se construyen exclusivamente con funciones de :mod:`physics_core`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

try:
    from .physics_core import (
        AxisCommands,
        LimitedCommands,
        MechanicalLimits,
        MirrorPose,
        ReceiverFrame,
        ReceiverImpact,
        Vector3,
        angle_between,
        apply_mechanical_limits,
        mirror_pose_from_altaz,
        receiver_frame,
        receiver_impact,
        reflected_direction,
    )
    from .physics_pipeline import (
        PhysicalStepInputs,
        PhysicalStepResult,
        simulate_physical_step,
    )
except ImportError:
    # Shinylive aplana estos archivos en la raíz de la aplicación exportada.
    from physics_core import (  # type: ignore[no-redef]
        AxisCommands,
        LimitedCommands,
        MechanicalLimits,
        MirrorPose,
        ReceiverFrame,
        ReceiverImpact,
        Vector3,
        angle_between,
        apply_mechanical_limits,
        mirror_pose_from_altaz,
        receiver_frame,
        receiver_impact,
        reflected_direction,
    )
    from physics_pipeline import (  # type: ignore[no-redef]
        PhysicalStepInputs,
        PhysicalStepResult,
        simulate_physical_step,
    )


# =============================================================================
# 1. TRADUCCIÓN DE NOMBRES DE MÉTODO SOLAR
# =============================================================================

_SOLAR_METHODS = {
    "d&b": "duffie_beckman",
    "db": "duffie_beckman",
    "duffie_beckman": "duffie_beckman",
    "reda": "reda",
    "spa": "spa",
    "spa/pvlib": "spa",
}


def solar_method_for_core(interface_name: str) -> str:
    """Convierte la etiqueta visible de la interfaz en una clave del núcleo."""

    key = str(interface_name).strip().lower()
    try:
        return _SOLAR_METHODS[key]
    except KeyError as error:
        raise ValueError(f"Método solar de interfaz desconocido: {interface_name!r}") from error


# =============================================================================
# 2. ENTRADAS INMUTABLES DEL ADAPTADOR
# =============================================================================

@dataclass(frozen=True)
class WebScenarioRequest:
    """Pose motorizada y errores que definen un escenario de presentación.

    ``motor_commands`` son los ángulos que muestran los encoders. El peralte
    nominal se descuenta al reconstruir la pose óptica, mientras que los dos
    errores angulares se suman a sus ejes físicos correspondientes.
    """

    name: str
    motor_commands: AxisCommands
    target_offset: Vector3
    azimuth_error_deg: float = 0.0
    height_error_deg: float = 0.0


@dataclass(frozen=True)
class WebPhysicsRequest:
    """Todos los datos requeridos para evaluar el instante mostrado por la web."""

    when: dt.datetime
    latitude_deg: float
    longitude_deg: float
    utc_offset_hours: float
    receiver_offset: Vector3
    current_motor_commands: AxisCommands
    scenarios: tuple[WebScenarioRequest, ...]
    selected_scenario: str
    solar_method: str
    pivot_height_m: float = 2.20
    site_altitude_m: float = 1280.0
    pressure_pa: float = 101325.0
    temperature_c: float = 25.0
    minimum_solar_altitude_deg: float = 0.0
    peralte_deg: float = 0.0
    camera_offset_az_deg: float = 0.0
    camera_offset_height_deg: float = 0.0
    limits: MechanicalLimits = MechanicalLimits()
    fallback_azimuth_deg: float = 0.0


# =============================================================================
# 3. RESULTADOS TRAZABLES PARA LA INTERFAZ
# =============================================================================

@dataclass(frozen=True)
class WebScenarioGeometry:
    """Pose completa y resultado óptico de uno de los escenarios históricos."""

    name: str
    target_offset: Vector3
    target_direction: Vector3 | None
    pose: MirrorPose
    reflected: Vector3 | None
    receiver: ReceiverFrame | None
    impact: ReceiverImpact | None
    incidence_deg: float | None
    reflection_deg: float | None
    target_difference_deg: float | None


@dataclass(frozen=True)
class WebPhysicsResult:
    """Resultado del pipeline ideal más las poses actualmente alcanzadas."""

    ideal_step: PhysicalStepResult
    control_targets: LimitedCommands | None
    current_motor_limits: LimitedCommands
    scenarios: tuple[WebScenarioGeometry, ...]
    selected: WebScenarioGeometry

    def scenario(self, name: str) -> WebScenarioGeometry:
        """Devuelve un escenario por nombre o informa un contrato incompleto."""

        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        raise KeyError(f"Escenario físico ausente: {name}")


# =============================================================================
# 4. CONSTRUCCIÓN DE LA SOLUCIÓN IDEAL Y OBJETIVOS DE CONTROL
# =============================================================================

def _global_point(origin: Vector3, offset: Vector3) -> Vector3:
    """Traslada un vector relativo sin introducir álgebra vectorial duplicada."""

    return tuple(
        origin_component + offset_component
        for origin_component, offset_component in zip(origin, offset, strict=True)
    )  # type: ignore[return-value]


def _ideal_step(request: WebPhysicsRequest) -> PhysicalStepResult:
    """Ejecuta el pipeline V2 con la geometría global correspondiente a la web."""

    pivot: Vector3 = (0.0, 0.0, request.pivot_height_m)
    receiver = _global_point(pivot, request.receiver_offset)
    return simulate_physical_step(
        PhysicalStepInputs(
            when=request.when,
            latitude_deg=request.latitude_deg,
            longitude_deg=request.longitude_deg,
            utc_offset_hours=request.utc_offset_hours,
            heliostat_center=pivot,
            receiver_center=receiver,
            solar_method=solar_method_for_core(request.solar_method),
            site_altitude_m=request.site_altitude_m,
            pressure_pa=request.pressure_pa,
            temperature_c=request.temperature_c,
            minimum_solar_altitude_deg=request.minimum_solar_altitude_deg,
            limits=request.limits,
            fallback_azimuth_deg=request.fallback_azimuth_deg,
        )
    )


def _control_targets(
    request: WebPhysicsRequest,
    ideal_step: PhysicalStepResult,
) -> LimitedCommands | None:
    """Convierte la normal ideal en órdenes de encoder y aplica los límites."""

    if ideal_step.ideal_commands is None:
        return None
    desired = AxisCommands(
        azimuth_deg=(
            ideal_step.ideal_commands.azimuth_deg + request.camera_offset_az_deg
        ),
        height_deg=(
            ideal_step.ideal_commands.height_deg
            + request.peralte_deg
            + request.camera_offset_height_deg
        ),
    )
    return apply_mechanical_limits(desired, request.limits)


# =============================================================================
# 5. RECONSTRUCCIÓN DE CADA POSE REAL Y SU RAYO
# =============================================================================

def _scenario_geometry(
    request: WebPhysicsRequest,
    ideal_step: PhysicalStepResult,
    scenario: WebScenarioRequest,
) -> WebScenarioGeometry:
    """Evalúa un escenario usando la pose completa de la montura altazimutal."""

    optical_azimuth = (
        scenario.motor_commands.azimuth_deg + scenario.azimuth_error_deg
    )
    optical_height = (
        scenario.motor_commands.height_deg
        - request.peralte_deg
        + scenario.height_error_deg
    )
    pose = mirror_pose_from_altaz(optical_azimuth, optical_height)

    # Durante la noche se conserva la pose mecánica, pero no se fabrica un rayo.
    if not ideal_step.operational:
        return WebScenarioGeometry(
            name=scenario.name,
            target_offset=scenario.target_offset,
            target_direction=None,
            pose=pose,
            reflected=None,
            receiver=None,
            impact=None,
            incidence_deg=None,
            reflection_deg=None,
            target_difference_deg=None,
        )

    pivot: Vector3 = (0.0, 0.0, request.pivot_height_m)
    receiver_center = _global_point(pivot, scenario.target_offset)
    frame = receiver_frame(receiver_center, heliostat_center=pivot)
    incident = tuple(-component for component in ideal_step.sun_direction)
    reflected = reflected_direction(incident, pose.normal)  # type: ignore[arg-type]
    impact = receiver_impact(pivot, reflected, frame)
    target_direction = frame.normal
    return WebScenarioGeometry(
        name=scenario.name,
        target_offset=scenario.target_offset,
        target_direction=target_direction,
        pose=pose,
        reflected=reflected,
        receiver=frame,
        impact=impact,
        incidence_deg=angle_between(ideal_step.sun_direction, pose.normal),
        reflection_deg=angle_between(reflected, pose.normal),
        target_difference_deg=angle_between(reflected, target_direction),
    )


# =============================================================================
# 6. API PÚBLICA DEL ADAPTADOR
# =============================================================================

def evaluate_web_physics(request: WebPhysicsRequest) -> WebPhysicsResult:
    """Evalúa un instante sin depender de Shiny ni mutar el estado histórico."""

    if not request.scenarios:
        raise ValueError("Se requiere al menos un escenario para la interfaz")
    ideal_step = _ideal_step(request)
    targets = _control_targets(request, ideal_step)
    scenarios = tuple(
        _scenario_geometry(request, ideal_step, scenario)
        for scenario in request.scenarios
    )
    selected = next(
        (scenario for scenario in scenarios if scenario.name == request.selected_scenario),
        None,
    )
    if selected is None:
        raise ValueError(
            f"Escenario seleccionado ausente: {request.selected_scenario!r}"
        )
    current_limits = apply_mechanical_limits(
        request.current_motor_commands,
        request.limits,
    )
    return WebPhysicsResult(
        ideal_step=ideal_step,
        control_targets=targets,
        current_motor_limits=current_limits,
        scenarios=scenarios,
        selected=selected,
    )


__all__ = [
    "WebPhysicsRequest",
    "WebPhysicsResult",
    "WebScenarioGeometry",
    "WebScenarioRequest",
    "evaluate_web_physics",
    "solar_method_for_core",
]
