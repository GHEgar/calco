# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado con
[SemVer](https://semver.org/lang/es/).

## [No publicado]

## [0.2.0] - 2026-10-13

### Agregado

- `calco.classify`: cuantiles, Jenks, intervalos iguales, desviación estándar y cortes manuales,
  `class_of` y `legend`. Puerto de `@ghegar/panal/classify` (commit `411b44b`), probado contra sus
  vectores copiados en `tests/fixtures/classify/`.
- `Choropleth.from_classification`.
- Recetas `Categories` (igualdad por valor, `Other` como `ElseFilter`, regla de nulos), `Line` (uno o
  varios trazos) y `Annotation` (solo etiquetas).
- Lectura de SLD 1.1 / SE 1.1: título y resumen dentro de `Description`.
- Traductor a MapLibre: `strToUpperCase`, `strToLowerCase`, `strSubstring`, `strSubstringStart` y
  `numberFormat` con agrupación de dígitos.
- Pruebas marcadas `geoserver` contra un GeoServer real (`CALCO_GEOSERVER_URL`).

### Cambiado

- Un literal de filtro solo se lee como número si está escrito en forma canónica; `"001"` o `"1e3"`
  quedan como texto.
- La última clase de una coropleta puede ser degenerada (`[x, x]`), como la que produce Jenks.

## [0.1.0] - 2026-10-13

### Agregado

- Modelo genérico del subconjunto SLD 1.0.0 en dataclasses congeladas: capas, `NamedStyle`, `UserStyle`,
  `FeatureTypeStyle`, reglas con filtro, `ElseFilter` y escalas, y símbolos de polígono, línea, punto
  y texto.
- Expresiones `Property`, `Literal` y `Function` para geometrías, etiquetas concatenadas y filtros.
- Filtros `IsNull`, comparaciones, `Between`, `And`, `Or` y `Not`.
- Varios `UserStyle` por capa, con `IsDefault`, como los devuelve `GetStyles`; `recognize` elige por
  nombre o por el estilo por defecto.
- Colores `0xRRGGBB` al leer.
- `parse` y `write`: salida determinista; el lector tolera `SvgParameter` y reporta en `unsupported`
  todo lo que no lee, con su ruta.
- Recetas `Choropleth` (rangos, regla de nulos con fondo y achurado), `Polygon`, `Point` y `Label`, y
  `recognize` para leerlas de vuelta.
- `calco.maplibre`: etiquetas a capas `symbol`, `strip_text` y conversión entre escala y zoom.
