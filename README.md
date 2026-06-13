# Predicción Mundial 2026

Modelo estadístico que calcula, en vivo, las probabilidades de cada selección en el
Mundial 2026: quién gana su grupo, hasta qué ronda llega y quién levanta la copa.
Las probabilidades se obtienen por **simulación Monte Carlo** (20.000 torneos completos)
sobre un modelo de goles **Poisson** con ratings de ataque/defensa entrenados por máxima
verosimilitud, y se recalculan con los resultados reales según se van jugando.

### [**Ver la web en vivo →**](https://alexsaiz222.github.io/PrediccionMundial2026/)

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Sin dependencias](https://img.shields.io/badge/runtime-sin%20dependencias-success)
![GitHub Pages](https://img.shields.io/badge/deploy-GitHub%20Pages-222?logo=github)

---

## Qué incluye la web

| Sección | Descripción |
|---|---|
| **Panel de probabilidades** | Probabilidad de cada selección de pasar de ronda, llegar a la final y ser campeona, ordenada y recalculada cada jornada. |
| **Cuadro de eliminatorias** | El árbol oficial de cruces (partidos 73–104) con el ocupante más probable de cada casilla y sus alternativas. |
| **Modo «¿y si…?»** | Fuerza el marcador de cualquier partido pendiente y todo —probabilidades, cuadro y caminos— se vuelve a simular al instante **en tu navegador**, sin servidor. |
| **Evolución e historial** | Gráfica de la probabilidad de campeón jornada a jornada y «viaje en el tiempo» para revisar la predicción completa de cualquier día pasado. |
| **Cara a cara** | Enfrenta dos selecciones y obtén el 1X2, los marcadores más probables y la probabilidad de superar una eliminatoria. |
| **Camino más probable** | Pulsa una selección y verás sus rivales más probables en cada ronda y con qué frecuencia los supera. |

---

## El modelo

Cada partido se modela como dos distribuciones de Poisson para los goles de cada equipo,
con medias `λ` determinadas por la fuerza relativa de ataque y defensa:

```
log λ_local    = μ + h·(no es campo neutral) + ataque_local    − defensa_visitante
log λ_visitante = μ                          + ataque_visitante − defensa_local
```

Los parámetros (`μ`, ventaja de localía `h`, y los ratings de ataque/defensa de cada
selección) se ajustan por **máxima verosimilitud Poisson, estilo Dixon-Coles (1997)**,
sobre ~11.500 partidos internacionales reales, con:

- **Decaimiento temporal exponencial** (*half-life* de 4 años): los partidos recientes pesan más.
- **Amistosos ×0.5**: cuentan menos que los partidos de competición.
- **Regularización L2** para evitar sobreajuste a selecciones con pocos partidos.

La optimización se hace con Adam (numpy). Si no hay ratings entrenados, el motor usa un
**fallback basado en Elo** para no quedarse nunca sin predicción.

### Validación honesta (walk-forward)

Para evitar engañarse a uno mismo, el modelo se valida **entrenando solo con datos
anteriores** a cada Mundial y midiendo su acierto sobre ese torneo, que nunca vio:

| Conjunto de prueba | Log-loss 1X2 | Baseline uniforme |
|---|:---:|:---:|
| **WC 2018** | **0.976** | 1.099 |
| **WC 2022** | **1.033** | 1.099 |

Un log-loss menor que el baseline uniforme (1.099) confirma que el modelo aporta
información real, no ruido. El *half-life* del decaimiento se eligió por esta misma
métrica, no a ojo.

---

## Arquitectura

Pipeline de cuatro etapas. El Python solo se ejecuta **offline** para generar los datos;
la web publicada es 100 % estática y no necesita servidor.

```
data/international_results.csv          (histórico, ~49.000 partidos)
        │
        ▼  train.py  ── MLE Poisson + validación walk-forward
data/ratings.json                       (ratings ataque/defensa)
        │
        ▼  simulate.py  ── 20.000 torneos Monte Carlo
docs/data.json + docs/snapshots/ + docs/history.json
        │
        ▼  (GitHub Pages sirve docs/ tal cual)
Web estática (HTML/CSS/JS, sin frameworks)
```

El simulador JS del modo «¿y si…?» reutiliza **exactamente los mismos parámetros**
exportados dentro de `data.json`, así que las simulaciones del navegador coinciden con
las del backend.

---

## Estructura del repositorio

| Ruta | Qué es |
|---|---|
| `engine/train.py` | **ML**: ratings ataque/defensa por MLE Poisson (Dixon-Coles) con decaimiento temporal, validados walk-forward en WC2018/2022. |
| `engine/model.py` | Modelo de partido: fuerza → goles esperados → Poisson (modo ratings o fallback Elo). |
| `engine/tournament.py` | Reglas 2026: 12 grupos, mejores terceros y cuadro oficial (partidos 73–104). |
| `engine/simulate.py` | CLI Monte Carlo: escribe `docs/data.json`, la foto diaria y `docs/history.json` (admite `--snapshot-date` para reconstruir jornadas). |
| `engine/update_results.py` | Vuelca a `results.json` los partidos de grupos ya jugados según el dataset público. |
| `docs/` | Dashboard estático (lo que publica GitHub Pages). |
| `docs/simulator.js` | El mismo motor de simulación en JS para el «¿y si…?» sin servidor. |
| `docs/evolucion.html` · `docs/metodologia.html` | Gráfica de evolución y cuaderno de metodología navegable. |
| `data/teams.json` | 48 selecciones, grupos del sorteo real y Elo de respaldo. |
| `data/ratings.json` | Ratings entrenados (salida de `train.py`). |
| `data/international_results.csv` | Histórico de partidos ([martj42/international_results](https://github.com/martj42/international_results)). |
| `data/results.json` | Resultados reales del Mundial 2026 (se edita según se juega). |

---

## Ejecutar en local

No hace falta instalar nada para la web ni para la simulación (Python 3.8+ estándar y un
navegador). Solo el **entrenamiento** (`train.py`) usa `numpy`.

```bash
# 1. (Opcional, ya hecho) Entrenar los ratings propios
python engine/train.py

# 2. Generar las probabilidades (escribe docs/data.json)
python engine/simulate.py --sims 20000

# 3. Servir la web
cd docs
python -m http.server
# → abrir http://localhost:8000
```

---

## Actualizar los datos cada jornada

```bash
python engine/update_results.py   # baja los partidos ya jugados...
python engine/simulate.py         # ...y recalcula las probabilidades
git add -A && git commit -m "datos: jornada del 2026-06-XX" && git push
```

`update_results.py` solo añade los partidos de grupos ya terminados y **nunca toca** lo
fijado a mano. Si el dataset público va con retraso, basta con añadir el partido a
`data/results.json` (ids de equipo en `data/teams.json`):

```json
{ "date": "2026-06-13", "home": "CAN", "away": "QAT", "score": [3, 1] }
```

Cada ejecución guarda además la foto del día en `docs/snapshots/` y actualiza
`docs/history.json`, que alimentan la página de evolución y el viaje en el tiempo.

---

## Despliegue

La web se publica en **GitHub Pages** sirviendo la carpeta `docs/` de la rama `main`
(*Settings → Pages → Deploy from a branch → `main` / `docs`*). Al ser un sitio estático,
cada `git push` redespliega automáticamente en ~1 minuto. Sin servidores ni costes.

---

## Honestidad del modelo

Ningún modelo acierta un Mundial. Los porcentajes **cuantifican la incertidumbre, no la
eliminan**, y la web siempre muestra cuántas simulaciones y qué resultados reales hay
detrás de cada número. Decisiones deliberadamente simplificadas: el desempate de grupos
omite el head-to-head completo de FIFA (impacto marginal) y no se modela explícitamente
la correlación entre goles más allá de la estructura Poisson/Dixon-Coles.

Extensión natural pendiente: corregir `λ` con datos de *expected goals* (xG).

---

## Créditos

- **Datos históricos**: [Mart Jürisoo — international_results](https://github.com/martj42/international_results).
- **Banderas**: [flagcdn.com](https://flagcdn.com).
- **Autor**: [Alejandro Saiz García](https://www.linkedin.com/in/alejandrosaizgarc%C3%ADa).
