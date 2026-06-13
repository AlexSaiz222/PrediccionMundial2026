# Plan de implementación: ampliación del dashboard de predicciones 2026

Este documento describe las nuevas funcionalidades que enriquecen la experiencia de
usuario y prolongan la utilidad del proyecto a medida que avanza la competición.
Estado: **las cuatro implementadas el 12 de junio de 2026**, antes de la publicación
en GitHub.

---

## Características

### 1. Cuadro de eliminatorias (bracket) ✅
* **Qué es:** árbol visual del torneo en un solo sentido: los 16 dieciseisavos en la
  primera columna, los octavos en la segunda y así hasta converger en la final a la
  derecha. Tarjetas minimalistas (solo bandera, nombre y porcentaje), de modo que en
  escritorio cabe entero sin scroll horizontal.
* **Cómo funciona:** cada casilla muestra la selección que más veces la ocupa en las
  simulaciones, con su probabilidad; el tooltip lista las alternativas. Si una posición
  está garantizada (probabilidad 100 %) se marca como "fijo". En el modo ¿y si...? el
  cuadro se recalcula con los marcadores forzados.
* **Datos:** `engine/tournament.py` acumula los ocupantes de cada lado de cada cruce
  (partidos 73 a 104) durante la simulación; `simulate.py` exporta el campo `ko` de
  `data.json` (top 6 por lado, recortado en el 1 %). `web/simulator.js` replica el mismo
  recuento para el modo hipotético.
* **Render:** `renderBracket()` en `app.js` deriva las columnas recorriendo el bracket
  oficial hacia atrás desde la final, así no hay orden codificado a mano. Las rondas se
  unen con líneas conectoras en CSS (altura de columna fija, los cruces se distribuyen
  con `space-around` y las verticales miden alto/16, alto/8, alto/4 o alto/2 según la
  ronda), el campeón más probable va integrado en la casilla de la final y unas sombras laterales
  (consulta de estado de scroll, con degradación elegante) avisan de que el cuadro
  continúa al hacer scroll horizontal. La portada tiene además un índice lateral fijo
  en pantallas anchas que resalta la sección visible (IntersectionObserver).

### 2. Historial por días y gráfica de evolución ✅
* **Qué es:** página nueva `evolucion.html` con dos piezas:
  * **Gráfica temporal:** probabilidad de campeón de las 8 favoritas tras cada
    actualización diaria (SVG generado a mano, sin dependencias, con tooltips por punto).
  * **Viaje en el tiempo:** selector de fecha que abre `index.html?dia=AAAA-MM-DD` y
    muestra la página completa (grupos, cuadro, tablas) tal como estaba ese día, con un
    aviso y enlace de vuelta a la predicción actual.
* **Datos:** cada ejecución de `simulate.py` guarda una foto completa en
  `web/snapshots/AAAA-MM-DD.json` (se sobrescribe si se ejecuta dos veces el mismo día)
  y actualiza la serie ligera `web/history.json` (fecha, partidos fijados y probabilidad
  de campeón por selección).

### 3. Comparador cara a cara ✅
* **Qué es:** sección en la portada para enfrentar a dos selecciones cualesquiera.
* **Cómo funciona:** cálculo analítico instantáneo (rejilla de Poisson hasta 10 goles,
  sin simulación): probabilidades de victoria, empate y derrota a 90 minutos, goles
  esperados, los 5 marcadores más probables y la probabilidad de pasar una eliminatoria
  (90 minutos, prórroga con lambdas a un tercio y penaltis con la misma inclinación
  `pen_tilt` del motor). Si una de las dos es anfitriona se aplica su ventaja de local
  y se indica.
* **Datos:** usa `Simulator.matchLambdas` (exportado de `simulator.js`) con los mismos
  parámetros publicados en `data.json`; coherencia garantizada con el motor Python.

### 4. Camino más probable por selección ✅
* **Qué es:** al pulsar el nombre de cualquier selección (favoritos, grupos o tabla de
  rondas) se abre un diálogo con su camino: probabilidad de alcanzar cada ronda y sus
  3 rivales más probables en ella, con la frecuencia del cruce (condicionada a jugar la
  ronda) y, en el tooltip, la frecuencia con la que supera ese cruce.
* **Datos:** `tournament.py` acumula cruces y victorias por equipo y ronda; `simulate.py`
  exporta el campo `paths` de `data.json` (top 3 rivales por ronda, recortado en el
  0,5 %). El simulador JS produce la misma estructura, así que el diálogo también
  refleja el modo hipotético.

---

## Contrato de datos (resumen)

```
data.json (nuevo respecto a la fase 2)
  ko:    { "73": [ [[tid, p], ...], [[tid, p], ...] ], ... }   # lados A y B por cruce
  paths: { "ESP": { "r16": [[rival, p_cruce, p_gana], ...], ... }, ... }

web/history.json      { "days": [{ "date", "results", "champion": {tid: p} }] }
web/snapshots/*.json  copia íntegra del data.json de cada día
```

`Simulator.run(data, forced, n)` devuelve ahora `{ probs, ko, paths }` con las mismas
formas (antes devolvía solo `probs`).

## Verificación realizada

* `python engine/simulate.py --sims 20000 --seed 26`: genera `ko` y `paths` coherentes
  (por ejemplo, el partido 73 lo ocupa el 2º del grupo A: Corea 50 %, México 27 %).
* Node: `Simulator.run` con un 0-3 forzado de España ante Uruguay baja su título del
  12,1 % al 10,2 % y recoloca sus rivales de octavos; 10.000 simulaciones en ~0,7 s.
* Servidor local: las tres páginas y todos los recursos (incluidos `history.json` y la
  foto del día) responden 200.

## Mejoras posteriores al plan (13 de junio)

* **Etiquetado por jornada**: cada foto se fecha con la jornada que cierra (la fecha del
  último partido fijado), no con el día de ejecución; la foto de salida es la víspera
  (10 de junio). `simulate.py --snapshot-date` permite reconstruir jornadas pasadas.
* **`engine/update_results.py`**: vuelca a `results.json` los partidos de grupos ya
  jugados desde el dataset público, sin clave de API y sin pisar lo fijado a mano.
* **Calendario en el índice lateral** de la portada: cambia de jornada sin recargar
  (intercambio de datos en sitio con View Transitions, URL actualizada con pushState,
  scroll intacto); franja de jornada de altura constante para comparar sin saltos.
* **Gráfica de evolución rediseñada**: eje ajustado al rango real, curvas suaves,
  paleta apagada, banderas en las etiquetas, foco interactivo (hover destaca, clic
  fija) y animación de dibujado; todo respeta `prefers-reduced-motion`.
* **Metodología en dos capas**: tres desplegables "Para el lector técnico"
  (optimización y gradiente, Brier y baseline de frecuencias, paridad de motores y
  ruido de muestreo) y la sección 9 reescrita como decisiones de diseño.
* Datos siempre frescos: los JSON se piden con `cache: "no-store"`.

## Próximo paso

Publicación en GitHub (Pages + Action diaria que ejecute `update_results.py` y
`simulate.py` y haga commit de `data.json`, la foto del día y `history.json`).
