# Catálogo de fuentes

**Observatorio de Dinámicas Electorales de Barrancabermeja**
Actualizado: octubre de 2026

Este documento registra de dónde sale cada dato del proyecto y cómo se obtiene. Es la
referencia que permite que cualquier persona reproduzca el corpus desde cero.

---

## 1. Registraduría Nacional del Estado Civil · paquetes MMV

Los resultados por mesa se publican como paquetes **MMV** (Modelo de Mesa Virtual): un ZIP
por elección y departamento que trae los votos mesa por mesa, los catálogos básicos y el PDF
que documenta la estructura de cada archivo.

### 1.1 Plantillas de descarga

Estas URL **no aparecen como enlaces** en el portal: la página las construye en JavaScript a
partir de un selector de departamento. Fueron leídas del código del propio portal y
verificadas una por una comprobando que la respuesta empieza con la firma `PK` de un archivo
ZIP.

| Familia | Plantilla | Verificada |
| --- | --- | --- |
| Territoriales 2023 | `https://observatorio.registraduria.gov.co/comprimidos/MMV_TERRITORIALES2023_{DEPARTAMENTO}.zip` | sí |
| Territoriales 2019 | `https://observatorio.registraduria.gov.co/comprimidosTwo/MMV_TERRITORIALES2019_{DEPARTAMENTO}.zip` | sí |
| Congreso 2022 | `https://observatorio.registraduria.gov.co/congreso22/MMV_CONGRESO_2022_{DEPARTAMENTO}.zip` | sí |
| Presidencia 2018 · 2ª vuelta | `https://observatorio.registraduria.gov.co/comprimidosTwo/MMV_PRESIDENTE_V2_2018_{DEPARTAMENTO}.zip` | sí |
| Nacionales (presidencia, congreso 2026) | `https://observatorio.registraduria.gov.co/anexos/MMV_*.zip` | sí |
| Genérico por departamento | `https://observatorio.registraduria.gov.co/comprimidosTwo/MMV_{DEPARTAMENTO}.zip` | parcial |

**Formato de `{DEPARTAMENTO}`:** mayúsculas, con guion bajo en lugar de espacio.
`SANTANDER`, `NORTE_DE_SANTANDER`, `LA_GUAJIRA`, `SAN_ANDRES`.

Como la plantilla es por departamento, estas URL abren los 32 departamentos, no solo
Santander. Eso permite comparar a Barrancabermeja contra su propio departamento sin trabajo
adicional.

### 1.2 Dos trampas del servidor

**Rechaza `HEAD`.** Una petición `HEAD` responde 500 con una página de error HTML, aunque el
archivo exista. Hay que pedir con `GET`; para verificar sin descargar todo, se pide un rango
de bytes y se comprueba la firma `PK`.

**El código territorial electoral no es el código DANE.** Barrancabermeja es `68081` en el
DANE, pero en el paquete de presidencia 2026 su código electoral era departamento `27`,
municipio `019`. No son equivalentes y no se cruzan sin una tabla de equivalencia explícita.
El cuaderno 01 **descubre** el código buscando el nombre del municipio en el DIVIPOL de cada
paquete, en lugar de suponerlo, porque puede cambiar entre paquetes.

Los códigos llevan ceros a la izquierda. Al leer cualquier tabla de este proyecto hay que
usar `dtype=str`: convertirlos a número convierte `019` en `19` y rompe todos los cruces.

### 1.3 Dos arquitecturas distintas, no una

Este es el punto donde es fácil equivocarse. Los paquetes MMV **no comparten estructura
interna**, y suponer que la comparten hace que la lectura falle por completo o, peor, que
produzca una tabla plausible y equivocada.

**Formato A · CSV consolidado.** Territoriales 2019 y 2023, Congreso 2022 y anteriores.
Un único CSV con cabecera explícita más su archivo de huellas. Cada fila es un voto por
mesa, corporación, partido y candidato, con los nombres ya resueltos. No necesita
catálogos. Es el formato de los históricos y el más fácil de usar.

| Elección | Codificación | Columnas | Descomprimido |
| --- | --- | --- | --- |
| Territoriales 2023 · Santander | UTF-8 | 18 | 192 MB |
| Territoriales 2019 · Santander | UTF-8 | 18 | 168 MB |
| Congreso 2022 · Santander | **UTF-16** | 21 (agrega circunscripción y CITREP) | 204 MB |

Columnas: código y nombre de departamento, municipio, zona, puesto, mesa, comuna,
corporación, circunscripción, partido y candidato, más el total de votos. Congreso 2022
agrega nombre de circunscripción y código y nombre de CITREP.

**Formato B · catálogos y archivos de ancho fijo.** Presidencia y Congreso 2026.

| Archivo | Formato | Contenido |
| --- | --- | --- |
| `DIVIPOL_*.TXT` | ancho fijo, 13 campos | Puestos, **potencial de sufragantes**, mesas declaradas, comuna |
| `CANDIDATOS_*.TXT` | ancho fijo, 13 campos | Todos los inscritos, incluidos los de cero votos; nombre, partido, **género** |
| `PARTIDOS_*.TXT` | ancho fijo | Código y nombre de cada agrupación |
| `*PRECONTEO*.txt` | ancho fijo, 38 bytes | Votos según el informe de la jornada |
| `*ESCRUTINIO*.csv` | delimitado por `;`, 12 campos | Votos según el resultado jurídico |
| `HASH*.txt` | UTF-16 | SHA-256 oficiales |
| `Estructuras Basicas (*).pdf` | PDF | La documentación de los campos |

El formato B da más detalle —potencial de sufragantes, género, preconteo frente a
escrutinio— a cambio de ser más trabajoso. El A no trae censo, ni género, ni la distinción
entre los dos conteos.

`detectar_formato()` en `src/ingesta/lector_mmv.py` decide cuál es cada paquete mirando sus
miembros, y la decisión queda escrita en la auditoría del cuaderno.

### 1.4 Tres trampas de los datos, verificadas contra los archivos reales

**El código de puesto no siempre identifica el puesto.** En Congreso 2022, `Código Puesto`
viene en `00` para varios puestos distintos de la zona 99 (la rural): EL LLANITO SEDE A,
EL LLANITO SEDE B, ESC. LAURELES, PUEBLO REGAO CAMPO 23 y COL. BLANCA DURÁN comparten
código. 61 puestos reales se colapsan en 56 códigos. Toda agregación territorial usa
`id_puesto` —construido con zona, código y nombre normalizado, determinista— y nunca
`cod_puesto`.

**El código de puesto es alfanumérico.** En 2019 y 2023 la zona rural usa `A1`, `A5`,
`B2`. Convertirlo a número destruye esas filas.

**El código de comuna viene pegado al nombre** en algunos años: `06COMUNA 6`,
`10CORREG. LA FORTUNA AUTOPISTA`. El original se conserva tal cual; se agrega
`comuna_normalizada` solo cuando el prefijo coincide exactamente con el código, y queda
registrado cuántas filas se tocaron.

### 1.5 Clasificación de las filas de voto

No todas las filas son votos a una persona, y ninguna se descarta.

| `clase_opcion` | Qué es |
| --- | --- |
| `candidatura` | Voto a una persona concreta de una lista |
| `voto_de_lista_no_preferente` | Voto a la lista sin marcar candidato. **Verificado: no es la suma de los candidatos, son votos distintos** |
| `opcion_especial` | Voto en blanco (996), nulo (997) o no marcado (998) |
| `agregado_sin_candidatura` | Fila de totales que el propio archivo trae |

Las tres clases suman exactamente el total de votos del archivo. Esto se comprueba en cada
corrida, porque es la garantía de que no hay doble conteo.

### 1.6 Corporaciones

Un paquete territorial trae **cinco elecciones distintas en el mismo archivo**. Los códigos
**no son universales**: `001` es GOBERNADOR en una territorial y PRESIDENTE en una
presidencial; `02` es CÁMARA en Congreso 2022. Por eso el nombre se toma del archivo y no
de un mapa interno.

Observado en Barrancabermeja: GOBERNADOR, ASAMBLEA, ALCALDE, CONCEJO y JAL en 2019 y 2023;
SENADO y CÁMARA en 2022.

Cada corporación tiene su propio universo de candidatos y su propia fórmula de asignación.
**No se suman entre sí.** El proyecto las escribe en tablas separadas y no existe ninguna
salida que las combine.

### 1.7 Lo que ya está extraído

Ejecutado el cuaderno 01 contra los paquetes reales:

| Año | Corporaciones | Filas | Votos |
| --- | --- | --- | --- |
| 2019 | Gobernador, Asamblea, Alcalde, Concejo, JAL | 93.595 | 598.822 |
| 2022 | Senado, Cámara | 48.207 | 202.035 |
| 2023 | Gobernador, Asamblea, Alcalde, Concejo, JAL | 138.142 | 649.758 |

Código electoral de Barrancabermeja observado en los tres años y en 2026: departamento
`27`, municipio `019`. Las huellas SHA-256 de los tres CSV coinciden con los manifiestos
oficiales de sus paquetes.

Validación externa: en Alcaldía 2023 la tabla da 72.593 votos a Jonathan Stivel Vásquez
Gómez, que es el alcalde efectivamente electo, y en Gobernación 2023 encabeza Juvenal Díaz
Mateus, el gobernador electo de Santander.

---

## 1.8 Antes de 2018 no hay datos por mesa

Verificado contra el portal y contra el contenido de los propios archivos.

El selector de años del Observatorio ofrece 2026, 2023, 2022, 2021, 2019, 2018 y luego un
paquete agrupado "1997 – 2015". Dentro de ese grupo hay territoriales de 2000, 2003, 2007,
2011 y 2015, todas con ZIP válido, en `/comprimidoThree/{NOMBRE_CON_GUIONES_BAJOS}.zip`
(el nombre es el texto visible de la opción con los espacios cambiados por guiones bajos).

**Pero no son datos.** Leyendo el directorio interno de los ZIP sin descargarlos:

| Elección | Tamaño | Contenido real |
| --- | --- | --- |
| 2015 territoriales | 347 MB | `setupEstadisticas.exe` (299 MB) + `jre-8u66-windows-i586.exe` + un PDF |
| 2011 territoriales | 254 MB | `setup.exe` (209 MB) + `Adobe.exe` + `jre-7u5` + manual en PDF |
| 2007 territoriales | 225 MB | instalador equivalente |
| 2003 territoriales | 121 MB | instalador equivalente |
| 2000 territoriales | 19 MB | instalador equivalente |

Son instaladores de una aplicación de escritorio de Windows de la época, con los datos
adentro. No se ejecutan ni se descargan en este proyecto. El portal oficial de estadísticas
electorales (`estadisticaselectorales.registraduria.gov.co`) tampoco cubre el período: para
territoriales solo ofrece 2023 y 2019.

**Conclusión:** el formato abierto con resultados mesa por mesa empieza en 2018. Para la
serie histórica se usa el CEDE, a nivel de municipio. Ver la sección 5.

---

## 2. Fuentes que no se descargan con una URL

Estas exigen un navegador y una consulta interactiva. Se listan con lo que bloquean, para que
el pendiente tenga consecuencia.

| Fuente | Dónde | Bloquea |
| --- | --- | --- |
| Censo electoral histórico por puesto | [registraduria.gov.co](https://www.registraduria.gov.co/-Consulta-los-censos-historicos-utilizados-para-los-procesos-electorales-desde-.html) | Participación y abstención: el censo es el denominador. **Localizado, ver 2.1** |
| Candidaturas inscritas 2023 | [wapp.registraduria.gov.co](https://wapp.registraduria.gov.co/electoral/elecciones-territoriales-2023/) | Nada de forma absoluta: el cuaderno 01 ya reconstruye la oferta desde `CANDIDATOS` del propio paquete. Sirve de contraste |
| Candidaturas inscritas 2019 | [wapp.registraduria.gov.co](https://wapp.registraduria.gov.co/electoral/Elecciones-2019/infocandidatos2019.php) | Igual que la anterior |
| Cuentas Claras (CNE) | [cnecuentasclaras.gov.co](https://www.cnecuentasclaras.gov.co/) | Todo el análisis de financiación y su cruce con contratación |
| Comunas, barrios y corregimientos | Geoportal DANE · IGAC · Planeación del Distrito | Todo el análisis espacial: Moran's I, LISA, Getis-Ord, y los mapas |

Al guardarlas, van a `datos/brutos/<fuente>/` sin modificar el archivo descargado.

### 2.1 Censo electoral por puesto · cómo obtenerlo

Está en la consulta de censos históricos de la Registraduría, y cubre exactamente los años
del corpus: **2018, 2019, 2022, 2023, 2024, 2025 y 2026**.

La consulta filtra por **Año · Tipo de elección · Departamento · Municipio · Zona · Puesto**
y la tabla trae estas columnas:

| Columna | |
| --- | --- |
| Año | |
| Tipo de elección | |
| Departamento | |
| Municipio | |
| Zona | |
| **Puesto de votación** | la granularidad que necesita el proyecto |
| Sexo · Hombres · Mujeres · Otros | permite además el análisis por sexo |

Tiene botones de exportación a **Excel, CSV y PDF**.

**Procedimiento**, una vez por elección:

1. Abrir la página de consulta de censos históricos.
2. Año → el de la elección. Tipo de elección → la que corresponda; la lista de tipos cambia
   según el año elegido.
3. Departamento → SANTANDER. Municipio → BARRANCABERMEJA. Zona y Puesto se dejan sin
   filtrar, para traer todos los puestos.
4. Cambiar "registros por página" a 100 y exportar con el botón **CSV**.
5. Guardar en `datos/brutos/registraduria/censo/` con el nombre
   `censo_{año}_{eleccion}_barrancabermeja.csv`.

**Las tres que necesita el corpus actual:** territoriales 2019, Congreso 2022 y
territoriales 2023.

**Advertencia de uso.** El censo es el denominador de la participación, y el censo que se
usa es el de **esa** elección, no el de otro año. Mezclarlos produce tasas de participación
que parecen razonables y están mal. Por eso el archivo lleva el año en el nombre y la tabla
conserva la columna `Año`.

---

## 3. DANE

| Fuente | Qué aporta |
| --- | --- |
| Proyecciones de población municipal 2005–2017 y 2018–2042 | Denominadores demográficos y tasas por habitante |
| CNPV 2018 | Variables socioeconómicas por manzana, para caracterizar territorios |
| Marco geoestadístico nacional | Geometrías municipales |

---

## 4. Reglas de uso que aplican a todas las fuentes

1. **El original no se modifica nunca.** Vive en `datos/brutos/` tal como se descargó, con su
   huella SHA-256 registrada.
2. **Preconteo y escrutinio se conservan separados.** El preconteo es el informe de la
   jornada; el escrutinio es el resultado jurídico y es el que se usa para afirmar cualquier
   cosa sobre resultados. Se comparan para documentar cuánto corrigió el escrutinio, nunca
   para reemplazar uno con el otro ni para promediarlos. Que difieran es el procedimiento
   funcionando, no una anomalía.
3. **Nada se imputa.** Si un dato falta, falta.
4. **Los valores extremos se marcan, no se borran.** Un resultado raro es un hallazgo.
5. **Lo que no se puede etiquetar se marca y se cuenta.** Los votos en blanco y nulos
   (códigos 996, 997, 998) se conservan con su código, porque el paquete no les da nombre. En
   ningún caso se elimina una fila para que cuadren los totales.
6. **Los candidatos y electos se nombran.** Son figuras públicas que se sometieron al voto.
7. **La cédula no se escribe.** Se usa solo para cruzar catálogos dentro de un paquete y no
   llega a ninguna tabla del proyecto. Hay una comprobación automática en cada corrida.
8. **Los financiadores personas naturales se agregan, nunca se nombran** en un producto
   público.
9. **Toda cifra de Cuentas Claras lleva escrita al lado que lo reportado no es lo gastado.**
10. **Una anomalía estadística no es evidencia de fraude**, y un dato agregado no permite
    inferir el comportamiento de una persona (falacia ecológica).

---

## 5. CEDE · Universidad de los Andes · serie histórica municipal

*Resultados Electorales de Colombia*, Centro de Estudios sobre Desarrollo Económico (CEDE),
Universidad de los Andes. DOI [`10.71590/R2KLKI`](https://doi.org/10.71590/R2KLKI),
licencia **CC0**. De 1958 a hoy, con Presidencia, Senado, Cámara, Gobernación, Asamblea,
Alcaldía y Concejo, con detalle por candidato y por partido. Formatos `.dta` (Stata) y
`.tab` (delimitado por tabulador), más un diccionario de datos en PDF. Los archivos se
llaman `{año}_{tipo}.{ext}`.

**Años de Concejo disponibles**, verificado contra la API del repositorio: 1972, 1974, 1976,
1978, 1980, 1982, 1984, 1986, 1990, 1992, 1994, 1997, 2000, 2003, 2007, 2011, 2015, 2019 y
2023.

**Granularidad: municipio.** No hay puesto ni mesa. Esto define los dos niveles del corpus:

| Nivel | Fuente | Concejo | Sirve para |
| --- | --- | --- | --- |
| Mesa | MMV Registraduría | 2019, 2023 | Distribución por comuna y puesto, análisis espacial |
| Municipio | CEDE | 1997 – 2023 | Serie larga: fragmentación, volatilidad, partidos efectivos |

**Los dos niveles no se mezclan** en un mismo indicador sin declararlo. Toda tabla del CEDE
lleva `nivel_geografico = "municipio"` y `fuente = "CEDE"`.

**El solape es la validación.** 2019 y 2023 existen en las dos fuentes. Los totales
municipales del CEDE se comparan contra la suma de las tablas mesa a mesa del MMV. Si
cuadran, la serie histórica hereda esa credibilidad; si no, queda escrito en cuánto
difieren. Sin ese contraste, la serie larga no sería verificable.

**Dos identificadores con el mismo nombre.** El buscador global del repositorio devuelve
archivos de otros depósitos con nombres idénticos (`1997_concejo.tab` aparece con dos
identificadores distintos). Los identificadores se resuelven **dentro del DOI**, nunca desde
el buscador: un identificador equivocado daría una tabla plausible y falsa.

**Red.** El dominio no está en la lista blanca del proxy que usan las herramientas
automáticas de este proyecto. La descarga funciona ejecutando `src/ingesta/cede.py` con el
Python local, que tiene red abierta.

**Citación obligatoria** en cualquier producto que use estos datos:

> Centro de Estudios sobre Desarrollo Económico (CEDE), Universidad de los Andes.
> *Resultados Electorales de Colombia.* https://doi.org/10.71590/R2KLKI

---

## 6. OpenStreetMap · geometrías de comuna y corregimiento

Módulo: `src/geoespacial/osm.py`. Se consulta la **Overpass API** y se guarda GeoJSON en
`datos/geograficos/`. Licencia **ODbL 1.0**, con atribución obligatoria a los
colaboradores de OpenStreetMap en cualquier mapa que se publique.

### Por qué no es el DANE

La fuente oficial de los límites de comuna y corregimiento es el **Marco Geoestadístico
Nacional** del DANE. Su geoportal no respondió desde el entorno automático y la descarga
manual tampoco se completó. OpenStreetMap sí tiene cargadas las siete comunas como
límites administrativos, y eso resuelve la geometría urbana, donde está la mayor parte del
censo electoral.

La diferencia importa y queda escrita: OSM es colaborativo, no catastral. Cada polígono se
guarda con su `osm_id` y la fecha de consulta, para que cualquiera pueda ir a verificarlo.
(El campo `osm_version` existe en la salida pero llega vacío: `out geom;` no devuelve
metadatos de edición; para llenarlo habría que pedir `out meta geom;`.) Si en algún momento se consigue la capa del DANE, **reemplaza a esta** y
el módulo queda como respaldo.

### Qué hay y qué no

| Territorio | Qué trae OSM | Nivel | Estado |
| --- | --- | --- | --- |
| Municipio | Polígono | `admin_level=6` | 1 258 km² aprox. |
| Perímetro urbano | Polígono | `admin_level=7` | 30,72 km² |
| Comunas 1 a 7 | Polígono | `admin_level=8` | Las 7, contornos cerrados |
| Corregimientos 08 a 13 | **Solo punto** | nodo `place` | 4 de 6 ubicados |

**Los corregimientos no tienen polígono.** No están cargados como límites
administrativos. Lo que hay es el caserío como nodo, así que la salida es un punto. Un
punto **no sirve** para coropletas ni para densidades, y el archivo lo dice en su propio
campo `advertencia`. `LA FORTUNA AUTOPISTA` y `CIENAGA DEL OPON` no aparecen en OSM ni
como nodo, y quedan sin ubicar: inventarles un polígono habría sido fabricar un dato.

### Una trampa de Overpass que cuesta un día

En Overpass, `out tags;` imprime **solo las etiquetas y suprime los miembros** de la
relación. La consulta `out geom tags;` devuelve los nombres de las comunas pero sin
geometría, y el resultado es una colección vacía de polígonos **sin ningún mensaje de
error**: nueve elementos recibidos, cero polígonos construidos. La forma correcta es
`out geom;`.

Una relación de límite tampoco es un polígono: es una lista de tramos (`way`)
desordenados y con orientación arbitraria que hay que encadenar por extremos
coincidentes. La Comuna 1 son 17 tramos. `ensamblar_anillos()` hace ese encadenado y
**marca el anillo que no logra cerrar** en vez de cerrarlo a la fuerza, porque un contorno
abierto significa que a OSM le faltan tramos y eso hay que verlo, no taparlo.

### Sin librerías geoespaciales

No hay `geopandas`, `shapely` ni `pyproj` en el entorno y no se instalaron. Punto en
polígono por lanzamiento de rayo, centroide por la fórmula del área, área por
proyección equirectangular local, y vecindad por vértices compartidos: todo en Python
puro, unas cuarenta líneas. La salida es GeOJSON estándar, así que el día que haya
`geopandas` la lee sin cambiar nada.

El área es **aproximada**. A 7° de latitud el error de la proyección es de décimas de
porcentaje, suficiente para una densidad de votantes y **no utilizable** como área
catastral.

### Las dos validaciones que hacen creíble la geometría

1. **Las comunas tapizan el casco urbano.** Suman 30,73 km² y el perímetro urbano mide
   30,72 km², dos polígonos que se calcularon por separado. Si el encadenado de anillos
   estuviera mal, esa coincidencia no se daría.
2. **Ningún puesto urbano cae fuera de las siete comunas.** De los puestos que la
   Registraduría ubica en comunas 01 a 07 y que tienen coordenada, los 0 quedan fuera de
   los polígonos. Y los 17 puestos rurales caen fuera, que es justo lo que corresponde.

### Lo que la geometría NO valida

La coincidencia **comuna por comuna** entre OSM y la Registraduría va en **30 de 40
(75 %)**, por debajo del 90 % que se exigía. Las 10 discrepancias están listadas una por
una en `datos/procesados/geografia/verificacion_comuna.csv` y se reparten así:

- **7 son sedes emparejadas con el campus principal.** Las sedes B, C, F, G de un colegio
  están en comunas distintas, pero OSM solo tiene cargado el campus principal, así que
  todas reciben su coordenada. Los puntajes de parecido lo delatan: 0,40 a 0,50.
- **3 son nombres idénticos en comunas distintas** (`SEMINARIO SAN PEDRO CLAVER`,
  `COLEGIO DIVINO NIÑO JESÚS`), con parecido 1,00. Una de las dos fuentes está
  equivocada y desde aquí no se puede saber cuál. **Requieren revisión humana.**

Por eso ese control es de criticidad **media** y no alta: mide el emparejamiento por
nombre tanto como el polígono, y sus fallas son casi todas del primero. El porcentaje se
reporta tal cual, sin ajustar umbrales para que pase.

### Regla de autoridad

**OSM aporta la forma; la Registraduría aporta la clasificación.** Ante un desacuerdo
sobre a qué comuna pertenece un puesto, manda el `cod_comuna` de la Registraduría, que es
el acto administrativo. La geometría de OSM se usa para dibujar, para medir vecindad y
para calcular distancias, nunca para reasignar un puesto de comuna.

El emparejamiento de puesto a punto usa el perímetro urbano como filtro —un puesto urbano
no puede caer en un sitio rural y al revés—, porque hay nombres repetidos entre el casco y
el campo (`Santa Isabel` es un colegio urbano y también una vereda). **No** filtra por
comuna, aunque mejoraría los números, porque eso volvería circular la validación: se
estaría eligiendo el punto para que caiga en la comuna correcta y luego comprobando que
cae en la comuna correcta.

### Coordenadas de puestos: lo que son y lo que no

`datos/geograficos/puestos_votacion.geojson` y
`datos/procesados/geografia/puestos_coordenadas.csv`.

**No son la ubicación certificada de ningún puesto.** Son el resultado de emparejar el
nombre del puesto con equipamientos y centros poblados de OSM. De 106 variantes de nombre
(el mismo puesto se escribe distinto según el año, y la llave `id_puesto` incluye el
nombre), 42 reciben coordenada con parecido alto, 28 quedan como dudosas y 36 sin
coordenada. **Un puesto sin coordenada se queda sin coordenada**: no se le asigna el
centro de su comuna ni nada parecido.

55 puestos comparten punto con otro. La columna `puestos_en_el_mismo_sitio` lo dice. Para
asignar comuna da igual, porque es el mismo lugar; para cualquier análisis que trate los
puestos como puntos distintos, hay que mirar esa columna primero.

### Caché

Overpass es gratuito y limita por uso: a la tercera o cuarta corrida empieza a responder
`429`. El módulo **reutiliza el GeoJSON que ya esté en disco** y solo vuelve a pedirlo con
`python src/geoespacial/osm.py --refrescar`. Los límites administrativos no cambian de un
día para otro; el emparejamiento de puestos sí se puede querer repetir muchas veces.

### Citación obligatoria

> © Colaboradores de OpenStreetMap. Datos disponibles bajo la Open Database License
> (ODbL) 1.0. https://www.openstreetmap.org/copyright
