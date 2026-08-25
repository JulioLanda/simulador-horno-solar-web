# Three.js local

Archivos vendorizados del paquete oficial `three@0.180.0`:

- `three.module.min.js`: modulo ES de Three.js.
- `three.core.min.js`: nucleo importado por el modulo ES desde Three.js r180.
- `OrbitControls.js`: control de camara usado por el gemelo digital.
- `LICENSE`: licencia MIT original del proyecto.

Origen: `https://registry.npmjs.org/three/-/three-0.180.0.tgz`

SHA-512 del paquete descargado:

`a3eab2700319ae1f93b04d351aa594c5420a47500bd12f29abbcc3918390c3c1aa7d7f1bf15a022985281db8625f98feee1afc5ecb870d553afa09102502a0f7`

La unica adaptacion local de `OrbitControls.js` es sustituir el importador
desnudo `three` por `./three.module.min.js`, ya que estos archivos se sirven
directamente en el navegador sin un empaquetador JavaScript.
