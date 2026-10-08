# Objetivos del Proyecto

## Observatorio de Dinámicas Electorales de Barrancabermeja

### 1. Propósito del proyecto

Desarrollar un proyecto reproducible de ciencia de datos y análisis electoral enfocado en Barrancabermeja, Santander, que permita integrar, depurar, analizar y visualizar información pública electoral, demográfica, territorial y socioeconómica con el fin de comprender la evolución y las dinámicas agregadas del comportamiento electoral del distrito.

El proyecto estará orientado al análisis ciudadano, académico, politico y territorial, utilizando exclusivamente información pública y metodologías estadísticas, matemáticas, geoespaciales y de ciencia de datos.

---

## 2. Objetivo general

Construir un sistema de análisis de datos electorales para Barrancabermeja que integre información histórica y reciente de elecciones nacionales y territoriales, permitiendo identificar patrones, cambios, asociaciones y características territoriales relacionadas con la participación electoral, la abstención, la distribución del voto, la oferta electoral y la evolución del comportamiento electoral agregado.

---

## 3. Objetivos específicos

### 3.1. Construir una base histórica electoral

Recopilar, organizar y estandarizar datos públicos de diferentes procesos electorales con información correspondiente a Barrancabermeja, incluyendo, cuando estén disponibles:

- Elecciones de Presidencia de la República.
- Elecciones de Senado.
- Elecciones de Cámara de Representantes.
- Elecciones de Alcaldía.
- Elecciones de Concejo Distrital.
- Elecciones de Juntas Administradoras Locales.
- Otros procesos electorales o mecanismos de participación que resulten pertinentes.

La base deberá conservar, cuando la fuente lo permita, niveles de desagregación como:

- elección;
- año;
- corporación;
- vuelta electoral;
- departamento;
- municipio;
- zona;
- puesto de votación;
- mesa;
- partido, movimiento, coalición o agrupación;
- candidato;
- votos.

---

### 3.2. Identificar y documentar las fuentes de datos

Construir un catálogo de fuentes oficiales y públicas utilizadas en el proyecto, registrando para cada dataset:

- institución responsable;
- nombre de la fuente;
- URL de origen;
- fecha de descarga;
- elección y año;
- nivel de desagregación;
- formato;
- variables disponibles;
- cobertura territorial;
- observaciones sobre calidad y consistencia;
- naturaleza del resultado, cuando aplique: preconteo, escrutinio u otra fuente.

Las principales fuentes previstas incluyen:

- Registraduría Nacional del Estado Civil;
- Observatorio Electoral de la Registraduría;
- DIVIPOLE;
- Departamento Administrativo Nacional de Estadística — DANE;
- Consejo Nacional Electoral — CNE;
- Cuentas Claras;
- Alcaldía Distrital de Barrancabermeja;
- Misión de Observación Electoral — MOE;
- otras fuentes públicas verificables que resulten pertinentes.

---

### 3.3. Estandarizar la información electoral

Diseñar procesos reproducibles de ingesta, limpieza y transformación que permitan integrar archivos provenientes de diferentes años y elecciones.

Se deberán resolver, entre otros, problemas relacionados con:

- cambios en nombres de columnas;
- cambios de codificación;
- diferencias entre formatos de archivos;
- variaciones en nombres de partidos y movimientos;
- identificación de candidatos;
- diferencias entre elecciones nacionales y territoriales;
- códigos DIVIPOLE y DIVIPOLA;
- datos faltantes;
- duplicados;
- tipos de datos inconsistentes;
- diferencias entre preconteo y escrutinio.

---

### 3.4. Construir una geografía electoral de Barrancabermeja

Relacionar los puestos y zonas de votación con la organización territorial del distrito para construir una dimensión geoespacial que permita analizar resultados por:

- comuna;
- barrio;
- corregimiento;
- zona urbana;
- zona rural;
- puesto de votación;
- otras unidades territoriales disponibles.

Cuando sea posible, se incorporarán coordenadas geográficas y cartografía oficial para permitir análisis y visualizaciones espaciales.

---

### 3.5. Analizar la participación y la abstención electoral

Estudiar la evolución histórica de indicadores como:

- potencial electoral;
- número de sufragantes;
- participación;
- abstención;
- votos válidos;
- votos nulos;
- votos en blanco;
- tarjetas no marcadas;
- cambios de participación entre elecciones;
- diferencias entre elecciones nacionales y territoriales.

El análisis deberá realizarse tanto para el total de Barrancabermeja como para unidades territoriales más pequeñas cuando la información lo permita.

---

### 3.6. Analizar la distribución territorial del voto

Identificar diferencias y similitudes en el comportamiento electoral agregado entre zonas, puestos y mesas de votación.

Se buscará estudiar:

- concentración territorial del voto;
- distribución de votos por candidato;
- distribución de votos por partido;
- diferencias entre zonas urbanas y rurales;
- estabilidad o cambio entre elecciones;
- puestos con comportamientos similares;
- territorios con patrones persistentes a través del tiempo.

---

### 3.7. Analizar la evolución de la oferta electoral

Construir indicadores sobre la cantidad y características de las candidaturas y organizaciones participantes en elecciones territoriales.

Entre las variables de interés se podrán incluir:

- número de candidatos a Alcaldía;
- número de candidatos al Concejo;
- número de listas;
- candidatos por lista;
- partidos y movimientos participantes;
- coaliciones;
- grupos significativos de ciudadanos;
- candidaturas por firmas;
- cambios en la oferta electoral entre elecciones.

---

### 3.8. Medir fragmentación, concentración y competitividad electoral

Aplicar indicadores cuantitativos que permitan caracterizar la estructura de cada elección.

Entre las métricas previstas se encuentran:

- porcentaje de votos;
- margen entre candidatos;
- concentración electoral;
- índice Herfindahl-Hirschman — HHI;
- número efectivo de partidos;
- fragmentación electoral;
- volatilidad electoral;
- concentración territorial;
- dispersión del voto.

La inclusión de cada indicador dependerá de la disponibilidad y calidad de los datos.

---

### 3.9. Integrar variables demográficas y territoriales

Relacionar la información electoral agregada con variables públicas de contexto disponibles para Barrancabermeja.

Podrán estudiarse variables como:

- población;
- sexo;
- grupos de edad;
- densidad poblacional;
- educación;
- vivienda;
- servicios públicos;
- composición de hogares;
- condiciones socioeconómicas;
- características urbanas y rurales;
- crecimiento poblacional;
- otras variables territoriales disponibles.

Estas relaciones deberán interpretarse exclusivamente como asociaciones a nivel agregado.

---

### 3.10. Explorar tipologías territoriales mediante ciencia de datos

Utilizar técnicas estadísticas y de aprendizaje no supervisado para identificar grupos de zonas o puestos con características electorales similares.

Entre las metodologías que podrán evaluarse se encuentran:

- análisis de componentes principales — PCA;
- K-Means;
- clustering jerárquico;
- DBSCAN;
- HDBSCAN;
- reducción de dimensionalidad;
- análisis de similitud y distancia.

El objetivo será identificar patrones estructurales en los datos sin imponer previamente categorías políticas.

---

### 3.11. Realizar análisis espacial

Aplicar técnicas de estadística espacial para estudiar la distribución territorial de indicadores electorales.

Cuando la calidad de la georreferenciación lo permita, podrán utilizarse:

- autocorrelación espacial;
- Moran's I;
- indicadores locales de asociación espacial — LISA;
- Getis-Ord Gi*;
- análisis de vecindad;
- mapas de concentración;
- mapas de cambio electoral.

---

### 3.12. Analizar la relación entre financiación y resultados electorales

Cuando exista información pública suficiente, integrar datos del Consejo Nacional Electoral y Cuentas Claras para estudiar variables como:

- ingresos de campaña;
- gastos de campaña;
- fuentes de financiación;
- gasto total;
- gasto por voto;
- categorías de gasto;
- diferencias entre candidaturas.

Este análisis será de asociación y no deberá interpretarse automáticamente como evidencia causal entre gasto electoral y resultado obtenido.

---

### 3.13. Desarrollar visualizaciones y productos analíticos

Crear productos que permitan comunicar los resultados de manera clara y reproducible, entre ellos:

- gráficos estadísticos;
- mapas electorales;
- tablas comparativas;
- series históricas;
- indicadores;
- dashboards;
- informes analíticos;
- notebooks reproducibles.

---

### 3.14. Construir una arquitectura reproducible

Desarrollar el proyecto bajo una estructura modular que permita:

- conservar los datos originales;
- reproducir todas las transformaciones;
- incorporar nuevas elecciones;
- actualizar datasets;
- reutilizar funciones;
- documentar cada etapa;
- mantener trazabilidad entre fuente, dato procesado y resultado analítico.

---

## 4. Preguntas orientadoras iniciales

El proyecto buscará responder, entre otras, las siguientes preguntas:

1. ¿Cómo ha evolucionado la participación electoral en Barrancabermeja?

2. ¿Existen zonas o puestos con niveles persistentemente altos o bajos de participación?

3. ¿Cómo cambia el comportamiento electoral entre elecciones nacionales y territoriales?

4. ¿Qué tan estable o volátil ha sido la distribución del voto entre elecciones?

5. ¿Existen patrones territoriales persistentes dentro de Barrancabermeja?

6. ¿Cómo ha cambiado la oferta electoral en las últimas elecciones territoriales?

7. ¿Cómo ha evolucionado la fragmentación del voto?

8. ¿Qué diferencias se observan entre zonas urbanas y rurales?

9. ¿Existen grupos de puestos de votación con comportamientos electorales similares?

10. ¿Cómo se relacionan las características demográficas y territoriales agregadas con los indicadores electorales?

11. ¿Cómo ha evolucionado el voto en blanco, el voto nulo y la abstención?

12. ¿Qué cambios pueden observarse entre Congreso, Presidencia y elecciones territoriales?

13. ¿Cómo se distribuye espacialmente el apoyo electoral agregado a diferentes candidaturas o agrupaciones?

14. ¿Qué asociaciones pueden encontrarse entre financiación de campañas y resultados electorales?

15. ¿Qué indicadores permiten caracterizar de manera objetiva las dinámicas electorales del distrito?

---

## 5. Alcance inicial del proyecto

### Cobertura territorial

Barrancabermeja, Santander, Colombia.

### Cobertura temporal inicial

Se priorizarán inicialmente las elecciones para las cuales exista información pública digital suficientemente estructurada, con énfasis en:

- 2015;
- 2018;
- 2019;
- 2022;
- 2023;
- 2026.

La cobertura podrá ampliarse a otros años conforme avance la auditoría de fuentes.

### Unidad mínima de análisis

La unidad de análisis dependerá de la disponibilidad de cada fuente.

Se buscará alcanzar, cuando sea posible:

**municipio → zona → puesto → mesa**

Para análisis territoriales se buscarán equivalencias con:

**comuna → barrio → corregimiento → urbano/rural**

---

## 6. Principios metodológicos

### 6.1. Reproducibilidad

Toda transformación relevante deberá poder ejecutarse nuevamente mediante código.

### 6.2. Trazabilidad

Cada dato procesado deberá conservar referencia a su fuente original.

### 6.3. Conservación de datos brutos

Los archivos originales descargados no deberán modificarse.

### 6.4. Separación entre preconteo y escrutinio

Nunca se deberán mezclar resultados de preconteo y escrutinio sin identificarlos claramente.

### 6.5. Calidad de datos

Antes de cualquier análisis se realizarán validaciones de:

- integridad;
- duplicados;
- consistencia;
- tipos de datos;
- cobertura;
- valores faltantes;
- sumatorias electorales;
- correspondencia territorial.

### 6.6. Interpretación responsable

Una asociación estadística no implica causalidad.

Una anomalía estadística no constituye por sí misma evidencia de irregularidad o fraude.

Los resultados deberán interpretarse en función de las limitaciones de las fuentes y de los métodos utilizados.

### 6.7. Prevención de falacia ecológica

Las características agregadas de una zona no deberán atribuirse automáticamente a las personas que viven o votan allí.

Por ejemplo, una asociación entre proporción de población joven y determinado resultado electoral en un territorio no permite concluir cómo votaron individualmente los jóvenes.

---

## 7. Resultado esperado

El resultado final esperado es una plataforma analítica reproducible que permita estudiar de manera histórica, estadística y geoespacial las dinámicas electorales de Barrancabermeja.

El proyecto deberá permitir que futuras elecciones puedan incorporarse siguiendo el mismo pipeline:

**fuente → datos brutos → auditoría → limpieza → estandarización → integración → análisis → visualización → documentación**

De esta manera, el proyecto podrá evolucionar progresivamente hacia un **Observatorio de Dinámicas Electorales de Barrancabermeja basado en datos públicos**.
