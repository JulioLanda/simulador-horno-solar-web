# Simulador web del mini horno solar 0.2

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
- Gemelo 3D WebGL con profundidad, cámara libre y vistas fijas.
- Click izquierdo para desplazar, click derecho para girar y rueda para zoom.
- Perfil precargado del Minihorno IER y dimensiones personalizables.
- Posición solar por los métodos D&B y REDA.
- Cálculo de normal, reflexión e impacto sobre el receptor.
- Vistas del gemelo, spot, trayectoria solar, facetas, deriva y diagnóstico.
- Acomodo de facetas cuadradas, circulares y hexagonales.
- Historial local y descarga en CSV.
- Interfaz adaptable a computadoras y pantallas angostas.

Esta edición web es una primera fase y no sustituye a la versión 2.0 de
escritorio.

## Desarrollo local

```powershell
uv sync --project web_app
uv run --project web_app shiny run web_app/app.py
```

## Exportación estática

```powershell
New-Item -ItemType Directory -Force build/digital_twin, build/www
Copy-Item web_app/app.py, web_app/engine.py build/
Copy-Item web_app/www/* build/www/
Copy-Item digital_twin/*.py build/digital_twin/
uv run --project web_app shinylive export build _site
```

## Validación

```powershell
uv run --project web_app python -m unittest web_app.test_engine
```
