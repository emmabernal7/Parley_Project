# Documentación Exhaustiva: APIs y Scripts del Proyecto SportsQuant

Este documento detalla todas las **APIs (externas e internas)** y los **scripts (ejecutables, CLI y utilitarios)** que componen el proyecto cuantitativo de análisis deportivo y predicción de apuestas **SportsQuant** (`sports-quant-ai-v2`), así como la biblioteca satélite de apoyo (`sports-betting-main`).

---

## 1. Visión General de la Arquitectura

El proyecto está diseñado bajo una arquitectura modular desacoplada:
* **Backend Cuantitativo**: Python 3.10+ con **FastAPI** y **Uvicorn**, respaldado por almacenamiento local persistente en SQLite (`data/sportsquant.db`).
* **Modelos Matemáticos**: Inferencia estadística pura en CPU (Dixon-Coles Poisson bivariado con parámetro $\rho$, desmargenado/de-vig por el método de Shin, Criterio de Kelly Fraccional $0.25 f^*$ y Same-Game Parlays mediante integración de distribución conjunta 2D).
* **Ingesta y Proveedores en Vivo**: Hilos de sondeo en segundo plano (*background worker threads*) que recopilan calendarios, marcadores en vivo, clima, árbitros y cuotas de mercado.
* **Capa Conversacional / Asistente**: Doble modalidad (motor de reglas determinista offline sin dependencias, o agentes LLM con Gemini / Anthropic que ejecutan llamadas a herramientas matemáticas `ToolBox`).
* **Frontend Web**: Aplicación local servida directamente por FastAPI en `http://127.0.0.1:8000` con HTML5/CSS/JavaScript vanilla (cero dependencias de Node.js/npm).

```
                      ┌───────────────────────────────────────────────┐
                      │              FUENTES Y APIS EXTERNAS          │
                      │  • ESPN JSON (Scores, Live, Rosters, Bajas)   │
                      │  • SofaScore (Tiempo real)                    │
                      │  • TheSportsDB (Fixtures & IDs)               │
                      │  • Football-Data.co.uk (Históricos & Odds)    │
                      │  • Open-Meteo (Clima al Kickoff)              │
                      │  • Gemini / Anthropic (LLM Tool Calling)      │
                      │  • X API v2 (Lesiones y Bajas en Redes)       │
                      └───────────────────────┬───────────────────────┘
                                              │
                                              ▼
┌───────────────────────┐            ┌────────────────────────────────┐
│   SCRIPTS Y CLI       │            │       SPORTSQUANT CORE         │
│ • run.py              │            │  • LiveManager (Polling)       │
│ • scripts/ingest.py   │───────────►│  • ModelManager (Dixon-Coles)  │
│ • scratch/test_*.py   │            │  • ToolBox (Math & EV Engine)  │
│ • sportsbet CLI       │            │  • ChatEngine (Offline / LLM)  │
└───────────────────────┘            └────────────────┬───────────────┘
                                                      │
                                                      ▼
                                     ┌────────────────────────────────┐
                                     │      API REST INTERNA (FASTAPI)│
                                     │  • /api/events                 │
                                     │  • /api/event/{id}             │
                                     │  • /api/slip & /api/bets       │
                                     │  • /api/chat & /api/settings   │
                                     └────────────────┬───────────────┘
                                                      │
                                                      ▼
                                     ┌────────────────────────────────┐
                                     │       FRONTEND (BROWSER)       │
                                     │  Dashboard, Bet Slip, Chat UI  │
                                     └────────────────────────────────┘
```

---

## 2. Catálogo de APIs Externas (Consumidas)

El sistema consume múltiples APIs públicas, tanto gratuitas (sin clave) como de servicios avanzados con clave opcional (`.env`).

### 2.1. ESPN Public JSON Endpoints (API Principal en Vivo)
* **Archivo de integración**: `sportsquant/live/providers/espn.py`
* **Naturaleza**: API pública no oficial utilizada internamente por el portal de ESPN. No requiere autenticación contractual.
* **Tolerancia a fallos**: Implementa *fail-soft*; ante errores de red o cambios de esquema devuelve listas vacías y no detiene el motor. Cuenta con URLs primaria y de respaldo:
  - Primaria: `https://site.web.api.espn.com/apis/site/v2/sports`
  - Fallback: `https://site.api.espn.com/apis/site/v2/sports`
* **Endpoints consumidos**:
  1. **Scoreboard & Fixtures**:
     - `GET /{sport}/{league_slug}/scoreboard`
     - `GET /{sport}/{league_slug}/scoreboard?dates=YYYYMMDD`
     - *Datos extraídos*: Marcador actual, reloj de juego (`displayClock`, periodo, cuarto, inning, outs), estadios (`venue`), árbitros/oficiales (`officials`), cuotas iniciales y de cierre del bookmaker de ESPN (`moneyline`, `total_line`).
  2. **Event Summary (Resumen Profundo)**:
     - `GET /{sport}/{league_slug}/summary?event={clean_id}`
     - *Datos extraídos*: Reporte detallado de lesionados y bajas (`injuries`), lanzadores abridores en béisbol (`probables`), alineaciones y entrenadores.
* **Deportes y Ligas Mapeadas**:
  - **Fútbol (Soccer)**: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, Europa League, MLS, Liga MX, Copa Libertadores, etc.
  - **Béisbol (Baseball)**: MLB y ligas invernales caribeñas completas:
    - LVBP (Venezuela: `venezuelan-winter-league`)
    - LIDOM (Rep. Dominicana: `dominican-winter-league`)
    - LMP (México: `mexican-winter-league`)
    - LBPRC (Puerto Rico: `puerto-rican-winter-league`)
    - Serie del Caribe (`caribbean-series`)
    - World Baseball Classic (`world-baseball-classic`)
    - *Nota*: Incluye soporte de "slates" programados y normalización de nombres en español (ej. *Navegantes del Magallanes*, *Tigres del Licey*).
  - **Baloncesto (Basketball)**: NBA, NCAA Men's Basketball, WNBA, EuroLeague, Liga ACB España.
  - **Fútbol Americano (NFL)**: NFL, NCAA Football, CFL, UFL.
  - **Hockey sobre Hielo (Hockey)**: NHL, KHL, Campeonato IIHF.
  - **Tenis**: ATP, WTA, Australian Open, Roland Garros, Wimbledon, US Open.
  - **MMA**: UFC, Bellator, PFL, ONE Championship.
  - **Voleibol**: NCAA Men/Women, FIVB Volleyball Nations League.
  - **Automovilismo**: Formula 1 (`racing/f1`).
  - **Waterpolo**: LEN Champions League, FINA World Championship, Juegos Olímpicos.

---

### 2.2. SofaScore Public API
* **Archivo de integración**: `sportsquant/live/providers/sofascore.py`
* **Base URL**: `https://api.sofascore.com/api/v1`
* **Autenticación**: No requiere API Key. Requiere encabezados HTTP de navegador (`User-Agent`, `Origin`, `Referer: https://www.sofascore.com/`).
* **Endpoints**:
  - `GET /sport/{sport_slug}/events/live`: Lista de todos los partidos activos en tiempo real.
  - `GET /event/{event_id}`: Detalle de evento, tarjetas, goles, cuartos, sets.
* **Propósito**: Canal secundario para verificación de eventos en juego (*inplay*) y actualización en vivo si ESPN no responde.

---

### 2.3. TheSportsDB REST API
* **Archivo de integración**: `sportsquant/live/providers/thesportsdb.py`
* **Base URL**: `https://www.thesportsdb.com/api/v1/json/123` (utiliza clave pública de prueba `123` / `3`).
* **Endpoints**:
  - `GET /eventsday.php?d=YYYY-MM-DD`: Eventos del día por fecha UTC.
  - `GET /eventsnextleague.php?id={league_id}`: Próximos partidos por liga.
  - `GET /eventspastleague.php?id={league_id}`: Resultados recientes por liga.
* **Propósito**: Sincronización de calendarios programados y cruce de identificadores de competiciones internacionales.

---

### 2.4. Football-Data.co.uk (Ingesta Histórica y Cuotas de Mercado)
* **Archivo de integración**: `sportsquant/ingest/footballdata.py`
* **Base URL**: `https://www.football-data.co.uk/mmz4281`
* **Formato**: Archivos CSV descargables estructurados por temporada y división.
* **URL patrón**: `https://www.football-data.co.uk/mmz4281/{season_code}/{division_code}.csv` (ejemplo: `.../2425/E0.csv` para la Premier League 2024-2025).
* **Divisiones soportadas (22 ligas)**:
  - Inglaterra: Premier League (`E0`), Championship (`E1`), League One (`E2`), League Two (`E3`), National League (`EC`).
  - Escocia: Premiership (`SC0`), Championship (`SC1`), League One (`SC2`), League Two (`SC3`).
  - Alemania: Bundesliga (`D1`), 2. Bundesliga (`D2`).
  - España: La Liga (`SP1`), La Liga 2 (`SP2`).
  - Italia: Serie A (`I1`), Serie B (`I2`).
  - Francia: Ligue 1 (`F1`), Ligue 2 (`F2`).
  - Países Bajos: Eredivisie (`N1`).
  - Bélgica: Jupiler Pro League (`B1`).
  - Portugal: Primeira Liga (`P1`).
  - Turquía: Super Lig (`T1`).
  - Grecia: Super League (`G1`).
* **Datos Ingeridos**:
  - Resultados al descanso y tiempo reglamentario (`HTHG`, `HTAG`, `FTHG`, `FTAG`).
  - Estadísticas de partido: Tiros (`HS`, `AS`), tiros a puerta (`HST`, `AST`), faltas (`HF`, `AF`), córners (`HC`, `AC`), tarjetas amarillas y rojas (`HY`, `AY`, `HR`, `AR`).
  - Árbitro designado (`Referee`).
  - Cuotas de casas de apuestas: 1X2 de Pinnacle (`PSH`, `PSD`, `PSA`), Bet365 (`B365H`, `B365D`, `B365A`), William Hill (`WHH`, `WHD`, `WHA`), máximas (`MaxH`) y promedios del mercado (`AvgH`), así como totales Over/Under 2.5 (`P>2.5`, `P<2.5`, `B365>2.5`, `B365<2.5`).

---

### 2.5. Open-Meteo Weather API
* **Archivo de integración**: `sportsquant/live/providers/weather.py`
* **Autenticación**: 100% gratuita, sin API key.
* **Endpoints**:
  1. **Geocodificación**:
     - `https://geocoding-api.open-meteo.com/v1/search?name={city}&count=5`
     - Resuelve la latitud y longitud de la ciudad del estadio donde se disputará el encuentro.
  2. **Predicción Meteorológica Horaria**:
     - `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=UTC&hourly=temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code`
* **Propósito**: Recuperar temperatura, lluvia (mm), velocidad del viento y código WMO exactamente a la hora del kickoff. Permite al modelo ajustar proyecciones ofensivas en deportes al aire libre.

---

### 2.6. The Odds API (Opcional - Mercado en Vivo)
* **Configuración**: Clave configurada en `.env` mediante `THE_ODDS_API_KEY` o `ODDS_API_KEY`.
* **Base URL**: `https://api.the-odds-api.com/v4/sports/{sport_key}/odds`
* **Propósito**: Traer automáticamente las cuotas de casas de apuestas estadounidenses y europeas (DraftKings, FanDuel, BetMGM, Pinnacle) para calcular automáticamente el valor esperado (+EV) y el Closing Line Value (CLV) sin requerir entrada manual del usuario.

---

### 2.7. LLM APIs (Asistente de Chat y Razonamiento)
* **Archivo de integración**: `sportsquant/chat/engine.py`
* **Modo Offline**: Si no se proporciona ninguna clave, opera un analizador determinista con expresiones regulares y gramática que responde consultas sobre equipos, +EV, Kelly y slips.
* **Modo Online**:
  1. **Google Gemini**:
     - Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={GEMINI_API_KEY}`
     - Modelo por defecto: `gemini-2.5-flash`
     - Mecanismo: *Function Calling* / *Tool Declarations*. La API de Gemini recibe las especificaciones de herramientas de `ToolBox` y ejecuta hasta 4 turnos recursivos para responder siempre con números matemáticamente reales calculados por el código.
  2. **Anthropic Claude**:
     - Endpoint: `https://api.anthropic.com/v1/messages`
     - Modelo por defecto: `claude-sonnet-5` (o `claude-3-5-sonnet`)
     - Headers: `x-api-key: {ANTHROPIC_API_KEY}`, `anthropic-version: 2023-06-01`
     - Mecanismo: Tool Use (`type: "tool_use"` y `type: "tool_result"`).

---

### 2.8. Twitter / X API v2 (Extracción de Lesiones y Señales Sociales)
* **Archivo de integración**: `sportsquant/social/extractor.py`
* **Base URL**: `https://api.twitter.com/2`
* **Autenticación**: `X_BEARER_TOKEN` en `.env`.
* **Endpoints**:
  - `GET /users/by/username/{handle}`
  - `GET /users/{id}/tweets?max_results=10&tweet.fields=created_at&exclude=retweets,replies`
* **Propósito**: Monitorear cuentas oficiales de clubes (Tier 1) y periodistas reputados (Tier 2) especificados en `config/accounts_twitter.json` para extraer bajas de último minuto mediante un LLM, bloqueando y descartando de forma estricta cuentas parodia o comentarios no verificados (Tier 3 y Tier 4).

---

## 3. Catálogo de APIs Internas (FastAPI Backend)

El servidor web interno de SportsQuant expone una API REST moderna con validación de esquemas Pydantic y soporte asíncrono.

| Método | Endpoint | Parámetros / Body | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Ninguno | Sirve la interfaz web SPA principal (`index.html`). |
| `GET` | `/static/{file_path}` | Path file | Sirve archivos estáticos (CSS, JS, iconos, logos). |
| `GET` | `/api/settings` | Ninguno | Devuelve la configuración pública actual (banca, keys activas como booleanos, proveedor LLM, etc.). |
| `POST` | `/api/settings` | `SettingsPatch` (`bankroll`, `kelly_fraction`, `value_min_edge`) | Actualiza en caliente parámetros de gestión de banca y umbral de valor. |
| `GET` | `/api/events` | Query: `sport`, `status` (`scheduled`, `live`, `finished`) | Lista todos los eventos cargados en memoria, ordenados por estado y hora de inicio, con su cuota principal precalculada. |
| `POST` | `/api/events/refresh` | Ninguno | Fuerza el refresco concurrente e inmediato contra todos los proveedores configurados. |
| `GET` | `/api/event/{event_id}` | Path: `event_id` | Devuelve el desglose matemático completo de mercados (1X2, Over/Under, Hándicaps Asiáticos, Ambos Marcan, Marcador Exacto, Margen, Props de jugador/lanzador, clima, árbitro). |
| `POST` | `/api/event/{event_id}/odds` | `OddsBody` (`key`, `odds`) | Permite al usuario asociar la cuota ofrecida por su casa de apuestas a una selección específica (vía clic derecho). |
| `GET` | `/api/data-status` | Ninguno | Informa la cantidad de partidos históricos ingeridos por liga en la base de datos local y la fecha del último reajuste de modelos. |
| `GET` | `/api/social/status` | Ninguno | Informa si la integración con Twitter/X está activa y el conteo de cuentas monitoreadas por nivel de confianza. |
| `GET` | `/api/ml/backtest` | Query: `league`, `stake` | Ejecuta un backtest histórico walk-forward (sin sesgo de anticipación) evaluando el ROI de la estrategia Dixon-Coles + Kelly. |
| `POST` | `/api/refit` | Ninguno | Fuerza el re-entrenamiento inmediato de los parámetros de ataque, defensa y ventaja local de los equipos. |
| `POST` | `/api/chat` | `ChatBody` (`session_id`, `message`) | Procesa mensajes en el chat de asesoría cuantitativa (enrutador offline o LLM online con tool-calling). |
| `GET` | `/api/slip` | Query: `session_id` | Obtiene el boleto de apuestas activo y calcula la probabilidad conjunta real y cuota justa correlacionada (SGP). |
| `POST` | `/api/slip/add` | `SlipAdd` (`session_id`, `event_id`, `key`, `odds`) | Agrega una selección deportiva al boleto. |
| `POST` | `/api/slip/remove` | `SlipRemove` (`session_id`, `event_id`, `key`) | Elimina una selección específica del boleto. |
| `POST` | `/api/slip/clear` | `SlipClear` (`session_id`) | Vacía por completo el boleto de apuestas de la sesión. |
| `GET` | `/api/bets` | Query: `status` (`OPEN`, `WON`, `LOST`) | Consulta el historial de apuestas de práctica (*paper bets*) almacenadas en SQLite. |
| `POST` | `/api/bets` | `PlaceBet` (`session_id`, `stake`) | Registra una nueva apuesta de práctica con el stake indicado y deduce el monto de la banca de simulación. |
| `DELETE`| `/api/bets/{bet_id}` | Path: `bet_id` | Cancela o elimina un registro del historial de apuestas de práctica. |

---

## 4. Catálogo y Manual de Scripts del Proyecto

A continuación se detallan los scripts ejecutables disponibles en el repositorio, su propósito, opciones de línea de comandos y ejemplos de uso.

### 4.1. `run.py` — Ejecutor Principal de la Aplicación
* **Ruta**: `sports-quant-ai-v2/run.py`
* **Función**: Punto de entrada de un solo comando para arrancar la plataforma. Configura el `PYTHONPATH`, inicia el servidor Uvicorn en el host y puerto definidos en `config/settings.yaml` (por defecto `127.0.0.1:8000`) y abre automáticamente el navegador web predeterminado.
* **Cómo ejecutarlo**:
  ```bash
  python run.py
  ```
* **Variables que respeta**:
  - `SQ_PORT`: Sobrescribe el puerto HTTP (ej. `SQ_PORT=8080 python run.py`).
  - `SQ_PROVIDERS`: Proveedores activos de datos en vivo (ej. `SQ_PROVIDERS=espn`).

---

### 4.2. `scripts/ingest.py` — Ingesta de Datos Históricos
* **Ruta**: `sports-quant-ai-v2/scripts/ingest.py`
* **Función**: Descarga temporadas reales de fútbol desde `football-data.co.uk`, analiza los CSVs, limpia inconsistencias de nombres de equipos y almacena partidos, marcadores, árbitros, tiros, tarjetas y cuotas históricas de cierre en la base de datos local SQLite (`data/sportsquant.db`).
* **Sintaxis**:
  ```bash
  python scripts/ingest.py [OPCIONES]
  ```
* **Argumentos**:
  - *(Sin argumentos)*: Descarga las **Big 5** ligas europeas (Inglaterra Premier League `E0`, España La Liga `SP1`, Alemania Bundesliga `D1`, Italia Serie A `I1`, Francia Ligue 1 `F1`) para las últimas 3 temporadas.
  - `--all`: Descarga todas las ligas configuradas en `config/leagues.json` que cuenten con código `fd_code` (incluye segunda división inglesa, española, italiana, alemana, francesa, Portugal, Holanda, Bélgica, Turquía, Grecia y Escocia).
  - `--div <D1 D2 ...>`: Especifica una lista explícita de divisiones (ej. `--div E0 SP1 P1`).
  - `--seasons <S1 S2 ...>`: Especifica temporadas en formato `YYYY-YYYY` (ej. `--seasons 2022-2023 2023-2024 2024-2025`).
  - `--years <N>`: Atajo para descargar los últimos $N$ años hasta el actual.
* **Ejemplos**:
  ```bash
  # Ingesta estándar (Big 5, últimas 3 temporadas)
  python scripts/ingest.py

  # Ingesta completa de todas las ligas europeas disponibles
  python scripts/ingest.py --all

  # Ingesta específica de Premier League y La Liga para 2 temporadas
  python scripts/ingest.py --div E0 SP1 --seasons 2023-2024 2024-2025
  ```

---

### 4.3. Scripts de Prueba y Verificación (`scratch/`)

#### A. `scratch/test_caribbean.py`
* **Ruta**: `sports-quant-ai-v2/scratch/test_caribbean.py`
* **Función**: Verifica la conectividad HTTP con los scoreboards de béisbol de ESPN y comprueba el retorno de eventos para las ligas invernales del Caribe (LVBP, LIDOM, LMP, LBPRC, Serie del Caribe y MLB).
* **Cómo ejecutarlo**:
  ```bash
  python scratch/test_caribbean.py
  ```

#### B. `scratch/test_winter_dates.py`
* **Ruta**: `sports-quant-ai-v2/scratch/test_winter_dates.py`
* **Función**: Realiza barridos por fechas (`?dates=YYYYMMDD`) sobre las ligas caribeñas en ESPN para validar la disponibilidad de partidos históricos y programados en los calendarios oficiales.
* **Cómo ejecutarlo**:
  ```bash
  python scratch/test_winter_dates.py
  ```

---

### 4.4. Scripts y CLI de `sports-betting-main` (Módulo Satélite)
En el directorio `d:\Proyecto_Parley\sports-betting-main` reside la biblioteca open source de George Douzas para modelado predictivo scikit-learn con CLI integrada.

* **Puntos de entrada**: `src/sportsbet/cli/_cli.py` y `__main__.py`
* **Comandos CLI disponibles**:
  - `sportsbet dataloaders`: Permite descargar datos tabulares de fuentes públicas (como Football-Data o Kaggle) y transformarlos en matrices de características para entrenamiento.
  - `sportsbet bettor`: Permite entrenar clasificadores / regresores y evaluar estrategias de valor esperado.
  - `sportsbet mcp`: Lanza un servidor MCP (*Model Context Protocol*) para conectar modelos cuantitativos con agentes de IA.
  - `sportsbet execution`: Conduce navegadores web mediante Playwright (`python -m playwright install chromium`) para automatización de apuestas en casas con interfaz web.

---

## 5. Herramientas Matemáticas Expuestas al Chat (`ToolBox`)

El archivo `sportsquant/chat/tools.py` actúa como la API interna entre el asistente conversacional y el motor matemático:

1. **`find_event(query)`**: Busca partidos por nombre de equipo, ciudad o competición utilizando similitud de tokens canónicos.
2. **`event_markets(event_id)`**: Obtiene las cuotas justas, el marcador esperado y la distribución de probabilidades de cualquier partido.
3. **`find_value(sport, min_edge)`**: Escanea todos los mercados donde el usuario ingresó cuotas y devuelve las selecciones con valor esperado positivo ($+EV$).
4. **`price_parlay(legs)`**: Calcula la probabilidad exacta de un boleto combinado. Si las selecciones pertenecen a partidos distintos, multiplica sus probabilidades. Si son del **mismo partido de fútbol**, consulta la **distribución conjunta 2D** $P(H=i, A=j)$ del modelo Dixon-Coles, calculando la correlación real (ej. *Ambos Marcan* y *Más de 2.5 goles*).
5. **`bankroll_stake(model_prob, market_odds)`**: Aplica el Criterio de Kelly Fraccional ($0.25 f^*$) y calcula el stake sugerido en dólares y porcentaje de banca.
6. **`devig_market(odds)`**: Desmargena cuotas de casas de apuestas empleando el algoritmo iterativo de **Shin**, el método aditivo o proporcional.
7. **`analyze_proposition(team, stat_type, line, direction, opponent)`**: Evalúa proposiciones específicas (como carreras anotadas en béisbol o goles en fútbol) proyectando la tasa Poisson del equipo frente a su rival y cruzándola con lanzadores abridores, lesionados y clima.

---

## 6. Variables de Entorno y Configuración (`.env`)

El comportamiento de los scripts y APIs se configura mediante `config/settings.yaml` y el archivo `.env` en la raíz del proyecto. **Ninguna API Key es obligatoria** para que el sistema funcione en su totalidad.

| Variable | Tipo | Por defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `SQ_PORT` | Entero | `8000` | Puerto en el que se ejecuta el servidor web local. |
| `SQ_PROVIDERS` | String | `espn` | Lista de proveedores separados por coma (ej. `espn`). |
| `GEMINI_API_KEY` | String | Vacío | Clave de Google AI Studio para activar el modelo `gemini-2.5-flash` con *Tool Calling*. |
| `ANTHROPIC_API_KEY` | String | Vacío | Clave de Anthropic para activar `claude-sonnet-5`. |
| `SQ_LLM` | String | `auto` | Modo del asistente: `auto`, `gemini`, `anthropic` o `offline`. |
| `THE_ODDS_API_KEY` | String | Vacío | Clave para sincronizar cuotas reales de casas de apuestas globales. |
| `X_BEARER_TOKEN` | String | Vacío | Token Bearer de la API v2 de Twitter para lectura de noticias de alineaciones. |
| `SQ_DB` | Path | `data/sportsquant.db` | Ruta a la base de datos SQLite donde se persisten partidos, cuotas y apuestas. |

---

## 7. Resumen de Flujo de Datos

1. **Ingesta Offline**: Se ejecuta `python scripts/ingest.py` para alimentar `data/sportsquant.db` con cientos de partidos y cuotas históricas.
2. **Arranque**: `python run.py` levanta FastAPI y el navegador en `http://127.0.0.1:8000`.
3. **Hilo de Sondeo en Vivo**: `LiveManager` consulta concurrentemente la API de ESPN (y SofaScore/TheSportsDB) cada pocos segundos para detectar eventos live o programados.
4. **Cálculo Bajo Demanda**: Cuando el usuario selecciona un partido en la UI o en el chat, el motor ajusta la matriz de Dixon-Coles o las tasas de Poisson de inmediato ($\sim 5-25$ ms), calcula cuotas justas sin margen y las proyecta en pantalla.
5. **Apuestas de Práctica**: El usuario añade selecciones a su boleto, analiza la correlación conjunta y registra apuestas con dinero simulado, las cuales se liquidan automáticamente cuando el partido finaliza.
