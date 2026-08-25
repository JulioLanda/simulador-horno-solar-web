"""Núcleo matemático puro para el simulador web del Minihorno IER.

Este módulo no conoce Shiny, JavaScript, controles de interfaz, historiales ni
archivos de exportación. Sus funciones reciben datos explícitos y devuelven
resultados inmutables que pueden probarse de forma independiente.

Responsabilidad de las bibliotecas
----------------------------------

* ``NumPy`` realiza el álgebra vectorial: suma, resta, producto punto,
  producto cruz, norma, normalización y funciones trigonométricas.
* ``SciPy`` realiza las rotaciones tridimensionales mediante
  ``scipy.spatial.transform.Rotation``.
* ``pvlib`` calcula la posición solar Duffie-Beckman y NREL SPA.
* Este módulo conserva únicamente auxiliares privados para validar dimensiones
  y unidades y para convertir resultados a tuplas inmutables. Las funciones
  físicas usan directamente arreglos NumPy durante sus cálculos.

Convención global del proyecto
------------------------------

* ``+x`` apunta al oeste.
* ``+y`` apunta al sur.
* ``+z`` apunta al cenit.
* Acimut ``0°`` apunta al sur y crece hacia el oeste.
* Altura ``90°`` representa el espejo horizontal (Home).
* Altura ``10°`` representa el límite casi vertical.

La posición solar se obtiene mediante funciones de ``pvlib``. Este archivo
solo valida entradas, selecciona el método y convierte el acimut a la
convención del proyecto; no reimplementa los algoritmos astronómicos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

# Las anotaciones de pandas se cargan solo para análisis estático. En ejecución,
# pandas se importa de forma diferida cuando realmente se pide posición solar.
if TYPE_CHECKING:
    import pandas as pd


# =============================================================================
# 1. CONVENCIONES, TIPOS Y RESULTADOS INMUTABLES
# =============================================================================

# 1.1 Tipos, tolerancia y vectores globales
# -----------------------------------------------------------------------------

# Tipo público: los vectores salen del núcleo como tuplas inmutables.
Vector3 = tuple[float, float, float]

# Una orientación se expresa mediante tres vectores columna: e, p y n.
Matrix3Columns = tuple[Vector3, Vector3, Vector3]

# Tipo interno empleado exclusivamente para operar con NumPy.
VectorArray = NDArray[np.float64]

# Tolerancia numérica para detectar magnitudes y denominadores casi nulos.
EPSILON = 1.0e-12

# Vector vertical global: apunta del suelo hacia el cenit.
UP: Vector3 = (0.0, 0.0, 1.0)

# Vector horizontal global: apunta hacia el oeste.
WEST: Vector3 = (1.0, 0.0, 0.0)


# 1.2 Estructuras de resultados
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SolarPosition:
    """Resultado solar normalizado a la convención angular del proyecto.

    Attributes:
        zenith_deg: Ángulo desde el cenit. SPA entrega el valor aparente;
            Duffie-Beckman entrega el geométrico.
        altitude_deg: Elevación sobre el horizonte, igual a ``90° - cenit``.
        azimuth_deg: Cero al sur, positivo al oeste y negativo al este.
        method: Identificador inequívoco de la rutina de biblioteca utilizada.
        equation_of_time_min: Ecuación del tiempo en minutos, si el método la
            proporciona.
    """

    zenith_deg: float
    altitude_deg: float
    azimuth_deg: float
    method: str
    equation_of_time_min: float | None = None


@dataclass(frozen=True)
class AxisCommands:
    """Comandos angulares independientes enviados a la montura.

    ``azimuth_deg`` aumenta hacia el oeste. ``height_deg`` vale ``90°`` con
    el espejo horizontal y disminuye hasta ``10°`` al acercarse a la vertical.
    """

    azimuth_deg: float
    height_deg: float


@dataclass(frozen=True)
class MechanicalLimits:
    """Intervalos físicos cerrados permitidos para ambos motores.

    La clase valida los límites al construirse para impedir que un intervalo
    invertido alcance el cálculo de comandos.
    """

    azimuth_min_deg: float = -90.0
    azimuth_max_deg: float = 90.0
    height_min_deg: float = 10.0
    height_max_deg: float = 90.0

    def __post_init__(self) -> None:
        """Valida finitud y orden inmediatamente después del constructor."""

        # Un NaN haría falsas las comparaciones de límites; se rechaza primero.
        _require_finite(
            self.azimuth_min_deg,
            self.azimuth_max_deg,
            self.height_min_deg,
            self.height_max_deg,
        )
        # El intervalo de acimut debe tener una amplitud estrictamente positiva.
        if self.azimuth_min_deg >= self.azimuth_max_deg:
            raise ValueError("El límite mínimo de acimut debe ser menor que el máximo")
        # La misma condición se exige al intervalo del motor de altura.
        if self.height_min_deg >= self.height_max_deg:
            raise ValueError("El límite mínimo de altura debe ser menor que el máximo")


@dataclass(frozen=True)
class LimitedCommands:
    """Orden original, orden físicamente aplicable y estados de saturación."""

    requested: AxisCommands
    applied: AxisCommands
    limit_labels: tuple[str, ...]

    @property
    def limited(self) -> bool:
        """Indica si la orden se recortó o quedó exactamente sobre un límite."""

        return bool(self.limit_labels)


@dataclass(frozen=True)
class MirrorPose:
    """Pose completa del espejo obtenida mediante la montura altazimutal.

    ``orientation_columns`` contiene los ejes locales del espejo expresados en
    coordenadas globales: arista horizontal, dirección hacia la parte superior
    y normal, en ese orden.
    """

    azimuth_deg: float
    height_deg: float
    normal: Vector3
    horizontal_edge: Vector3
    upper_direction: Vector3
    orientation_columns: Matrix3Columns


@dataclass(frozen=True)
class ReceiverFrame:
    """Base ortonormal que define el plano y coordenadas del receptor.

    ``normal`` es perpendicular al plano, ``u_axis`` apunta al oeste y
    ``v_axis`` apunta hacia el cenit.
    """

    center: Vector3
    normal: Vector3
    u_axis: Vector3
    v_axis: Vector3


@dataclass(frozen=True)
class RayPlaneIntersection:
    """Resultado explícito de una intersección entre un rayo y un plano.

    Los campos opcionales quedan en ``None`` cuando la intersección no existe.
    ``reason`` permite distinguir un rayo paralelo de un impacto situado detrás
    de su origen.
    """

    valid: bool
    point: Vector3 | None
    ray_parameter_m: float | None
    reason: str


@dataclass(frozen=True)
class ReceiverImpact:
    """Impacto de un rayo expresado en las coordenadas locales del receptor.

    ``u_m`` y ``v_m`` son desplazamientos respecto del centro. El error radial
    es su distancia euclidiana bidimensional.
    """

    valid: bool
    point: Vector3 | None
    u_m: float | None
    v_m: float | None
    radial_error_m: float | None
    ray_parameter_m: float | None
    reason: str


# =============================================================================
# 2. OPERACIONES ESCALARES Y VECTORIALES
# =============================================================================

# 2.0 Validación y conversiones en la frontera NumPy/tupla
# -----------------------------------------------------------------------------

def _require_finite(*values: float) -> None:
    """Rechaza entradas escalares que contengan NaN o infinito.

    NumPy evalúa todos los valores de una vez. Esta validación común evita que
    un NaN se propague silenciosamente por varias operaciones geométricas.
    """

    # Convertir a un arreglo numérico permite aplicar una validación vectorizada.
    numeric_values = np.asarray(values, dtype=np.float64)

    # ``np.all`` exige que cada elemento satisfaga ``np.isfinite``.
    if not bool(np.all(np.isfinite(numeric_values))):
        raise ValueError("Todas las entradas numéricas deben ser finitas")


def _vector_array(vector: Vector3 | VectorArray) -> VectorArray:
    """Convierte una entrada tridimensional en un arreglo validado de NumPy.

    La forma ``(3,)`` es intencional: se rechazan matrices ``(1, 3)`` o
    ``(3, 1)`` para que el broadcasting de NumPy no oculte un error de entrada.
    """

    # NumPy realiza la conversión de listas, tuplas o arreglos a punto flotante.
    array = np.asarray(vector, dtype=np.float64)

    # Un vector del núcleo debe contener exactamente tres escalares en una fila.
    if array.shape != (3,):
        raise ValueError("Un vector tridimensional debe tener tres componentes")

    # Se comprueba el arreglo completo antes de enviarlo a álgebra lineal.
    if not bool(np.all(np.isfinite(array))):
        raise ValueError("Todas las componentes del vector deben ser finitas")

    return array


def _array_to_vector(array: VectorArray) -> Vector3:
    """Devuelve un resultado de NumPy como tupla inmutable del API público."""

    # Validar nuevamente protege la frontera de salida del núcleo.
    validated = _vector_array(array)

    # ``float`` evita exponer escalares ``np.float64`` al resto de la aplicación.
    return (float(validated[0]), float(validated[1]), float(validated[2]))


# 2.1 Recorte y envoltura angular
# -----------------------------------------------------------------------------

def clamp(value: float, low: float, high: float) -> float:
    """Limita un escalar al intervalo cerrado ``[low, high]`` con NumPy.

    Raises:
        ValueError: Si una entrada no es finita o el intervalo está invertido.
    """

    # La validación ocurre antes de comparar para manejar correctamente NaN.
    _require_finite(value, low, high)

    # Un intervalo invertido sería aceptado de forma ambigua por algunas APIs.
    if low > high:
        raise ValueError("El límite inferior no puede superar al límite superior")

    # ``np.clip`` es la operación estándar de NumPy para saturar valores.
    return float(np.clip(value, low, high))


def wrap_degrees(angle_deg: float) -> float:
    """Envuelve un ángulo al intervalo ``[-180°, 180°)`` mediante módulo."""

    # Un ángulo infinito no posee una representación modular útil.
    _require_finite(angle_deg)

    # Desplazar, aplicar módulo 360 y regresar el origen al centro del intervalo.
    return (float(angle_deg) + 180.0) % 360.0 - 180.0


# 2.2 Suma, resta y multiplicación por un escalar
# -----------------------------------------------------------------------------
# No existen funciones envolventes: los arreglos usan directamente ``+``, ``-``
# y ``*``. NumPy ejecuta las operaciones componente a componente.

# 2.3 Producto punto, producto cruz y norma
# -----------------------------------------------------------------------------
# Se usan directamente ``np.dot``, ``np.cross`` y ``np.linalg.norm`` en las
# funciones físicas que necesitan cada operación.

# 2.4 Vector unitario y ángulo entre vectores
# -----------------------------------------------------------------------------

def _unit_vector_array(
    vector: Vector3 | VectorArray,
    *,
    epsilon: float = EPSILON,
) -> VectorArray:
    """Valida y normaliza un vector; devuelve un arreglo interno de NumPy.

    Esta es una responsabilidad propia del dominio: además de calcular la norma
    con ``numpy.linalg.norm``, rechaza vectores cuya magnitud sea demasiado
    pequeña para tener una dirección física confiable.
    """

    # Convertir y validar una sola vez mantiene el arreglo durante todo el cálculo.
    array = _vector_array(vector)

    # La tolerancia debe ser positiva y finita para definir el umbral de rechazo.
    _require_finite(epsilon)
    if epsilon <= 0.0:
        raise ValueError("epsilon debe ser positivo")

    # NumPy calcula directamente la norma euclidiana del arreglo tridimensional.
    magnitude = float(np.linalg.norm(array))
    if magnitude < epsilon:
        raise ValueError("No se puede normalizar un vector nulo")

    # La división permanece en NumPy; no se convierte aún a una tupla pública.
    return array / magnitude


def angle_between(a: Vector3, b: Vector3) -> float:
    """Devuelve en grados el ángulo menor entre dos vectores.

    NumPy realiza la normalización, el producto punto, el recorte y el arcocoseno.
    """

    # Normalizar elimina la influencia de las magnitudes originales.
    a_unit = _unit_vector_array(a)
    b_unit = _unit_vector_array(b)

    # El producto punto de unitarios equivale al coseno del ángulo.
    cosine = float(np.clip(np.dot(a_unit, b_unit), -1.0, 1.0))

    # ``np.arccos`` trabaja en radianes; ``np.degrees`` convierte la salida.
    return float(np.degrees(np.arccos(cosine)))


# 2.5 Rotación de Rodrigues mediante SciPy
# -----------------------------------------------------------------------------

def rotate_about_axis(vector: Vector3, axis: Vector3, angle_deg: float) -> Vector3:
    """Rota un vector con ``scipy.spatial.transform.Rotation``.

    SciPy representa la rotación mediante un vector de rotación: su dirección
    es el eje unitario y su magnitud es el ángulo en radianes. Internamente es
    equivalente a la fórmula de Rodrigues, pero no se reimplementa aquí.
    """

    # Validar el vector que recibirá la transformación de SciPy.
    vector_array = _vector_array(vector)

    # SciPy requiere un eje unitario para que la magnitud sea exactamente el ángulo.
    axis_array = _unit_vector_array(axis)

    # Rechazar NaN o infinito antes de convertir unidades.
    _require_finite(angle_deg)

    # Formar el vector de rotación requerido por ``Rotation.from_rotvec``.
    rotation_vector = axis_array * np.deg2rad(float(angle_deg))

    # Construir la rotación y aplicarla al vector sin alterar su magnitud.
    rotated = Rotation.from_rotvec(rotation_vector).apply(vector_array)
    return _array_to_vector(rotated)


# =============================================================================
# 3. CINEMÁTICA ALTAZIMUTAL
# =============================================================================

# 3.1 Dirección definida por acimut y altura
# -----------------------------------------------------------------------------

def _direction_array_from_azimuth_height(
    azimuth_deg: float,
    height_deg: float,
) -> VectorArray:
    """Calcula internamente la dirección altazimutal como arreglo NumPy.

    La ecuación implementa la convención ``+x`` oeste, ``+y`` sur y ``+z``
    cenit. Mantener el arreglo evita conversiones intermedias en otras funciones
    del núcleo.
    """

    # Validar antes de aplicar funciones trigonométricas periódicas.
    _require_finite(azimuth_deg, height_deg)

    # NumPy recibe radianes; la API pública del proyecto recibe grados.
    azimuth_rad = float(np.deg2rad(azimuth_deg))
    height_rad = float(np.deg2rad(height_deg))

    # Construir simultáneamente las tres componentes de la dirección altazimutal.
    direction = np.array(
        [
            np.cos(height_rad) * np.sin(azimuth_rad),
            np.cos(height_rad) * np.cos(azimuth_rad),
            np.sin(height_rad),
        ],
        dtype=np.float64,
    )
    return direction


def direction_from_azimuth_height(azimuth_deg: float, height_deg: float) -> Vector3:
    """Devuelve como tupla la dirección global definida por acimut y altura."""

    # La conversión a tupla ocurre únicamente en esta frontera pública.
    return _array_to_vector(
        _direction_array_from_azimuth_height(azimuth_deg, height_deg)
    )


# 3.2 Conversión inversa: dirección a comandos de los motores
# -----------------------------------------------------------------------------

def azimuth_height_from_direction(
    direction: Vector3,
    *,
    fallback_azimuth_deg: float = 0.0,
) -> AxisCommands:
    """Obtiene con NumPy los comandos altazimutales de una dirección.

    Cuando la dirección es vertical el acimut es indeterminado. En ese caso se
    conserva ``fallback_azimuth_deg`` para impedir saltos de orientación.
    """

    # La inversión supone una dirección unitaria; se normaliza explícitamente.
    direction_array = _unit_vector_array(direction)

    # El valor alternativo también debe ser un ángulo numérico válido.
    _require_finite(fallback_azimuth_deg)

    # La proyección horizontal determina si el acimut está definido.
    horizontal = float(np.hypot(direction_array[0], direction_array[1]))
    if horizontal < EPSILON:
        # En el cenit, conservar el acimut evita un giro arbitrario del cuadrado.
        azimuth_deg = wrap_degrees(fallback_azimuth_deg)
    else:
        # ``atan2(x, y)`` refleja que el cero del proyecto está en +y (sur).
        azimuth_deg = wrap_degrees(
            float(np.degrees(np.arctan2(direction_array[0], direction_array[1])))
        )

    # Recortar n_z protege ``arcsin`` frente a pequeños excesos por redondeo.
    height_deg = float(
        np.degrees(np.arcsin(np.clip(direction_array[2], -1.0, 1.0)))
    )
    return AxisCommands(azimuth_deg=azimuth_deg, height_deg=height_deg)


# 3.3 Base completa y orientación del espejo
# -----------------------------------------------------------------------------

def mirror_pose_from_altaz(azimuth_deg: float, height_deg: float) -> MirrorPose:
    """Construye la pose completa respetando los dos ejes de la montura.

    La arista horizontal depende del acimut, pero no de la altura. Por ello
    permanece paralela al suelo incluso en Home, donde la normal es vertical y
    no bastaría por sí sola para fijar la orientación del cuadrado.
    """

    # Los ángulos serán usados tanto por NumPy como por las validaciones físicas.
    _require_finite(azimuth_deg, height_deg)
    azimuth_rad = float(np.deg2rad(azimuth_deg))

    # La cinemática directa fija primero la normal a partir de ambos motores.
    normal_array = _unit_vector_array(
        _direction_array_from_azimuth_height(azimuth_deg, height_deg)
    )

    # Dirección equivalente a unit(k × n) dentro del intervalo operativo. Se
    # escribe explícitamente para conservar el acimut cuando n es vertical.
    horizontal_edge_array = _unit_vector_array(
        np.array(
            [-np.cos(azimuth_rad), np.sin(azimuth_rad), 0.0],
            dtype=np.float64,
        )
    )

    # El producto cruz de NumPy completa la base dextrógira del espejo.
    upper_direction_array = _unit_vector_array(
        np.cross(normal_array, horizontal_edge_array)
    )

    # Convertir a tuplas solamente al construir el resultado público inmutable.
    normal = _array_to_vector(normal_array)
    horizontal_edge = _array_to_vector(horizontal_edge_array)
    upper_direction = _array_to_vector(upper_direction_array)

    # Las columnas se ordenan como arista, dirección superior y normal.
    orientation = (horizontal_edge, upper_direction, normal)

    # Empaquetar la pose impide que una función consumidora pierda un eje local.
    pose = MirrorPose(
        azimuth_deg=wrap_degrees(azimuth_deg),
        height_deg=float(height_deg),
        normal=normal,
        horizontal_edge=horizontal_edge,
        upper_direction=upper_direction,
        orientation_columns=orientation,
    )
    # Una comprobación defensiva detecta cualquier regresión en la construcción.
    if not validate_mirror_basis(pose):
        raise ArithmeticError("La pose altazimutal no produjo una base ortonormal")
    return pose


# 3.3.1 Verificación de la base ortonormal y la arista horizontal

def validate_mirror_basis(pose: MirrorPose, *, tolerance: float = 1.0e-9) -> bool:
    """Comprueba ortonormalidad, orientación y arista horizontal.

    Todas las normas, productos punto y productos cruz se ejecutan directamente
    con NumPy dentro de esta función.
    """

    # La tolerancia debe ser estrictamente positiva para tener valor numérico.
    _require_finite(tolerance)
    if tolerance <= 0.0:
        raise ValueError("tolerance debe ser positiva")
    # Nombres cortos hacen visibles las identidades geométricas comprobadas.
    edge = _vector_array(pose.horizontal_edge)
    upper = _vector_array(pose.upper_direction)
    normal = _vector_array(pose.normal)

    # El producto cruz debería coincidir con la normal si la base es dextrógira.
    cross_unit = _unit_vector_array(np.cross(edge, upper))
    normal_unit = _unit_vector_array(normal)
    # Comparar los vectores directamente evita que ``arccos`` amplifique el
    # redondeo cuando el coseno es indistinguible de uno. El residuo conserva la
    # misma escala adimensional que las demás comprobaciones de ortonormalidad.
    orientation_residual = float(np.linalg.norm(cross_unit - normal_unit))
    # Cada entrada representa un residuo que debería ser matemáticamente cero.
    checks = (
        abs(float(np.linalg.norm(edge)) - 1.0),
        abs(float(np.linalg.norm(upper)) - 1.0),
        abs(float(np.linalg.norm(normal)) - 1.0),
        abs(float(np.dot(edge, upper))),
        abs(float(np.dot(edge, normal))),
        abs(float(np.dot(upper, normal))),
        abs(float(np.dot(edge, _vector_array(UP)))),
        orientation_residual,
    )
    # La base es válida solamente si el peor residuo satisface la tolerancia.
    return float(np.max(checks)) <= tolerance


# 3.4 Centros de las aristas inferior y superior
# -----------------------------------------------------------------------------

def mirror_edge_centers(
    center: Vector3,
    side_length_m: float,
    pose: MirrorPose,
) -> tuple[Vector3, Vector3]:
    """Devuelve los centros de las aristas inferior y superior del espejo.

    NumPy conserva los valores como arreglos durante toda la operación; esta
    función aporta la geometría específica del espejo.
    """

    # Convertir el centro garantiza tres componentes finitas.
    center_array = _vector_array(center)

    # Un lado nulo o negativo no representa un espejo físico.
    _require_finite(side_length_m)
    if side_length_m <= 0.0:
        raise ValueError("El lado del espejo debe ser positivo")
    # El desplazamiento desde el centro a cada arista es L/2 sobre el eje p.
    half_upper = _vector_array(pose.upper_direction) * (side_length_m / 2.0)

    # Restar apunta a la arista inferior y sumar a la superior.
    lower = center_array - half_upper
    upper = center_array + half_upper
    return _array_to_vector(lower), _array_to_vector(upper)


# =============================================================================
# 4. DIRECCIÓN OBJETIVO Y ÓPTICA DEL HELIOSTATO
# =============================================================================

# 4.1 Dirección del heliostato al receptor
# -----------------------------------------------------------------------------

def target_direction(heliostat_center: Vector3, receiver_center: Vector3) -> Vector3:
    """Dirección unitaria desde el heliostato hacia el centro del receptor.

    La resta y la norma se calculan directamente con NumPy.
    """

    # El orden receptor menos heliostato determina el sentido de propagación.
    heliostat = _vector_array(heliostat_center)
    receiver = _vector_array(receiver_center)
    return _array_to_vector(_unit_vector_array(receiver - heliostat))


# 4.2 Normal ideal: bisectriz entre Sol y receptor
# -----------------------------------------------------------------------------

def ideal_heliostat_normal(sun_direction: Vector3, target_direction_vector: Vector3) -> Vector3:
    """Normal bisectriz que refleja la radiación solar hacia el objetivo.

    Para vectores unitarios ``s`` y ``t``, la normal ideal es
    ``unit(s + t)``. La función rechaza el caso degenerado de direcciones
    opuestas porque su suma es nula.
    """

    # El vector solar debe apuntar desde el espejo hacia el Sol.
    sun = _unit_vector_array(sun_direction)

    # El vector objetivo debe apuntar desde el espejo hacia el receptor.
    target = _unit_vector_array(target_direction_vector)

    # NumPy suma ambos unitarios y la normalización produce su bisectriz.
    return _array_to_vector(_unit_vector_array(sun + target))


# 4.3 Ley vectorial de reflexión
# -----------------------------------------------------------------------------

def reflected_direction(incident_direction: Vector3, normal: Vector3) -> Vector3:
    """Aplica la ley vectorial de reflexión.

    ``incident_direction`` debe apuntar hacia la superficie reflectante.
    """

    # Normalizar el rayo elimina cualquier escala que no afecte su dirección.
    incident = _unit_vector_array(incident_direction)

    # La ley utilizada supone una normal de magnitud uno.
    normal_array = _unit_vector_array(normal)

    # Ley de reflexión: r = i - 2(i·n)n. Punto, escala y resta usan NumPy.
    reflected = incident - 2.0 * np.dot(incident, normal_array) * normal_array
    # Normalizar de nuevo controla el error acumulado de punto flotante.
    return _array_to_vector(_unit_vector_array(reflected))


# =============================================================================
# 5. PLANO RECEPTOR E IMPACTO
# =============================================================================

# 5.1 Marco local del receptor
# -----------------------------------------------------------------------------

def receiver_frame(
    receiver_center: Vector3,
    *,
    heliostat_center: Vector3 = (0.0, 0.0, 0.0),
    plane_normal: Vector3 | None = None,
) -> ReceiverFrame:
    """Construye una base ortonormal para el plano receptor.

    Si no se proporciona normal, el plano queda perpendicular a la línea entre
    heliostato y receptor. ``u`` apunta al oeste y ``v`` hacia arriba.
    """

    # Validar y congelar semánticamente los dos puntos geométricos.
    center = _vector_array(receiver_center)
    origin = _vector_array(heliostat_center)

    # Elegir la normal geométrica predeterminada o normalizar la indicada.
    normal = (
        _unit_vector_array(center - origin)
        if plane_normal is None
        else _unit_vector_array(plane_normal)
    )
    # ``normal × vertical`` genera un eje contenido en el plano y horizontal.
    up = _vector_array(UP)
    u_raw = np.cross(normal, up)
    if float(np.linalg.norm(u_raw)) < EPSILON:
        # Si el receptor está sobre la vertical, proyectar el oeste global.
        # Proyección: oeste - normal(oeste·normal).
        west = _vector_array(WEST)
        u_raw = west - normal * np.dot(west, normal)

    # Normalizar convierte la dirección horizontal en el eje local u.
    u_axis = _unit_vector_array(u_raw)

    # ``u × normal`` completa una base ortonormal dentro del plano.
    v_axis = _unit_vector_array(np.cross(u_axis, normal))

    # Corregir conjuntamente los signos si v quedó orientado hacia el suelo.
    if float(np.dot(v_axis, up)) < 0.0:
        u_axis = -u_axis
        v_axis = -v_axis

    # Convertir a tuplas únicamente al cruzar la frontera del resultado público.
    return ReceiverFrame(
        center=_array_to_vector(center),
        normal=_array_to_vector(normal),
        u_axis=_array_to_vector(u_axis),
        v_axis=_array_to_vector(v_axis),
    )


# 5.2 Intersección de un rayo con un plano
# -----------------------------------------------------------------------------

def ray_plane_intersection(
    ray_origin: Vector3,
    ray_direction: Vector3,
    plane_point: Vector3,
    plane_normal: Vector3,
    *,
    forward_only: bool = True,
    epsilon: float = EPSILON,
) -> RayPlaneIntersection:
    """Intersecta un rayo con un plano y explica los casos inválidos.

    Usa la forma paramétrica ``P(t) = origen + t*dirección``. Los productos
    punto y operaciones vectoriales se delegan a NumPy.
    """

    # El origen es un punto: solo necesita validación tridimensional.
    origin = _vector_array(ray_origin)

    # La dirección sí debe ser unitaria para interpretar t en metros.
    direction = _unit_vector_array(ray_direction)

    # Un punto y una normal definen el plano receptor.
    point_on_plane = _vector_array(plane_point)
    normal = _unit_vector_array(plane_normal)

    # La tolerancia determina cuándo un denominador se considera cero.
    _require_finite(epsilon)
    if epsilon <= 0.0:
        raise ValueError("epsilon debe ser positivo")
    # El denominador d·n mide cuánto atraviesa el rayo al plano.
    denominator = float(np.dot(direction, normal))
    if abs(denominator) < epsilon:
        # Un valor casi cero significa rayo paralelo, sin intersección única.
        return RayPlaneIntersection(False, None, None, "rayo_paralelo_al_plano")

    # t = ((p_plano - origen)·normal)/(dirección·normal).
    parameter = float(np.dot(point_on_plane - origin, normal) / denominator)
    if forward_only and parameter <= epsilon:
        # t negativo coloca la intersección en sentido opuesto a la propagación.
        return RayPlaneIntersection(False, None, parameter, "interseccion_detras_del_origen")

    # Evaluar la ecuación paramétrica en el valor t encontrado.
    point = origin + direction * parameter
    return RayPlaneIntersection(
        True,
        _array_to_vector(point),
        parameter,
        "impacto_valido",
    )


# 5.3 Coordenadas locales y error radial del impacto
# -----------------------------------------------------------------------------

def receiver_impact(
    ray_origin: Vector3,
    ray_direction: Vector3,
    frame: ReceiverFrame,
) -> ReceiverImpact:
    """Calcula el impacto ``u``, ``v`` y el error radial del receptor."""

    # Reutilizar la intersección concentra en un solo sitio los casos inválidos.
    intersection = ray_plane_intersection(
        ray_origin,
        ray_direction,
        frame.center,
        frame.normal,
    )
    # Propagar un resultado inválido sin inventar coordenadas de impacto.
    if not intersection.valid or intersection.point is None:
        return ReceiverImpact(
            valid=False,
            point=None,
            u_m=None,
            v_m=None,
            radial_error_m=None,
            ray_parameter_m=intersection.ray_parameter_m,
            reason=intersection.reason,
        )
    # Expresar el impacto respecto del centro antes de proyectarlo.
    relative = _vector_array(intersection.point) - _vector_array(frame.center)

    # Los productos punto calculados por NumPy entregan coordenadas locales.
    u_m = float(np.dot(relative, _vector_array(frame.u_axis)))
    v_m = float(np.dot(relative, _vector_array(frame.v_axis)))
    return ReceiverImpact(
        valid=True,
        point=intersection.point,
        u_m=u_m,
        v_m=v_m,
        # ``np.hypot`` calcula sqrt(u² + v²) de forma numéricamente estable.
        radial_error_m=float(np.hypot(u_m, v_m)),
        ray_parameter_m=intersection.ray_parameter_m,
        reason="impacto_valido",
    )


# =============================================================================
# 6. OFFSETS, LÍMITES MECÁNICOS Y DISPONIBILIDAD SOLAR
# =============================================================================

# 6.1 Offsets de referencia o encoder
# -----------------------------------------------------------------------------

def apply_encoder_offsets(
    commands: AxisCommands,
    *,
    azimuth_offset_deg: float = 0.0,
    height_offset_deg: float = 0.0,
) -> AxisCommands:
    """Aplica offsets explícitos de referencia o encoder a los comandos.

    Esta operación no impone límites: separar ambas responsabilidades permite
    diagnosticar cuánto solicitó el modelo y cuánto aceptó la mecánica.
    """

    # Validar los offsets antes de sumarlos a órdenes que ya pueden ser válidas.
    _require_finite(azimuth_offset_deg, height_offset_deg)

    # Cada motor recibe solamente el offset correspondiente a su propio eje.
    return AxisCommands(
        azimuth_deg=commands.azimuth_deg + azimuth_offset_deg,
        height_deg=commands.height_deg + height_offset_deg,
    )


# 6.2 Saturación y etiquetas de límites físicos
# -----------------------------------------------------------------------------

def apply_mechanical_limits(
    commands: AxisCommands,
    limits: MechanicalLimits = MechanicalLimits(),
    *,
    tolerance_deg: float = 1.0e-9,
) -> LimitedCommands:
    """Satura independientemente cada eje y produce etiquetas operativas.

    ``clamp`` usa ``numpy.clip``; esta función añade el significado físico de
    cada borde y conserva simultáneamente la orden solicitada.
    """

    # Validar tanto la orden como la tolerancia usada para detectar los bordes.
    _require_finite(commands.azimuth_deg, commands.height_deg, tolerance_deg)
    if tolerance_deg < 0.0:
        raise ValueError("tolerance_deg no puede ser negativa")
    # Saturar el motor de acimut sin modificar el comando de altura.
    azimuth = clamp(
        commands.azimuth_deg,
        limits.azimuth_min_deg,
        limits.azimuth_max_deg,
    )
    # Saturar el motor de altura de manera independiente.
    height = clamp(
        commands.height_deg,
        limits.height_min_deg,
        limits.height_max_deg,
    )
    # Acumular todas las fronteras alcanzadas; pueden coincidir dos a la vez.
    labels: list[str] = []
    if azimuth <= limits.azimuth_min_deg + tolerance_deg:
        labels.append("limite_acimut_este")
    if azimuth >= limits.azimuth_max_deg - tolerance_deg:
        labels.append("limite_acimut_oeste")
    if height <= limits.height_min_deg + tolerance_deg:
        labels.append("limite_altura_minimo")
    if height >= limits.height_max_deg - tolerance_deg:
        labels.append("limite_altura_home")
    # Conservar la orden original permite calcular y mostrar la saturación.
    return LimitedCommands(
        requested=commands,
        applied=AxisCommands(azimuth_deg=azimuth, height_deg=height),
        limit_labels=tuple(labels),
    )


# 6.3 Posición Home y condición mínima de operación
# -----------------------------------------------------------------------------

def home_commands() -> AxisCommands:
    """Devuelve la referencia Home confirmada: sur y espejo horizontal."""

    # En la convención del proyecto, 90° de altura coloca la normal en el cenit.
    return AxisCommands(azimuth_deg=0.0, height_deg=90.0)


def sun_is_operational(solar_altitude_deg: float, *, minimum_deg: float = 0.0) -> bool:
    """Indica si el Sol supera estrictamente la altura operativa configurada.

    La comparación es estricta: estar exactamente en el umbral todavía se
    considera fuera de operación.
    """

    # Validar evita que NaN produzca silenciosamente ``False``.
    _require_finite(solar_altitude_deg, minimum_deg)
    return solar_altitude_deg > minimum_deg


# =============================================================================
# AUXILIARES COMPARTIDOS POR LOS MÉTODOS SOLARES DE LAS SECCIONES 7 Y 8
# =============================================================================

def _validate_solar_inputs(
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
) -> None:
    """Valida los dominios geográficos y temporales comunes a cada método."""

    # Latitud, longitud y offset deben ser números reales finitos.
    _require_finite(latitude_deg, longitude_deg, utc_offset_hours)

    # Los polos están incluidos en el dominio geográfico de la latitud.
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("La latitud debe estar entre -90° y 90°")
    # Se acepta cualquiera de las dos representaciones del antimeridiano.
    if not -180.0 <= longitude_deg <= 180.0:
        raise ValueError("La longitud debe estar entre -180° y 180°")
    # Este intervalo contiene los offsets civiles actualmente utilizados.
    if not -14.0 <= utc_offset_hours <= 14.0:
        raise ValueError("El offset UTC debe estar entre -14 h y 14 h")


def _localized_time_index(
    when: dt.datetime,
    utc_offset_hours: float,
) -> "pd.DatetimeIndex":
    """Crea el índice temporal localizado que requiere ``pvlib``.

    Una fecha ingenua se interpreta como hora civil del offset entregado. Una
    fecha con zona se convierte al mismo offset para conservar el instante.
    """

    # La importación diferida evita cargar pandas al usar solo geometría u óptica.
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("El cálculo solar requiere la dependencia pandas") from error

    # ``datetime.timezone`` representa un offset fijo, sin reglas de horario estacional.
    timezone = dt.timezone(dt.timedelta(hours=utc_offset_hours))
    if when.tzinfo is not None:
        # Una fecha consciente conserva el instante y cambia su representación local.
        local_when = when.astimezone(timezone)
    else:
        # Una fecha ingenua recibe explícitamente el offset indicado por el usuario.
        local_when = when.replace(tzinfo=timezone)

    # pvlib trabaja de forma vectorizada; incluso un instante usa DatetimeIndex.
    return pd.DatetimeIndex([local_when])


def _pvlib_solarposition() -> Any:
    """Devuelve el módulo solar de pvlib o un error de dependencia explícito."""

    # Importación diferida: el álgebra vectorial no necesita iniciar pvlib.
    try:
        from pvlib import solarposition
    except ImportError as error:
        raise RuntimeError("El cálculo solar requiere la dependencia pvlib") from error
    return solarposition


def _solar_position_from_pvlib_row(
    row: "pd.Series",
    method: str,
) -> SolarPosition:
    """Convierte una fila de pvlib a las unidades y ejes del proyecto.

    pvlib mide el acimut desde el norte en sentido horario. El Minihorno usa
    cero al sur, valores positivos al oeste y negativos al este.
    """

    # SPA ofrece elevación aparente: incluye la corrección de refracción solicitada.
    altitude_deg = float(row["apparent_elevation"])

    # No todos los calculadores garantizan esta columna, por eso es opcional.
    equation_of_time = (
        float(row["equation_of_time"])
        if "equation_of_time" in row.index
        else None
    )
    # Restar 180° cambia el origen norte a sur; ``wrap`` asigna el signo este/oeste.
    return SolarPosition(
        zenith_deg=float(row["apparent_zenith"]),
        altitude_deg=altitude_deg,
        azimuth_deg=wrap_degrees(float(row["azimuth"]) - 180.0),
        method=method,
        equation_of_time_min=equation_of_time,
    )


# =============================================================================
# 7. POSICIÓN SOLAR DUFFIE-BECKMAN MEDIANTE PVLIB
# =============================================================================

def solar_position_duffie_beckman(
    when: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
) -> SolarPosition:
    """Calcula la posición geométrica con las rutinas Duffie-Beckman de pvlib.

    Usa ``declination_cooper69``, ``equation_of_time_spencer71``,
    ``hour_angle``, ``solar_zenith_analytical`` y
    ``solar_azimuth_analytical``. Al ser un modelo analítico no incluye
    refracción atmosférica; por eso no debe confundirse con NREL SPA.
    """

    # Compartir validación garantiza los mismos dominios para los tres métodos.
    _validate_solar_inputs(latitude_deg, longitude_deg, utc_offset_hours)

    # Localizar la hora es indispensable para que pvlib calcule el ángulo horario.
    times = _localized_time_index(when, utc_offset_hours)

    # Obtener el módulo sin reimplementar ninguna de sus ecuaciones solares.
    solarposition = _pvlib_solarposition()

    # pvlib deriva el número ordinal del año a partir del instante localizado.
    day_of_year = times.dayofyear

    # Declinación de Cooper (1969), en radianes, implementada por pvlib.
    declination_rad = solarposition.declination_cooper69(day_of_year)

    # Ecuación del tiempo de Spencer (1971), devuelta en minutos.
    equation_of_time_min = solarposition.equation_of_time_spencer71(day_of_year)

    # El ángulo horario incorpora hora civil, offset, longitud y ecuación del tiempo.
    hour_angle_deg = solarposition.hour_angle(
        times,
        longitude_deg,
        equation_of_time_min,
    )
    # La rutina analítica de cenit exige latitud y ángulo horario en radianes.
    zenith_rad = solarposition.solar_zenith_analytical(
        np.deg2rad(latitude_deg),
        np.deg2rad(hour_angle_deg),
        declination_rad,
    )

    # pvlib obtiene el cuadrante correcto del acimut mediante su función analítica.
    azimuth_rad = solarposition.solar_azimuth_analytical(
        np.deg2rad(latitude_deg),
        np.deg2rad(hour_angle_deg),
        declination_rad,
        zenith_rad,
    )

    # Extraer el único instante y convertir el cenit de radianes a grados.
    zenith_deg = float(np.rad2deg(zenith_rad[0]))

    # Duffie-Beckman es geométrico: altitud y cenit son complementarios.
    return SolarPosition(
        zenith_deg=zenith_deg,
        altitude_deg=90.0 - zenith_deg,
        azimuth_deg=wrap_degrees(float(np.rad2deg(azimuth_rad[0])) - 180.0),
        method="duffie_beckman_pvlib",
        equation_of_time_min=float(equation_of_time_min[0]),
    )


# =============================================================================
# 8. REDA-ANDREAS Y NREL SPA MEDIANTE PVLIB
# =============================================================================

# 8.1 Entrada directa a ``spa_python``
# -----------------------------------------------------------------------------

def solar_position_reda(
    when: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
    *,
    altitude_m: float = 0.0,
    pressure_pa: float = 101325.0,
    temperature_c: float = 12.0,
    delta_t_s: float | None = None,
) -> SolarPosition:
    """Calcula la posición mediante Reda-Andreas (NREL SPA) en pvlib.

    ``spa_python`` es la implementación NumPy publicada por pvlib del algoritmo
    NREL. No existe una fórmula solar alternativa ni una perturbación propia.
    """

    # Validar coordenadas y zona antes de preparar la llamada científica.
    _validate_solar_inputs(latitude_deg, longitude_deg, utc_offset_hours)

    # Elevación, presión y temperatura determinan las correcciones topocéntricas.
    _require_finite(altitude_m, pressure_pa, temperature_c)

    # La presión cero permite desactivar refracción; una presión negativa no existe.
    if pressure_pa < 0.0:
        raise ValueError("La presión no puede ser negativa")
    # ``None`` ordena a pvlib estimar ΔT; un valor explícito se valida y conserva.
    if delta_t_s is not None:
        _require_finite(delta_t_s)
    # SPA requiere una secuencia de instantes consciente de zona horaria.
    times = _localized_time_index(when, utc_offset_hours)

    # Delegar el algoritmo completo a pvlib usando su backend NumPy.
    result = _pvlib_solarposition().spa_python(
        times,
        latitude_deg,
        longitude_deg,
        altitude=altitude_m,
        pressure=pressure_pa,
        temperature=temperature_c,
        delta_t=delta_t_s,
        how="numpy",
    )
    # Convertir la primera y única fila a la convención del Minihorno.
    return _solar_position_from_pvlib_row(result.iloc[0], "reda_andreas_spa_python")


# 8.2 Entrada de alto nivel a ``get_solarposition(method="nrel_numpy")``
# -----------------------------------------------------------------------------

def solar_position_spa(
    when: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
    *,
    altitude_m: float = 0.0,
    pressure_pa: float = 101325.0,
    temperature_c: float = 12.0,
    delta_t_s: float | None = None,
) -> SolarPosition:
    """Calcula NREL SPA con el selector público de alto nivel de pvlib.

    ``method="nrel_numpy"`` conduce al mismo fundamento Reda-Andreas que
    ``spa_python``. Esta función existe para verificar y conservar la entrada
    SPA/PVLIB que ya conoce la aplicación, no como un algoritmo independiente.
    """

    # Repetir validación en la función pública impide depender del selector externo.
    _validate_solar_inputs(latitude_deg, longitude_deg, utc_offset_hours)
    _require_finite(altitude_m, pressure_pa, temperature_c)
    if pressure_pa < 0.0:
        raise ValueError("La presión no puede ser negativa")
    if delta_t_s is not None:
        _require_finite(delta_t_s)
    # Preparar un índice temporal localizado para el adaptador de alto nivel.
    times = _localized_time_index(when, utc_offset_hours)

    # ``get_solarposition`` selecciona expresamente NREL SPA con backend NumPy.
    result = _pvlib_solarposition().get_solarposition(
        times,
        latitude_deg,
        longitude_deg,
        altitude=altitude_m,
        pressure=pressure_pa,
        method="nrel_numpy",
        temperature=temperature_c,
        delta_t=delta_t_s,
    )
    # Normalizar unidades y convención angular antes de exponer el resultado.
    return _solar_position_from_pvlib_row(result.iloc[0], "spa_pvlib_nrel_numpy")


# 8.3 Selector explícito del método solar
# -----------------------------------------------------------------------------

def solar_position(
    when: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
    *,
    method: str = "reda",
    altitude_m: float = 0.0,
    pressure_pa: float = 101325.0,
    temperature_c: float = 12.0,
    delta_t_s: float | None = None,
) -> SolarPosition:
    """Selecciona un método solar sin aplicar sustituciones silenciosas.

    El valor predeterminado es Reda-Andreas. Un método desconocido genera un
    error: nunca se degrada automáticamente a una aproximación distinta.
    """

    # Normalizar mayúsculas y separadores permite nombres de interfaz legibles.
    normalized_method = method.strip().lower().replace("-", "_").replace("/", "_")

    # Duffie-Beckman no utiliza presión, temperatura, elevación ni ΔT.
    if normalized_method in {"db", "d&b", "duffie_beckman"}:
        return solar_position_duffie_beckman(
            when,
            latitude_deg,
            longitude_deg,
            utc_offset_hours,
        )
    # Agrupar las entradas ambientales evita duplicar argumentos entre rutas SPA.
    common = {
        "altitude_m": altitude_m,
        "pressure_pa": pressure_pa,
        "temperature_c": temperature_c,
        "delta_t_s": delta_t_s,
    }
    # Ruta directa a ``spa_python`` identificada como REDA en la interfaz.
    if normalized_method in {"reda", "reda_andreas"}:
        return solar_position_reda(
            when,
            latitude_deg,
            longitude_deg,
            utc_offset_hours,
            **common,
        )
    # Ruta de alto nivel de pvlib, matemáticamente equivalente a la anterior.
    if normalized_method in {"spa", "spa_pvlib", "spa_pvlib_nrel_numpy"}:
        return solar_position_spa(
            when,
            latitude_deg,
            longitude_deg,
            utc_offset_hours,
            **common,
        )
    # Fallar explícitamente protege la trazabilidad científica del cálculo.
    raise ValueError(f"Método solar no reconocido: {method!r}")


# =============================================================================
# 9. VECTOR SOLAR EN EL SISTEMA DE COORDENADAS DEL PROYECTO
# =============================================================================

def solar_vector(
    when: dt.datetime,
    latitude_deg: float,
    longitude_deg: float,
    utc_offset_hours: float,
    *,
    method: str = "reda",
    altitude_m: float = 0.0,
    pressure_pa: float = 101325.0,
    temperature_c: float = 12.0,
    delta_t_s: float | None = None,
) -> tuple[SolarPosition, Vector3]:
    """Devuelve conjuntamente la posición y el vector solar unitario.

    El vector apunta desde el heliostato hacia el Sol en los ejes globales del
    proyecto. La posición adjunta registra el método que produjo sus ángulos.
    """

    # Obtener primero los ángulos mediante el método explícitamente seleccionado.
    position = solar_position(
        when,
        latitude_deg,
        longitude_deg,
        utc_offset_hours,
        method=method,
        altitude_m=altitude_m,
        pressure_pa=pressure_pa,
        temperature_c=temperature_c,
        delta_t_s=delta_t_s,
    )
    # Transformar acimut y elevación a componentes cartesianas del proyecto.
    vector = _direction_array_from_azimuth_height(
        position.azimuth_deg,
        position.altitude_deg,
    )

    # Normalizar defensivamente antes de entregar la dirección óptica.
    return position, _array_to_vector(_unit_vector_array(vector))


# =============================================================================
# 10. CADENA MATEMÁTICA COMPLETA
# =============================================================================
# Este archivo no crea una función monolítica. ``physics_pipeline.py`` compone
# las secciones 7/8 -> 9 -> 4 -> 3 -> 4.3 -> 5 y conserva cada resultado
# intermedio. Así, el núcleo sigue siendo matemático y el flujo completo puede
# probarse sin depender de Shiny, JavaScript o la escena tridimensional.

# =============================================================================
# 11. API PÚBLICA Y CORRESPONDENCIA ENTRE CÓDIGO Y ECUACIONES
# =============================================================================

# ``__all__`` define la API soportada cuando otro módulo usa
# ``from physics_core import *``. Los adaptadores internos con prefijo ``_`` no
# se exportan para que puedan evolucionar sin romper la aplicación.
__all__ = [
    "AxisCommands",
    "LimitedCommands",
    "Matrix3Columns",
    "MechanicalLimits",
    "MirrorPose",
    "RayPlaneIntersection",
    "ReceiverFrame",
    "ReceiverImpact",
    "SolarPosition",
    "Vector3",
    "angle_between",
    "apply_encoder_offsets",
    "apply_mechanical_limits",
    "azimuth_height_from_direction",
    "clamp",
    "direction_from_azimuth_height",
    "home_commands",
    "ideal_heliostat_normal",
    "mirror_edge_centers",
    "mirror_pose_from_altaz",
    "ray_plane_intersection",
    "receiver_frame",
    "receiver_impact",
    "reflected_direction",
    "rotate_about_axis",
    "solar_position",
    "solar_position_duffie_beckman",
    "solar_position_reda",
    "solar_position_spa",
    "solar_vector",
    "sun_is_operational",
    "target_direction",
    "validate_mirror_basis",
    "wrap_degrees",
]
