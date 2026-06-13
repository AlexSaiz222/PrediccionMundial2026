# Plan de implementación — Predicción Mundial 2026

> Web estática + motor Python que estima, vía simulación Monte Carlo, la probabilidad de cada
> selección de ganar su grupo, alcanzar cada ronda y ser campeona del Mundial 2026.
> Los números se recalculan cada día fijando los resultados reales ya jugados.

## Arquitectura

```
data/
  teams.json        # 48 selecciones: grupo, rating Elo, bandera, anfitrión
  results.json      # resultados reales jugados (se edita a diario)
engine/
  model.py          # modelo de partido: Elo → goles esperados → Poisson
  tournament.py     # reglas del torneo: grupos, mejores terceros, cuadro oficial
  simulate.py       # CLI: corre N simulaciones y escribe web/data.json
web/
  index.html        # UI: termómetro, grupos, tabla por rondas, modo "¿y si...?"
  styles.css
  app.js            # render del dashboard
  simulator.js      # el MISMO motor portado a JS → "¿y si...?" instantáneo en el navegador
  data.json         # generado por engine/simulate.py (no editar a mano)
```

**Decisión clave:** el motor existe dos veces a propósito. Python es la fuente de verdad
académica (ahí irá el ML de la fase 2) y genera los números publicados con 20.000–50.000
simulaciones. JS replica el modelo con los mismos parámetros (exportados en `data.json`)
para que el usuario pueda forzar un resultado y ver el cuadro entero reordenarse en su
navegador sin servidor. Esto permite desplegar como sitio 100 % estático (GitHub Pages).

## El modelo de partido (fase 1)

1. Diferencia de Elo `dr = eloA − eloB` (+60 de bonus a anfitriones MEX/USA/CAN).
2. Puntuación esperada Elo `E = 1/(1+10^(−dr/400))`, recortada a [0.12, 0.88].
3. Goles esperados: `λA = 2.8·E`, `λB = 2.8·(1−E)` → dos Poisson independientes.
4. Eliminatorias: si hay empate, prórroga con `λ/3` y si persiste, penaltis con ligera
   inclinación hacia el equipo mejor clasificado.

## Reglas del torneo implementadas (formato 2026, 48 equipos)

- 12 grupos de 4, round-robin. Clasifican 1º, 2º y los 8 mejores terceros.
- Desempate simplificado: puntos → diferencia de goles → goles a favor → azar
  (el head-to-head completo de FIFA se omite; impacto marginal en probabilidades).
- Dieciseisavos según el cuadro oficial (partidos 73–88), incluida la asignación de
  terceros a sus huecos permitidos mediante emparejamiento con backtracking.
- Cuadro completo hasta la final (89–96 octavos, 97–100 cuartos, 101–102 semis, final).

## Fases

### Fase 1 — MVP funcional (esta entrega) ✅
- [x] Datos reales: sorteo de diciembre 2025, Elo aproximado (eloratings.net), resultados del 11-jun.
- [x] Motor Monte Carlo en Python con resultados reales fijados.
- [x] Dashboard: termómetro de favoritos, 12 tarjetas de grupo con barras de probabilidad,
      tabla completa 48×6 rondas con mapa de calor.
- [x] "¿Y si...?": forzar el resultado de cualquier partido de grupos pendiente y
      re-simular 10.000 veces en el navegador.
- [x] Flujo de actualización diaria: editar `data/results.json` → `python engine/simulate.py`.

### Fase 2 — Ratings propios con ML (la parte académica) ✅
- [x] Dataset: histórico completo de partidos internacionales
      (github.com/martj42/international_results, ~49.000 partidos, actualizado a 2026)
      descargado en `data/international_results.csv`.
- [x] Modelo: `engine/train.py` ajusta ataque/defensa por equipo + ventaja de local
      maximizando la log-verosimilitud Poisson (estilo Dixon-Coles) con decaimiento
      temporal exponencial y regularización L2, vía Adam (numpy).
      `log λ_home = μ + h·local + att_home − def_away`.
- [x] Validación walk-forward honesta: entrenando solo con datos previos a cada torneo,
      log-loss 1X2 en WC2018 = 0.976 y WC2022 = 1.033 (baseline uniforme: 1.099).
      Los hiperparámetros (half-life del decaimiento y L2) se eligen en esa rejilla:
      ganó half-life=4 años, L2=1.0.
- [x] Integración sin tocar el motor: `simulate.py` detecta `data/ratings.json` y cambia
      `model.py` a modo "ratings"; la ventaja de local entrenada (h=0.255) sustituye al
      bonus Elo de los anfitriones. El simulador JS replica el modo (paridad verificada).
- Limitaciones documentadas: doble Poisson independiente (sin corrección rho de empates),
  desequilibrio entre confederaciones solo corregido por los cruces reales del dataset.
- Extensión opcional (fase 2.5, no bloqueante): corregir los λ con features de xG de
  StatsBomb open-data (gradient boosting). Requiere descargar ~400 MB de eventos;
  el contrato `match_lambdas()` lo permite sin cambios estructurales.

### Fase 2.6 — Rediseño profesional ✅
- [x] Tema claro editorial (estilo FiveThirtyEight): tipografía cuidada, sin emojis,
      tarjetas blancas con bordes finos, mapa de calor sobrio, navegación superior.
- [x] `web/metodologia.html`: cuaderno de trabajo navegable con el modelo, las fórmulas,
      la tabla de validación walk-forward completa y las limitaciones. El README de
      GitHub queda como ficha técnica; la página, como explicación divulgativa.

### Fase 2.7 — Ampliación pre-publicación ✅ (ver implementation_plan.md)
- [x] Cuadro de eliminatorias con conectores, ocupantes probables por casilla y
      reacción al modo hipotético.
- [x] Página de evolución: gráfica de P(campeón) por jornada + viaje en el tiempo
      (snapshot diario completo en `web/snapshots/`, serie en `web/history.json`).
- [x] Cara a cara analítico (1X2, marcadores probables, paso de eliminatoria).
- [x] Camino más probable por selección (diálogo al pulsar cualquier nombre).
- [x] Índice lateral con sección activa y tabla de rondas plegada a 24 con desplegable.

### Fase 3 — Despliegue
- Despliegue en GitHub Pages (es estático: subir `web/` tal cual).
- Actualización diaria automatizable (GitHub Action que ejecuta simulate.py con los
  resultados nuevos y hace commit de data.json, el snapshot e history.json).
- Extra pendiente: compartir un what-if por URL.

## Actualización diaria (manual, 2 minutos)

1. Añadir los partidos del día a `data/results.json`.
2. `python engine/simulate.py --sims 20000`
3. Recargar la web (o hacer push si está desplegada).

## Honestidad del modelo

La web muestra siempre el nº de simulaciones y la fecha de actualización, y los
porcentajes nunca se presentan como certezas. Ningún modelo acierta un Mundial;
el valor está en cuantificar la incertidumbre y verla moverse con cada jornada.
