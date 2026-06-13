# Predicción Mundial 2026

Probabilidades en vivo del Mundial 2026: quién gana su grupo, quién llega a cada ronda y
quién levanta la copa, recalculadas cada jornada con **simulación Monte Carlo** (20.000
torneos completos) y los resultados reales ya fijados.

Además del panel de probabilidades incluye:

- **Cuadro de eliminatorias**: el árbol oficial de cruces con el ocupante más probable
  de cada casilla y sus alternativas.
- **Modo "¿y si...?"**: fuerza el marcador de cualquier partido pendiente y todo
  (probabilidades, cuadro y caminos) se vuelve a simular al instante en tu navegador.
- **Evolución e historial**: gráfica de la probabilidad de campeón jornada a jornada y
  "viaje en el tiempo" para ver la predicción completa de cualquier día pasado.
- **Cara a cara**: enfrenta a dos selecciones y obtén 1X2, marcadores más probables y
  probabilidad de pasar una eliminatoria.
- **Camino más probable**: pulsa una selección y verás sus rivales más probables en
  cada ronda y con qué frecuencia los supera.

## Ejecutar

```bash
# 0. (opcional, ya hecho) entrenar los ratings propios (necesita numpy)
python engine/train.py

# 1. Generar las probabilidades (escribe docs/data.json)
python engine/simulate.py --sims 20000

# 2. Servir la web
cd docs
python -m http.server
# → abrir http://localhost:8000
```

La simulación y la web no tienen dependencias (Python 3.8+ estándar y un navegador);
solo el entrenamiento (`train.py`) usa numpy.

## Actualización diaria (2 minutos)

1. `python engine/update_results.py` descarga el histórico público y añade solo los
   partidos de grupos ya jugados (nunca toca lo fijado a mano). Si el dataset va con
   retraso, añade el partido manualmente a `data/results.json`:
   ```json
   { "date": "2026-06-13", "home": "CAN", "away": "QAT", "score": [3, 1] }
   ```
   (ids de equipo en `data/teams.json`)
2. `python engine/simulate.py`
3. Recarga la web. Las probabilidades se reordenan solas.

Cada ejecución guarda además la foto del día en `docs/snapshots/` y actualiza la serie
de `docs/history.json`, que alimentan la página de evolución y el viaje en el tiempo.

## Estructura

| Ruta | Qué es |
|---|---|
| `engine/train.py` | **ML**: ratings ataque/defensa por MLE Poisson (Dixon-Coles) con decaimiento temporal, validados walk-forward en WC2018/2022 |
| `engine/model.py` | Modelo de partido: fuerza → goles esperados → Poisson (modo ratings o fallback Elo) |
| `engine/tournament.py` | Reglas 2026: 12 grupos, mejores terceros, cuadro oficial (partidos 73 a 104) |
| `engine/simulate.py` | CLI Monte Carlo: escribe `docs/data.json`, la foto diaria y `docs/history.json` (admite `--snapshot-date` para reconstruir jornadas) |
| `engine/update_results.py` | Vuelca a `results.json` los partidos de grupos ya jugados según el dataset público |
| `docs/` | Dashboard estático (lo que publica GitHub Pages) |
| `docs/evolucion.html` | Gráfica de evolución por jornada y viaje en el tiempo |
| `docs/metodologia.html` | Cuaderno de trabajo navegable: modelo, validación y limitaciones |
| `docs/simulator.js` | El mismo motor en JS para el "¿y si...?" sin servidor |
| `docs/snapshots/`, `docs/history.json` | Predicción guardada de cada día y serie para la gráfica |
| `data/teams.json` | 48 selecciones, grupos del sorteo real, Elo de respaldo |
| `data/ratings.json` | Ratings entrenados (salida de `train.py`) |
| `data/international_results.csv` | Histórico ~49.000 partidos (martj42/international_results) |
| `data/results.json` | Resultados reales del Mundial 2026 (se edita a diario) |

## El modelo (fase 2)

`log λ_local = μ + h·(juega en casa) + ataque_local − defensa_visitante`, ajustado por
máxima verosimilitud Poisson ponderada (decaimiento exponencial half-life 4 años,
amistosos ×0.5, L2) sobre ~11.500 partidos. Hiperparámetros elegidos por validación
walk-forward: entrenando solo con datos previos a cada torneo, el log-loss 1X2 es
0.976 (WC2018) y 1.033 (WC2022) frente a 1.099 del baseline uniforme.

## Hoja de ruta

Siguiente paso: despliegue en GitHub Pages con actualización automática diaria.
Extensión opcional: corrección de λ con xG de StatsBomb.

## Honestidad del modelo

Ningún modelo acierta un Mundial. Los porcentajes cuantifican la incertidumbre, no la
eliminan, y la web siempre muestra cuántas simulaciones y qué resultados reales hay detrás.
