# Matriz de trazabilidad de la integración física V2

## 1. Propósito

Este documento permite localizar cada dato visible de la aplicación dentro del
adaptador, el pipeline y el núcleo matemático. La versión 0.5.0 conserva el
contrato de interfaz heredado de 0.4.0; los cálculos físicos provienen de V2.

## 2. Trazabilidad funcional

| Requisito o dato | Entrada histórica | Adaptación V2 | Función matemática | Consumidor | Comprobación |
|---|---|---|---|---|---|
| Fecha, ubicación y método solar | `WebTwinState.active_datetime()`, latitud, longitud, UTC y selector D&B/REDA | `WebPhysicsRequest` y `solar_method_for_core()` | `solar_position()` y `solar_vector()` | reloj, trayectoria, diagnóstico y seguimiento | equivalencia directa con `physics_core`; REDA, SPA y D&B en Pyodide |
| Vector solar | estado del instante | `ideal_step.sun_direction` | `solar_vector()` | escena 3D, reflexión y CSV por componentes | vector unitario y convención +x oeste, +y sur, +z cenit |
| Dirección al receptor | RX, RY y RZ relativos al pivote | conversión temporal a posiciones globales | `target_direction()` y `receiver_frame()` | óptica, escena y facetas | receptor relativo `(0, 5.55, -0.40) m` preservado |
| Normal ideal | Sol y receptor | `PhysicalStepResult.ideal_normal` | `ideal_heliostat_normal()` | objetivos de ambos motores | cierre ideal en el centro del receptor |
| Objetivo de acimut | normal ideal, offset de cámara y límites | `control_targets.applied.azimuth_deg` | `azimuth_height_from_direction()` y `apply_mechanical_limits()` | `az_target_deg` | oeste positivo, rango `[-90°, 90°]` |
| Objetivo de altura | normal ideal, peralte, offset de cámara y límites | `control_targets.applied.height_deg` | `azimuth_height_from_direction()` y `apply_mechanical_limits()` | `el_target_deg` | Home `90°`, mínimo `10°` |
| Movimiento independiente | estados, PWM, velocidad y encendido de cada motor | cada objetivo se conserva como eje separado | interpolación temporal del estado; pose posterior en V2 | animación, encoders y diagnóstico | apagar un motor no detiene el otro |
| Límite físico alcanzado | ángulos actuales | `current_motor_limits.limit_labels` | `apply_mechanical_limits()` | etiqueta de estado y bitácora | detención exacta y señal este/oeste/mínimo/Home |
| Pose completa del espejo | ángulos actuales y errores del escenario | `WebScenarioGeometry.pose` | `mirror_pose_from_altaz()` | escena 3D | base ortonormal; arista inferior con componente z igual a cero |
| Errores y corrección | `ErrorConfig`, deriva, muestra de movimiento y corrección acumulada | tres `WebScenarioRequest`: Ideal, Con error y Corregido | pose, reflexión e impacto del núcleo | comparación paralela y diagnóstico | escenario ideal centrado y escenario con error desplazado |
| Rayo reflejado | vector solar y pose alcanzada | `WebScenarioGeometry.reflected` | `reflected_direction()` | vector 3D y facetas | ley de reflexión y dirección al receptor |
| Impacto receptor | rayo y plano receptor | `WebScenarioGeometry.impact` | `receiver_impact()` | spot, tolerancia, corrección y CSV | coordenadas u/v, error radial y distancia de rayo |
| Noche | altura solar y umbral | `ideal_step.operational == False` | `sun_is_operational()` | estado y escena | conserva pose mecánica; no inventa impacto ni comandos solares |
| Historial y exportación | `snapshot()` | el adaptador llena las mismas claves escalares | sin fórmulas nuevas | CSV y ZIP | CSV conserva 166 columnas |
| Escena 3D | `scene_payload()` | añade arista y dirección superior solo al payload visual | `MirrorPose` | `twin3d.js` | no añade columnas al historial |
| Empaquetado científico | `shinylive_requirements.txt` | URI `site:` resuelta contra el mismo servidor | instalación `micropip` de rueda validada | Pyodide | SHA-256 fijo, sin solicitudes a PyPI |

## 3. Pseudocódigo del flujo conectado

```text
leer controles existentes y fecha activa
construir WebPhysicsRequest

ideal_step = simulate_physical_step(...)

si el Sol es operativo:
    obtener comandos ideales de acimut y altura
    aplicar calibraciones nominales
    recortar independientemente a los límites físicos
si no:
    conservar los objetivos actuales y no fabricar impacto

para escenario en [Ideal, Con error, Corregido]:
    formar comandos independientes de ambos motores
    aplicar únicamente los errores correspondientes al escenario
    pose = mirror_pose_from_altaz(acimut, altura)
    verificar base ortonormal y arista horizontal
    si el Sol es operativo:
        reflejado = reflected_direction(rayo_incidente, pose.normal)
        impacto = receiver_impact(reflejado, receptor)

seleccionar el escenario visible
actualizar el diccionario histórico sin cambiar sus columnas
añadir la base completa solamente al payload de la escena 3D
mover cada motor gradualmente hacia su propio objetivo
si un eje llega a un límite:
    detenerlo exactamente en la frontera
    mostrar etiqueta y registrar evento
```

## 4. Fronteras de responsabilidad

- `physics_core.py`: ecuaciones y operaciones matemáticas.
- `physics_pipeline.py`: orden físico de una solución ideal completa.
- `physics_adapter.py`: traducción entre el contrato web y las estructuras V2.
- `engine.py`: estado temporal, motores, historial, errores experimentales y exportación.
- `app.py`: interfaz y reactividad existentes.
- `twin3d.js`: representación visual de la pose ya calculada; no resuelve óptica.
