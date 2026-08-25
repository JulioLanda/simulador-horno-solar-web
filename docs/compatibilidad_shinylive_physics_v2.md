# Compatibilidad del núcleo físico V2 con Shinylive/Pyodide

## 1. Objetivo y alcance

Esta prueba comprueba que `physics_core.py` y `physics_pipeline.py` pueden
ejecutarse dentro del navegador, no solamente en Python local. Se utiliza una
miniaplicación independiente para no modificar todavía la interfaz, el motor
estable ni la escena 3D del simulador.

Archivos fuente de la prueba:

- `web_app/shinylive_smoke_app.py`;
- `web_app/shinylive_requirements.txt`;
- `web_app/export_shinylive_smoke.py`;
- `web_app/test_shinylive_smoke.py`;
- `web_app/test_export_shinylive_smoke.py`.

La exportación copia los archivos canónicos `physics_core.py` y
`physics_pipeline.py` a una carpeta de staging ignorada por Git. No existe una
segunda copia mantenida manualmente del núcleo matemático.

## 2. Entorno verificado

Prueba autocontenida ejecutada el 25 de agosto de 2026 con:

| Componente | Versión en el navegador |
|---|---:|
| Shinylive | 0.10.14 |
| Python/Pyodide | CPython 3.12.7, plataforma `emscripten` |
| NumPy | 2.0.2 |
| SciPy | 1.14.1 |
| pandas | 2.2.3 |
| pvlib | 0.15.2 |
| h5py | 3.12.1 |
| requests | 2.31.0 |

## 3. Resultado

El resultado visible final fue:

```text
RESULTADO: PASS
```

Las cuatro comprobaciones aprobaron:

1. Importación y ejecución real de NumPy, SciPy, pandas, pvlib y dependencias.
2. Cadena completa mediante REDA-Andreas/NREL SPA.
3. Cadena completa mediante la entrada SPA/PVLIB.
4. Cadena completa mediante Duffie-Beckman de `pvlib`.

En los tres métodos solares, el caso ideal de Temixco produjo:

- Sol operativo;
- comandos dentro de límites;
- intersección válida con el receptor;
- error radial inferior a `1 × 10⁻⁹ m`;
- razón final `impacto_valido`.

REDA y SPA produjeron un error radial de aproximadamente
`6.18 × 10⁻¹⁶ m`. Duffie-Beckman produjo aproximadamente
`1.14 × 10⁻¹⁵ m`. Estas magnitudes corresponden a redondeo numérico.

No se registraron errores en la consola durante la exportación final. Las únicas
advertencias provinieron de nombres de idioma obsoletos incluidos por
Bootstrap Datepicker y no afectan el núcleo físico.

## 4. Hallazgos de empaquetado

La compatibilidad es correcta, pero requiere una configuración explícita:

1. `pvlib` no pertenece al catálogo binario incluido por defecto en esta
   versión de Pyodide.
2. Shinylive lo instala correctamente mediante `requirements.txt` y
   `micropip` desde una rueda estática publicada en el mismo sitio.
3. El export reducido no descubrió automáticamente todas las dependencias
   transitivas de `pvlib`.
4. La prueba importa expresamente `h5py`, `requests`, `certifi`,
   `charset-normalizer`, `urllib3` y `pkgconfig` para que Shinylive copie sus
   ruedas compatibles desde el catálogo local de Pyodide.

Por tanto, cuando el núcleo se conecte a la aplicación principal, su proceso de
exportación también deberá:

- incluir la rueda fijada de `pvlib==0.15.2` bajo `assets/` y referenciarla
  mediante la URI portable `site:` que el postproceso convierte en URL;
- verificar antes de exportar que su SHA-256 sea
  `42035b063cc692bc3ece9480246297ccf211c835f1151faa752acac9584f6bb5`;
- hacer que el export reducido incluya las dependencias anteriores;
- conservar NumPy, SciPy y pandas entre los paquetes detectados;
- comprobar el resultado en navegador después de cada cambio de versión.

`web_app/export_shinylive_smoke.py` automatiza esas operaciones para la prueba
aislada y `web_app/export_shinylive_app.py` hace lo mismo para la aplicación
principal. La rueda descargada y el sitio generado se guardan bajo `build/` y
`_site/`, respectivamente; ambas rutas están ignoradas por Git. Así se evita
versionar un binario grande, pero cada exportación sigue siendo reproducible y
verifica exactamente el archivo que incorpora.

## 5. Tiempos observados

En la comprobación autocontenida final, una ejecución completa del informe
dentro de Pyodide tardó aproximadamente `4.98 s`:

| Operación | Tiempo observado |
|---|---:|
| Importación y prueba de bibliotecas científicas | 4853.5 ms |
| Paso físico REDA | 79.3 ms |
| Paso físico SPA | 28.1 ms |
| Paso físico Duffie-Beckman | 17.8 ms |

La navegación autocontenida mostró `RESULTADO: PASS` aproximadamente `8.7 s`
después de abrir la página en el equipo de prueba. Es una observación funcional,
no un benchmark controlado.

Estos tiempos corresponden al servidor local y al equipo de prueba. En GitHub
Pages dependerán de la conexión, caché, procesador y memoria del dispositivo.

## 6. Tamaño y dependencia de red

La aplicación principal autocontenida ocupa `86,339,720 bytes`, aproximadamente
`82.3 MiB`. La prueba aislada ocupa `85,214,407 bytes`, aproximadamente
`81.3 MiB`. La rueda oficial fijada de `pvlib==0.15.2` ocupa
`19,355,575 bytes`, aproximadamente `18.5 MiB`.

La rueda ya no está codificada dentro de `app.json`. En la aplicación principal,
`app.json` mide `1,205,590 bytes`; en la prueba aislada mide `80,437 bytes`.
`pvlib` se entrega como `assets/pvlib-0.15.2-py3-none-any.whl`, lo que evita la
expansión Base64 y permite almacenarlo en caché independientemente del código.

Three.js r180, `OrbitControls` y el módulo `three.core.min.js` se distribuyen
dentro de `www/vendor/three/`, junto con la licencia MIT. La escena ya no
consulta `esm.sh` ni otra CDN durante la visita. Estos módulos agregan unos
`0.74 MiB` al código de la aplicación y explican el aumento de `app.json`.

Se adoptó la opción de distribuir la rueda junto con el sitio. En la prueba
final, el registro mostró que `micropip` instaló
`https://servidor-del-simulador/assets/pvlib-0.15.2-py3-none-any.whl` —en la
prueba local, la URL equivalente bajo `127.0.0.1`— y no se observaron
solicitudes a `pypi.org` ni a `pythonhosted.org`. La primera visita todavía
necesita descargar los archivos estáticos desde el servidor del simulador, pero
ya no depende de que PyPI esté disponible ni de una segunda descarga externa.

La contrapartida es una publicación y una primera transferencia más grandes.
Después de almacenarse en caché, las visitas posteriores pueden reutilizar los
recursos del sitio según el comportamiento del navegador y del servidor.

## 7. Integración de la aplicación principal

La aplicación principal exportada también fue verificada en navegador. Conservó
menús, controles, historial, replay, facetas, correcciones, descargas y el CSV de
166 columnas. En un caso diurno con objetivo retenido:

- los motores de acimut y altura avanzaron gradualmente e independientemente;
- la escena recibió la base completa del espejo;
- la componente vertical de la arista inferior fue exactamente `0`;
- el rayo reflejado llegó al plano receptor;
- el estado alcanzó `EN OBJETIVO` con error radial observado de `0.73 mm`.

La escena representa ahora el soporte mediante un tubo central, un eje vertical
de acimut y el eje horizontal transportado por esa rotación. El espejo ya no se
orienta solamente con su normal.

La comprobación queda automatizada por `web_app/e2e_browser.py`. En Chrome
verifica la exportación Shinylive sin solicitudes externas y después acciona
Home, oeste y bajar sobre la aplicación directa. La prueba confirma que los
objetivos de ambos motores son independientes y que la componente vertical de
la arista inferior permanece dentro de `1e-10` de cero. El conjunto local
actual contiene `73` pruebas unitarias, además de esta prueba de navegador.

## 8. Conclusión técnica

El núcleo físico V2 es compatible con Shinylive/Pyodide bajo la configuración
de empaquetado verificada. REDA, SPA y Duffie-Beckman funcionan dentro del
navegador y producen el mismo cierre óptico esperado por las pruebas locales.

La compatibilidad no es automática: depende de fijar y validar la rueda de
`pvlib==0.15.2`, declarar sus dependencias Pyodide y conservar una prueba real
de navegador en el flujo de validación. La alternativa autocontenida queda
verificada sin dependencia de PyPI, `pythonhosted.org` ni `esm.sh` durante la
ejecución.
