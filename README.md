# Simulador web del mini horno solar 0.5.0

Edición web experimental y sin servidor del gemelo digital del mini horno
solar. El simulador se ejecuta directamente en el navegador mediante
Shinylive y Pyodide; GitHub Pages entrega únicamente archivos estáticos.

## Abrir el simulador

La versión publicada estará disponible en:

<https://juliolanda.github.io/simulador-horno-solar-web/>

La primera carga puede tardar un poco mientras el navegador prepara Python.
Después, los cálculos se realizan localmente en el dispositivo del usuario.

## Funciones incluidas

- Reloj en tiempo real o fecha simulada con multiplicador.
- Modos automático, manual y Home con movimiento gradual.
- Seguimiento programable por intervalos solares o bajo orden manual.
- Comparación simultánea Ideal / Con error / Corregido.
- Errores geométricos y mecánicos configurables y reproducibles.
- Seis estrategias de corrección, incluida cámara periódica.
- Gemelo 3D WebGL con profundidad, cámara libre y vistas fijas.
- Click izquierdo para desplazar, click derecho para girar y rueda para zoom.
- Perfil precargado del Minihorno IER y dimensiones personalizables.
- Posición solar exacta por D&B, REDA-Andreas y la entrada SPA/PVLIB.
- Cálculo de normal, reflexión e impacto sobre el receptor.
- Vistas del gemelo, spot, trayectoria solar, facetas, deriva y diagnóstico.
- Acomodo de facetas cuadradas, circulares y hexagonales.
- Historial local, replay, bitácora de eventos y CSV experimental de 166 columnas.
- Paquete ZIP con historial, resultados por faceta y bitácora de eventos.
- Interfaz adaptable a computadoras y pantallas angostas.

Esta edición web conserva el alcance educativo del escritorio y acerca sus
funciones experimentales principales al navegador. Los resultados siguen
requiriendo validación física antes de tomar decisiones de diseño o seguridad.

## Desarrollo local

```powershell
uv sync --project web_app
uv run --project web_app shiny run web_app/app.py
```

## Exportación estática

```powershell
uv run --project web_app python web_app/export_shinylive_app.py
```

El exportador incluye el núcleo V2 y publica la rueda validada de `pvlib` bajo
`_site/assets/`, separada de `app.json` para mejorar su caché.

## Validación

```powershell
uv run --project web_app python -m unittest web_app.test_engine web_app.test_physics_core web_app.test_physics_pipeline web_app.test_physics_adapter web_app.test_three_vendor web_app.test_shinylive_smoke web_app.test_export_shinylive_smoke web_app.test_export_shinylive_app
```

La escena 3D usa una copia local fijada de `three@0.180.0`; no solicita
Three.js desde una CDN. Su licencia y procedencia están documentadas en
`web_app/www/vendor/three/README.md`.

Después de exportar el sitio, la revisión automática en Chrome se ejecuta con:

```powershell
uv run --project web_app --group dev python web_app/e2e_browser.py --site _site
```

Esta prueba abre la exportación Shinylive y la aplicación Shiny directa. Revisa
la carga local de recursos, el lienzo 3D, Home, la independencia de los dos ejes
y la horizontalidad de la arista inferior del espejo.

## Prueba aislada en Shinylive/Pyodide

La miniaplicación de diagnóstico usa el mismo núcleo canónico, pero se exporta
en una carpeta separada para no modificar la interfaz del simulador:

```powershell
uv run --project web_app python web_app/export_shinylive_smoke.py
uv run --project web_app python -m http.server 8008 --bind 127.0.0.1 --directory _site/shinylive-smoke
```

El resultado se abre en <http://127.0.0.1:8008/>. La página debe mostrar
`RESULTADO: PASS`. El exportador descarga la rueda oficial de `pvlib==0.15.2`
solo si no existe en la caché de construcción, comprueba su SHA-256 y la
incorpora al sitio. La visita en navegador no consulta PyPI. Las condiciones
verificadas y los costos de carga están en
`docs/compatibilidad_shinylive_physics_v2.md`.
