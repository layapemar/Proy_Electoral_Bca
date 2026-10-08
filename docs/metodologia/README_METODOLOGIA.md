# Piloto de datos electorales: Barrancabermeja, presidencia 2026 (primera vuelta)

Fuente primaria: ZIP MMV_Presidente1V_2026.zip de la Registraduría. SHA-256: `e8623fdc10d0f0a37ffb984e477f26ce8315759596fdc7837729de86e9215642`. El archivo original queda separado de estas tablas derivadas. El esquema de preconteo, escrutinio, DIVIPOL y candidatos proviene del PDF `Estructuras Basicas (1808).pdf` contenido en el propio ZIP.

## Contenido

- `preconteo`: 8,941 registros, 121,378 votos reportados en 566 mesas. Registros de ancho fijo (38 bytes).
- `escrutinio`: 9,056 registros, 121,683 votos en 566 mesas. Doce campos separados por punto y coma.
- `novedades`: 566 filas, una por mesa; incorpora `totalVotos`, `potencial` y otras variables del archivo anidado de novedades.
- `control_mesas`: comparación por mesa entre preconteo, escrutinio y novedades.
- `divipol_local`: 67 puestos, nombre de comuna, potencial por puesto y número de mesas declaradas.
- `control_calidad.json`: huellas oficiales verificadas, recuentos y criterio de avance.

## Interpretación y límites

El código territorial **electoral** en este ZIP es departamento `27`, municipio `019`; se obtuvo del DIVIPOL adjunto y se cruzó por zona y puesto. Es distinto del código DANE `68081`, cuya equivalencia requiere una tabla explícita cuando se unan datos externos. Todas las claves con ceros iniciales deben leerse como texto (`dtype=str` en pandas). `votos` y las magnitudes numéricas de novedades pueden convertirse a enteros.

El escrutinio cuadra con `totalVotos` en **566 de 566 mesas**; además, el recuento de mesas por los 67 puestos coincide con DIVIPOL. Preconteo y escrutinio difieren en 33 mesas, con diferencia neta de +305 votos (escrutinio menos preconteo). Esta comparación no atribuye causas; conservar ambas fuentes. Los códigos de opción `996`, `997` y `998` no tienen etiqueta en los catálogos incluidos, por eso se conservan como códigos sin asignarles un nombre de categoría. El campo de comuna de escrutinio (`00` aquí) se conserva separado del de DIVIPOL.

La aprobación del piloto se refiere a calidad estructural y conciliación interna; no certifica firmeza jurídica ni cubre otras elecciones del catálogo. El cuaderno `00_auditoria_fuentes(4).ipynb` reproduce la generación y registra las rutas en la auditoría del proyecto.
