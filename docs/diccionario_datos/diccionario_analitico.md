# Diccionario de los datasets analíticos

`datos/analitico/` · generado por `src/transformacion/construir_datasets.py`

Estos son los datos con los que se analiza. Vienen de `datos/procesados/`, que a su vez
viene de `datos/brutos/`, que **no se modifica nunca**. Para rehacerlos desde cero:

```
python src/transformacion/construir_datasets.py
```

---

## Reglas que cumplen todas las tablas

1. **Nada está imputado.** Un potencial que falta queda vacío; una comuna que falta queda
   vacía. Si una columna tiene un valor, salió de la fuente o de una derivación declarada.
2. **Ningún valor extremo fue borrado ni recortado.** Se marcan en columnas `marca_*`.
3. **Ningún documento de identidad entra a ninguna tabla.** Candidatos y electos sí se
   nombran: son figuras públicas que se presentaron a una elección.
4. **Los códigos están rellenados a un ancho fijo.** `cod_candidato` siempre tiene 5
   caracteres, `cod_partido` 5, `cod_corporacion` 3, `mesa` 4, el resto 2 o 3. Sin esto,
   un `groupby` entre años partiría cada grupo en dos.
5. **Léelas con `keep_default_na=False, na_values=[""]`** si vas a volver a las tablas de
   `datos/procesados/`: ahí la cadena `NULL` y la cadena `N/A` son valores, no vacíos. En
   `datos/analitico/` ya están convertidos a nulo de verdad.

---

## Las dos llaves, y cuál usar

Esto es lo que más fácil se usa mal.

| Llave | Qué identifica | Úsala para |
| --- | --- | --- |
| `id_puesto` | un puesto **dentro de una elección** | unir votos con censo, agregar por puesto en un año |
| `id_panel` | **el mismo lugar físico a lo largo de los años** | comparar un puesto entre 2019, 2022 y 2023 |

**No uses `cod_puesto` para comparar entre años.** Está renumerado: entre 2019 y 2023 hay
14 puestos cuyo código pasó a señalar otro lugar. La zona sí es estable. La evidencia está
en el cuaderno 04 y en `codigos_de_puesto_reusados.csv`.

`id_panel` cubre 60 identidades presentes en más de un año y **52 presentes en los tres**.
Los puestos que no emparejan llevan `en_panel = False`: abrieron o cerraron, y eso es un
dato correcto, no un error.

---

## `puesto_eleccion.csv` — la tabla principal

770 filas × 70 columnas. **Una fila por puesto de votación y elección.**

### Identificación
| Columna | Qué es |
| --- | --- |
| `anio` | 2019, 2022 o 2023 |
| `familia` | `territorial` o `congreso` |
| `corporacion` | ALCALDE, CONCEJO, ASAMBLEA, GOBERNADOR, JAL, SENADO, CAMARA |
| `es_uninominal` | verdadero en Alcaldía y Gobernación: no hay listas ni cifra repartidora |
| `cod_zona`, `cod_puesto`, `puesto` | como vienen de la Registraduría, con ancho normalizado |
| `id_puesto` | llave del puesto dentro de la elección |

### Territorio
| Columna | Qué es |
| --- | --- |
| `cod_comuna` | 01–07 urbano, 08–13 corregimientos, 00 cárcel. Vacío en 6 puestos de 2022 |
| `territorio` | nombre canónico. Las fuentes escriben `CORREG.`, `CORRE.` y `CORREG` para lo mismo |
| `ambito` | `urbano`, `rural` o `especial` |
| `origen_del_ambito` | **de dónde salió el ámbito.** Mira esta columna antes de confiar en la anterior |
| `area_km2` | área aproximada de la comuna, de OpenStreetMap. Solo urbano |
| `densidad_votos_km2` | votos sobre área. Solo urbano |

La **zona 98 es la cárcel**, no un consolidado: un puesto real con 149 electores, censo 96 %
masculino y participación del 37,6 %. La **zona 99** agrupa los puestos rurales; de ahí se
deduce el ámbito rural de los seis puestos de 2022 que llegaron sin comuna, sin inventar
cuál corregimiento es.

### Votación
| Columna | Qué es |
| --- | --- |
| `votos_depositados` | **todos** los votos, incluidos blancos, nulos y no marcados |
| `votos_validos` | candidatos + lista + blanco. **El blanco es válido**: cuenta para la cifra repartidora |
| `votos_no_validos` | nulos + no marcados |
| `votos_a_candidatos` | voto preferente por una persona |
| `votos_de_lista` | voto por el partido sin marcar candidato |
| `votos_blanco`, `votos_nulos`, `votos_no_marcados` | códigos 00996, 00997 y 00998 |
| `candidatos_con_voto` | candidaturas distintas con al menos un voto en ese puesto |
| `listas_con_voto` | listas distintas con al menos un voto |
| `mesas` | mesas de votación en ese puesto |

**Identidad que se verifica en cada corrida:** `votos_validos + votos_no_validos =
votos_depositados`. Si falla, el proceso se detiene.

**`candidatos_con_voto` cuenta el par (lista, orden), no `cod_candidato`.** `cod_candidato`
es el número de orden dentro de su lista y se repite entre listas: contarlo solo daba 17
candidatos al Concejo —el número de curules— cuando son 275 en 2019 y 359 en 2023.

### Censo y participación
| Columna | Qué es |
| --- | --- |
| `potencial_electoral` | electores habilitados en ese puesto para **esa** elección |
| `participacion` | `votos_depositados / potencial_electoral × 100` |
| `abstencion` | 100 − participación |
| `via_del_cruce` | cómo se unió el puesto con su censo: por `id_puesto` o por zona y código |
| `sexo_*`, `edad_*` | composición del censo del puesto |
| `pct_censo_18_a_30`, `pct_censo_mas_de_60`, `pct_censo_mujeres` | derivadas |

Un año puede traer dos elecciones con censos distintos (Congreso y Presidencia). El cruce
exige que coincidan año **y** elección: mezclarlos daría el doble de potencial y la mitad
de participación.

> **Falacia ecológica.** `pct_censo_18_a_30` describe el **censo de un puesto**, no a quienes
> votaron. Que los puestos con censo joven tengan menos participación **no** permite afirmar
> que los jóvenes votan menos: dentro de cada puesto votan personas de todas las edades y no
> se sabe cuáles. La metodología del proyecto lo prohíbe de forma explícita.

### Geografía
| Columna | Qué es |
| --- | --- |
| `lon`, `lat` | **aproximadas**: salen de emparejar el nombre del puesto con sitios de OpenStreetMap |
| `parecido_geocodificacion` | 0 a 1. Por debajo de 0,6 es dudoso |
| `puestos_que_comparten_punto` | cuántos puestos recibieron esa misma coordenada |

No son la ubicación certificada de ningún puesto. 490 de 770 filas tienen coordenada; las
demás quedan vacías, sin asignarles el centro de su comuna ni nada parecido.

### Marcas
Todas booleanas. `marcas_activas` es el conteo. **Ninguna borra ni cambia un valor.**

| Marca | Qué señala |
| --- | --- |
| `marca_participacion_imposible` | participación por encima de 100 % |
| `marca_participacion_muy_baja` | por debajo de 20 % |
| `marca_sin_potencial` | sin censo: la participación no se puede calcular |
| `marca_puesto_pequeno` | menos de 100 votos: las proporciones son inestables |
| `marca_no_validos_altos` | más del 30 % de votos no válidos |
| `marca_ambito_especial` | la cárcel |

Para un agrupamiento o un modelo, `d[d.marcas_activas == 0]` es un punto de partida
razonable —y es una decisión que queda escrita en el análisis, no escondida en los datos.

---

## Las demás tablas

| Archivo | Filas | Qué contiene |
| --- | --- | --- |
| `votos_mesa.csv` | 302 979 | voto por mesa y opción. La tabla más granular |
| `panel_puestos.csv` | 190 | identidad estable del puesto entre años |
| `agregado_eleccion.csv` | 12 | totales del distrito por elección |
| `agregado_territorio.csv` | 164 | totales por comuna y corregimiento |
| `partido_eleccion.csv` | 226 | votos de cada lista, con preferente y de lista por separado |
| `concentracion_eleccion.csv` | 12 | HHI y número efectivo de partidos |
| `volatilidad.csv` | 5 | índice de Pedersen, **con la columna `lectura`** |
| `oferta_electoral.csv` | 12 | listas y candidatos que compitieron |
| `candidato_eleccion.csv` | 2 583 | votos de cada candidatura |
| `concentracion_territorial.csv` | 730 | HHI territorial por candidatura |
| `territorios.csv` | 14 | dimensión de territorios |
| `panel_participacion.csv` | 60 | participación del mismo puesto entre años, formato ancho |
| `matriz_puesto_concejo_AAAA.csv` | 63 / 67 | variables por puesto, listas para agrupar o mapear |
| `apoyo_por_lista_concejo_AAAA.csv` | 63 / 67 | proporción de voto de cada lista por puesto |
| `controles_preparacion.csv` | 13 | los controles y si pasaron |
| `informe_unificacion.csv` | 12 | qué se leyó y qué se transformó en cada elección |
| `informe_panel.csv` | 3 | cuántos puestos emparejaron por año |
| `codigos_de_puesto_reusados.csv` | 179 | **la evidencia de la renumeración** |
| `codigos_de_partido_reusados.csv` | 23 | códigos de partido con más de un nombre |

### Columnas que hay que leer con cuidado

**`volatilidad.lectura`.** El índice de Pedersen mide el cambio en el reparto del voto entre
listas, pero en Colombia las listas cambian de nombre y se recoalicionan entre elecciones.
La columna dice si el número es interpretable:

- **Alcaldía 2019→2023: `NO INTERPRETABLE`.** Cero listas en común. El 100 que aparece es
  aritméticamente correcto y sustantivamente vacío: mide el rebautizo de coaliciones.
- Concejo, Asamblea y Gobernación: `CON CAUTELA`, menos de la mitad del voto está en listas
  presentes en los dos años.
- JAL: `interpretable`, 58 % del voto en listas continuas.

**`partido_eleccion.sin_voto_preferente_observado`.** Lo que se midió es la ausencia de voto
preferente, que **no es lo mismo** que una lista inscrita como cerrada, aunque aquí
coincidan: Pacto Histórico, Nuevo Liberalismo, Comunes y Estamos Listas aparecen en Senado
2022 con cero filas de candidato y cientos de filas de voto de lista.

**`oferta_electoral`** cuenta candidaturas **con votos**, que es un piso de la oferta
inscrita: un candidato que no obtuvo ni un voto no aparece en los resultados por mesa. La
cifra exacta exige el archivo de candidaturas, que todavía no se consigue.

---

## Qué falta

| Pendiente | Qué bloquea |
| --- | --- |
| Candidaturas inscritas | Nombre del electo en lista cerrada y género de los candidatos |
| Serie histórica CEDE | La serie larga 1972–2023 a nivel municipio |
| Presidencia 2018 y 2022 | La comparación nacional completa. El censo ya está |
| Geometría de corregimientos | Mapas de coropleta rurales. OSM solo tiene punto, y dos ni eso |
| Financiación CNE | Descartada: la cobertura real de Cuentas Claras es del 1,1 % |
