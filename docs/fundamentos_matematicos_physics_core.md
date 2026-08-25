# Fundamentos matemáticos de `physics_core.py`

> Nota de formato: este visor de Markdown no procesa LaTeX. Por eso las
> ecuaciones se escriben con símbolos matemáticos Unicode dentro de bloques de
> texto. Así son legibles aquí y no dependen de extensiones como KaTeX o
> MathJax.

La numeración de las secciones 1 a 11 se repite como encabezados comentados en
`web_app/physics_core.py`, para localizar rápidamente la implementación de cada
fundamento.

## 1. Convenciones

- `+x`: oeste.
- `+y`: sur.
- `+z`: cenit.
- Acimut `A = 0°`: sur.
- Acimut positivo: hacia el oeste.
- Altura `h = 90°`: normal vertical y espejo horizontal (Home).
- Altura `h = 10°`: espejo casi vertical.
- Ángulos de la API pública: grados.
- Distancias: metros.

### Bibliotecas responsables del cálculo

| Operación | Biblioteca utilizada en `physics_core.py` |
|---|---|
| Suma y resta de vectores | `numpy.add`, `numpy.subtract` |
| Multiplicación por un escalar | `numpy.multiply` |
| Producto punto | `numpy.dot` |
| Producto cruz | `numpy.cross` |
| Norma euclidiana | `numpy.linalg.norm` |
| Funciones trigonométricas y conversiones angulares | NumPy |
| Rotaciones tridimensionales | `scipy.spatial.transform.Rotation` |
| Posición solar | `pvlib.solarposition` |

El núcleo no mantiene funciones públicas que dupliquen estas operaciones.
Valida cada vector al entrar a una función física, opera internamente con
arreglos NumPy y convierte a tupla únicamente al construir un resultado público
inmutable.

## 2. Operaciones escalares y vectoriales

Sean dos vectores tridimensionales:

```text
a = (a_x, a_y, a_z)
b = (b_x, b_y, b_z)
```

### 2.1 Recorte y envoltura angular

```text
clamp(x, l, u) = max(l, min(u, x))
```

La envoltura angular empleada por `wrap_degrees` es:

```text
wrap₁₈₀(A) = ((A + 180°) mod 360°) − 180°
```

El resultado pertenece al intervalo `[-180°, 180°)`.

### 2.2 Suma, resta y multiplicación por un escalar

```text
a + b = (a_x + b_x, a_y + b_y, a_z + b_z)

a − b = (a_x − b_x, a_y − b_y, a_z − b_z)

λa = (λa_x, λa_y, λa_z)
```

### 2.3 Producto punto, producto cruz y norma

```text
a · b = a_x b_x + a_y b_y + a_z b_z
```

```text
        ( a_y b_z − a_z b_y )
a × b = ( a_z b_x − a_x b_z )
        ( a_x b_y − a_y b_x )
```

```text
‖a‖ = √(a · a)
```

### 2.4 Vector unitario y ángulo entre vectores

Para `‖a‖ > ε`:

```text
â = a / ‖a‖
```

El ángulo menor entre dos vectores no nulos es:

```text
θ = acos(clamp(â · b̂, −1, 1))
```

El recorte evita que el redondeo numérico entregue a `acos` un valor
ligeramente fuera de `[-1, 1]`.

### 2.5 Rotación de Rodrigues

Para rotar `v` un ángulo `θ` alrededor del eje unitario `k̂`:

```text
v_rot = v cos(θ)
      + (k̂ × v) sin(θ)
      + k̂ (k̂ · v) [1 − cos(θ)]
```

Esta es la base de `rotate_about_axis`.

## 3. Cinemática altazimutal

### 3.1 Dirección definida por acimut y altura

La normal unitaria asociada al acimut `A` y a la altura `h` es:

```text
          ( cos(h) sin(A) )
n(A,h) = ( cos(h) cos(A) )
          (     sin(h)     )
```

Casos de comprobación:

```text
n(0°, 0°)   = (0, 1, 0)    sur
n(90°, 0°)  = (1, 0, 0)    oeste
n(A, 90°)   = (0, 0, 1)    cenit, espejo horizontal
```

Esta ecuación corresponde a `direction_from_azimuth_height`.

### 3.2 Conversión inversa

Para una dirección unitaria `n = (n_x, n_y, n_z)` no vertical:

```text
A = atan2(n_x, n_y)
h = asin(n_z)
```

Si:

```text
√(n_x² + n_y²) < ε
```

el acimut es indeterminado. `azimuth_height_from_direction` conserva entonces
el último acimut disponible para evitar un salto de orientación.

### 3.3 Base completa del espejo

La normal no determina por sí sola la orientación de un espejo cuadrado. La
dirección horizontal de sus aristas inferior y superior se define como:

```text
       ( −cos(A) )
e(A) = (  sin(A) )
       (    0     )
```

La dirección dentro del plano hacia la parte superior del espejo es:

```text
p = unit(n × e)
```

La matriz de orientación se forma con las columnas:

```text
R_espejo = [ e | p | n ]
```

La base debe satisfacer:

```text
‖e‖ = ‖p‖ = ‖n‖ = 1

e · p = 0
e · n = 0
p · n = 0

e × p = n
```

La condición de horizontalidad es:

```text
e · (0, 0, 1) = 0
```

Por construcción, la tercera componente de `e` siempre es cero. Esto demuestra
que las aristas inferior y superior permanecen paralelas al suelo para
cualquier combinación válida de ambos motores. No es una corrección visual.

### 3.4 Centros de las aristas

Para un espejo cuadrado de lado `L` y centro `c`:

```text
c_inferior = c − (L/2) p
c_superior = c + (L/2) p
```

## 4. Dirección objetivo y óptica del heliostato

### 4.1 Dirección al receptor

Sean `H` el centro óptico del heliostato y `C` el centro del receptor:

```text
t = (C − H) / ‖C − H‖
```

### 4.2 Normal ideal del espejo

Sea `s` el vector unitario que apunta del heliostato hacia el Sol y `t` el
vector unitario hacia el receptor:

```text
n_ideal = (s + t) / ‖s + t‖
```

Esta expresión supone que `s` y `t` no son exactamente opuestos.

### 4.3 Ley vectorial de reflexión

El rayo solar incidente apunta hacia el espejo:

```text
i = −s
```

Para una normal unitaria `n`, la dirección reflejada es:

```text
r = i − 2(i · n)n
```

El resultado se normaliza para controlar el error de redondeo. Si
`n = n_ideal`, idealmente se obtiene:

```text
r = t
```

## 5. Plano receptor e impacto

### 5.1 Marco local del receptor

La normal predeterminada del receptor es:

```text
n_R = (C − H) / ‖C − H‖
```

Con el vector vertical `k = (0, 0, 1)`, el eje local hacia el oeste es:

```text
u = (n_R × k) / ‖n_R × k‖
```

El eje local hacia arriba es:

```text
v = unit(u × n_R)
```

Si el signo inicial deja `v` hacia abajo, ambos ejes tangenciales se
multiplican por `−1`. Si `n_R` es vertical, se proyecta el oeste global sobre
el plano receptor para evitar la singularidad.

### 5.2 Intersección rayo-plano

El rayo se representa mediante:

```text
P(τ) = O + τd
```

donde `O` es el origen y `d` su dirección unitaria. El plano receptor cumple:

```text
(P − C) · n_R = 0
```

Sustituyendo el rayo:

```text
     (C − O) · n_R
τ = ───────────────
         d · n_R
```

No existe una intersección única cuando:

```text
|d · n_R| < ε
```

Si solo se acepta propagación hacia delante, también se rechaza `τ ≤ 0`.

### 5.3 Coordenadas y error sobre el receptor

Para el punto de impacto `P`:

```text
u_R = (P − C) · u
v_R = (P − C) · v

error_radial = √(u_R² + v_R²)
```

## 6. Offsets y límites mecánicos

Los offsets de referencia o encoder se aplican independientemente:

```text
A_ajustado = A_ordenado + ΔA
h_ajustado = h_ordenado + Δh
```

Los límites físicos se aplican mediante:

```text
A_aplicado = clamp(A_ajustado, −90°, 90°)
h_aplicado = clamp(h_ajustado,  10°, 90°)
```

Cada eje se limita por separado. Llegar a un límite produce una etiqueta de
estado, pero no modifica silenciosamente el otro eje.

La posición Home es:

```text
(A_home, h_home) = (0°, 90°)
```

La condición solar operativa parametrizada actualmente es:

```text
h_Sol > h_mínima
```

El valor definitivo de `h_mínima` continúa pendiente de validación física.

## 7. Posición solar Duffie-Beckman mediante `pvlib`

`solar_position_duffie_beckman` no reimplementa las ecuaciones. Llama a las
funciones analíticas correspondientes de `pvlib.solarposition`.

### 7.1 Ángulo del día

Para el número de día `n`:

```text
B = 2π(n − 1) / 365
```

### 7.2 Declinación de Cooper

La función `declination_cooper69`, atribuida por `pvlib` a Duffie-Beckman,
utiliza:

```text
δ = 23.45° sin[2π(n + 284) / 365]
```

### 7.3 Ecuación del tiempo de Spencer

La función `equation_of_time_spencer71` calcula, en minutos:

```text
E = (1440 / 2π) [ 0.0000075
                 + 0.001868 cos(B)
                 − 0.032077 sin(B)
                 − 0.014615 cos(2B)
                 − 0.040849 sin(2B) ]
```

### 7.4 Hora solar y ángulo horario

Con longitud geográfica `λ_geo` positiva al este y offset UTC `z` en horas:

```text
L_STM = 15° z

                     4(λ_geo − L_STM) + E
t_solar = t_civil + ──────────────────────
                               60

ω = 15°(t_solar − 12)
```

`ω = 0°` al mediodía solar, negativo por la mañana y positivo por la tarde.

### 7.5 Cenit, elevación y acimut

Para latitud `φ`:

```text
θ_z = acos[cos(δ) cos(φ) cos(ω) + sin(δ) sin(φ)]

h_Sol = 90° − θ_z
```

El acimut de `pvlib`, medido desde el norte en sentido horario, es:

```text
                    cos(θ_z) sin(φ) − sin(δ)
γ = sign(ω) acos[ ─────────────────────────── ] + π
                         sin(θ_z) cos(φ)
```

El núcleo lo transforma a la convención del proyecto:

```text
A = wrap₁₈₀(γ_deg − 180°)
```

Este modelo es geométrico y no incluye refracción atmosférica. Es un método
Duffie-Beckman reproducible, pero no tiene la precisión astronómica de NREL
SPA.

## 8. Reda-Andreas y NREL SPA mediante `pvlib`

`solar_position_reda` llama a `pvlib.solarposition.spa_python`.
`solar_position_spa` llama a
`pvlib.solarposition.get_solarposition(method="nrel_numpy")`. Ambas rutas
ejecutan el algoritmo NREL SPA de Reda y Andreas; no son modelos astronómicos
independientes.

SPA contiene series periódicas extensas. El proyecto no copia sus tablas de
coeficientes: delega su evaluación a `pvlib`. A continuación se presenta la
cadena matemática ejecutada.

### 8.1 Escalas de tiempo

```text
ΔT = TT − UT1

JDE = JD + ΔT/86400

JC  = (JD  − 2451545) / 36525
JCE = (JDE − 2451545) / 36525
JME = JCE / 10
```

Si `delta_t_s=None`, `pvlib` estima `ΔT`. Para reproducibilidad metrológica se
debe proporcionar y registrar el valor adoptado.

### 8.2 Posición heliocéntrica de la Tierra

SPA obtiene la longitud `L`, latitud `B` y radio vector `R` mediante series
VSOP. Para cualquiera de esas variables `X`:

```text
X_i = Σ_j A_ij cos(B_ij + C_ij JME)

X = (1 / 10⁸) Σ_i X_i (JME)ⁱ

X ∈ {L, B, R}
```

Los coeficientes `A_ij`, `B_ij` y `C_ij` pertenecen a las tablas de SPA y son
evaluados por `pvlib`.

### 8.3 Coordenadas geocéntricas y nutación

```text
Θ = (L + 180°) mod 360°
β = −B
```

Las correcciones de nutación son:

```text
Δψ = (1 / 36000000)
     Σ_i (a_i + b_i JCE) sin[Σ_k Y_ik X_k]

Δε = (1 / 36000000)
     Σ_i (c_i + d_i JCE) cos[Σ_k Y_ik X_k]
```

`X₀ … X₄` son la elongación media, las anomalías medias del Sol y la Luna, el
argumento de latitud lunar y la longitud del nodo ascendente de la Luna.

La corrección por aberración es:

```text
Δτ = −20.4898 / (3600 R)
```

La longitud aparente del Sol es:

```text
λ = Θ + Δψ + Δτ
```

Para `U = JME/10`, la oblicuidad media, en segundos de arco, es:

```text
ε₀ = 84381.448
   − 4680.93 U
   − 1.55 U²
   + 1999.25 U³
   − 51.38 U⁴
   − 249.67 U⁵
   − 39.05 U⁶
   + 7.12 U⁷
   + 27.87 U⁸
   + 5.79 U⁹
   + 2.45 U¹⁰
```

La oblicuidad verdadera, en grados, es:

```text
ε = ε₀/3600 + Δε
```

### 8.4 Ascensión recta y declinación geocéntrica

```text
α = atan2[sin(λ) cos(ε) − tan(β) sin(ε), cos(λ)]
```

```text
δ = asin[sin(β) cos(ε) + cos(β) sin(ε) sin(λ)]
```

### 8.5 Tiempo sideral y ángulo horario

```text
ν₀ = 280.46061837
   + 360.98564736629(JD − 2451545)
   + 0.000387933 JC²
   − JC³/38710000

ν = ν₀ + Δψ cos(ε)

H = ν + λ_geo − α
```

### 8.6 Corrección topocéntrica

La paralaje ecuatorial horizontal es:

```text
ξ = 8.794 / (3600 R)
```

Para latitud `φ` y elevación del observador `E_obs`:

```text
u = atan[0.99664719 tan(φ)]

x = cos(u) + (E_obs/6378140) cos(φ)

y = 0.99664719 sin(u) + (E_obs/6378140) sin(φ)
```

La corrección de ascensión recta es:

```text
                  −x sin(ξ) sin(H)
Δα = atan2[ ────────────────────────── ]
             cos(δ) − x sin(ξ) cos(H)
```

Entonces:

```text
H′ = H − Δα
```

```text
             [sin(δ) − y sin(ξ)] cos(Δα)
δ′ = atan2[ ────────────────────────────── ]
              cos(δ) − x sin(ξ) cos(H)
```

### 8.7 Elevación, refracción y cenit aparente

La elevación topocéntrica sin refracción es:

```text
e₀ = asin[sin(φ) sin(δ′) + cos(φ) cos(δ′) cos(H′)]
```

Con presión `P` en mbar y temperatura `T` en grados Celsius:

```text
        P      283             1.02
Δe = ────── × ───── × ─────────────────────────
     1010     273+T   60 tan[e₀ + 10.3/(e₀+5.11)]
```

La API recibe `pressure_pa` en pascales y `pvlib` realiza:

```text
P = pressure_pa / 100
```

Los ángulos de la fórmula de refracción están en grados; la implementación
convierte el argumento de la tangente a radianes. La corrección solo se aplica
dentro del dominio angular permitido por SPA.

```text
e   = e₀ + Δe
θ_z = 90° − e
```

### 8.8 Acimut topocéntrico

El acimut astronómico intermedio es:

```text
                   sin(H′)
Γ = atan2[ ─────────────────────────────── ]
             cos(H′) sin(φ) − tan(δ′) cos(φ)
```

SPA lo expresa desde el norte en sentido horario:

```text
γ = (Γ + 180°) mod 360°
```

El núcleo lo transforma a la convención del proyecto:

```text
A = wrap₁₈₀(γ − 180°)
```

### 8.9 Ecuación del tiempo de SPA

La longitud media del Sol es:

```text
M = 280.4664567
  + 360007.6982779 JME
  + 0.03032028 JME²
  + JME³/49931
  − JME⁴/15300
  − JME⁵/2000000
```

La ecuación del tiempo antes de envolver el resultado es:

```text
E_deg = M − 0.0057183 − α + Δψ cos(ε)

E_min = 4 E_deg
```

El resultado se corrige modularmente en 1440 minutos para llevarlo al
intervalo físico cercano a `[-20 min, 20 min]`.

NREL declara para SPA una incertidumbre angular de aproximadamente `±0.0003°`
dentro de su intervalo temporal especificado. Esto no elimina los errores de
reloj, coordenadas, presión, temperatura, `ΔT` o alineación mecánica.

## 9. Vector solar en el sistema del proyecto

Con acimut solar `A_s` y elevación `h_s`:

```text
    ( cos(h_s) sin(A_s) )
s = ( cos(h_s) cos(A_s) )
    (       sin(h_s)     )
```

`solar_vector` normaliza nuevamente el resultado y entrega conjuntamente la
posición angular y el vector `s`.

## 10. Cadena matemática completa

```text
(t, φ, λ, z, P, T, E_obs, ΔT)
                  │
                  ▼
             (A_s, h_s)
                  │
                  ▼
                  s
```

```text
(H, C) ──► t

(s, t) ──► n_ideal ──► (A_ideal, h_ideal)

(A_ideal, h_ideal)
    ──► offsets
    ──► límites
    ──► (A_real, h_real)
    ──► (e, p, n_real)

(−s, n_real)
    ──► rayo reflejado r
    ──► impacto P
    ──► (u_R, v_R, error_radial)
```

## 11. Correspondencia entre código y ecuaciones

| Función | Fundamento matemático |
|---|---|
| `clamp` | Recorte al intervalo cerrado. |
| `wrap_degrees` | Envoltura modular a `[-180°, 180°)`. |
| Operadores `+`, `−`, `*` sobre arreglos | Suma, resta y escala directamente con NumPy. |
| `np.dot`, `np.cross`, `np.linalg.norm` | Producto punto, producto cruz y norma euclidiana. |
| `_unit_vector_array`, `angle_between` | Normalización interna y ángulo geométrico público. |
| `rotate_about_axis` | Fórmula de Rodrigues. |
| `direction_from_azimuth_height` | Conversión altazimutal directa. |
| `azimuth_height_from_direction` | Conversión altazimutal inversa. |
| `mirror_pose_from_altaz` | Base ortonormal completa de la montura. |
| `validate_mirror_basis` | Identidades de ortonormalidad y horizontalidad. |
| `mirror_edge_centers` | Traslación `±(L/2)p`. |
| `target_direction` | Vector relativo normalizado al receptor. |
| `ideal_heliostat_normal` | Bisectriz entre Sol y receptor. |
| `reflected_direction` | Ley vectorial de reflexión. |
| `receiver_frame` | Base local ortonormal del plano receptor. |
| `ray_plane_intersection` | Intersección paramétrica rayo-plano. |
| `receiver_impact` | Proyecciones locales y error radial. |
| `apply_encoder_offsets` | Suma independiente de offsets angulares. |
| `apply_mechanical_limits` | Saturación independiente de ambos ejes. |
| `home_commands` | Condición `A = 0°`, `h = 90°`. |
| `sun_is_operational` | Desigualdad `h_Sol > h_mínima`. |
| `solar_position_duffie_beckman` | Cooper, Spencer y trigonometría esférica de `pvlib`. |
| `solar_position_reda` | Implementación `spa_python` de NREL SPA. |
| `solar_position_spa` | Entrada `nrel_numpy` al mismo NREL SPA. |
| `solar_position` | Selección explícita del método solicitado. |
| `solar_vector` | Conversión de posición solar a vector unitario. |

## 12. Comprobaciones numéricas actuales

Las pruebas automatizadas comprueban:

1. Identidades vectoriales y rechazo de vectores nulos, no tridimensionales o no finitos.
2. Rotación de Rodrigues con casos conocidos.
3. Conversión directa e inversa altazimutal.
4. Ortonormalidad de la pose en todo el intervalo operativo.
5. Componente vertical nula de la arista horizontal.
6. Reflexión exacta hacia un receptor ideal.
7. Intersecciones válidas, paralelas y detrás del origen.
8. Saturación y etiquetado de límites.
9. Caso publicado por NREL SPA del 17 de octubre de 2003:

```text
θ_z        = 50.11162°
γ_NREL     = 194.34024°
A_proyecto = +14.34024°
```

10. Igualdad numérica entre las rutas REDA y SPA/PVLIB.
11. Error explícito cuando se solicita un método solar desconocido.

## 13. Fuentes

- I. Reda y A. Andreas, [Solar Position Algorithm for Solar Radiation Applications](https://docs.nrel.gov/docs/fy08osti/34302.pdf), NREL/TP-560-34302.
- NREL, [Solar Position Algorithm](https://midcdmz.nrel.gov/spa/).
- pvlib, [`spa_python`](https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.solarposition.spa_python.html).
- pvlib, [`declination_cooper69`](https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.solarposition.declination_cooper69.html).
- pvlib, [`equation_of_time_spencer71`](https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.solarposition.equation_of_time_spencer71.html).
- J. A. Duffie y W. A. Beckman, *Solar Engineering of Thermal Processes*, tercera edición, capítulos de geometría solar.
