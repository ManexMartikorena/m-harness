# 07. Trazas y coste: lo que pasó y lo que costó

Hito 7 (`v0.7.0`). Spec: `docs/specs/hito-7-trazas-coste.md`. Diseño:
`docs/DESIGN.md` §5, §6 y §11.

## El problema

Hasta el hito 6, `maha` decía cuántos tokens gastaba, pero no cuánto
costaban. Lo que pasaba en una sesión (cada llamada al modelo, cada
herramienta, cuánto tardó, qué se aprobó) se veía en pantalla y se perdía:
no había forma de revisarlo después. Un agente que no se puede auditar no
se puede mejorar, ni evaluar (hito 8).

## Cómo lo resuelve M-Harness

### 1. Una traza no es una sesión

La sesión (nota 06) guarda la conversación, para retomarla. La traza
guarda **lo que pasó**: un registro por evento del bucle, con su hora.

- *Traza:* el registro, en orden, de lo que hizo un programa.

```json
{"at": "2026-10-27T09:36:13Z", "session": "20261027-093613-4f90", "event": {"type": "turn_started", "text": "Repite exactamente: [redacted]"}}
{"at": "2026-10-27T09:36:15Z", "session": "20261027-093613-4f90", "event": {"type": "model_call_finished", "model": "glm-5.3-flash", "usage": {…}, "cost": "0.0002985"}}
{"at": "2026-10-27T09:36:15Z", "session": "20261027-093613-4f90", "event": {"type": "turn_finished", "reason": "end_turn", …}}
```

- Un JSONL por sesión en `~/.local/share/maha/traces/`, con el mismo id.
- **Todo menos los trozos de texto:** serían miles de líneas, y el texto ya
  está en la sesión.
- **Cómo acabó un turno que no acabó bien:** `error` (con el tipo y el
  mensaje) o `interrupted` (cortado antes de acabar).
- **No hay evento `AgentError`:** los errores siguen siendo excepciones; la
  traza los apunta desde fuera del bucle. El `Agent` no sabe que hay traza.
- **Una traza que falla no corta el turno:** se avisa una vez.

```
> /trace
  20261027-101402-1a4f · glm-5.3-flash · 1 turn · 1 model call · 0 tools
  1  11:14:02  1 call · 0 tools · 1249 in · 3 out · $0.0001 · 1.1 s
  total: 1249 in · 3 out · $0.0001
  [trace: ~/.local/share/maha/traces/20261027-101402-1a4f.jsonl]
```

### 2. Tokens: lo que se factura

| Cuenta | Qué es | Se cobra |
|---|---|---|
| entrada | todo el prompt, también la caché | a precio de entrada |
| caché leída | la parte del prompt que el proveedor ya tenía | más barata |
| caché escrita | la parte que guarda para la próxima | según el proveedor |
| salida | lo que escribe el modelo | a precio de salida |
| razonamiento | lo que "piensa" antes de contestar, **dentro** de la salida | como salida |

```
  [tokens: 1275 in · 55 out (44 reasoning) · $0.0186 · session $0.0192]
```

No todos los modelos dicen cuánto razonaron: con OpenCode, DeepSeek y Kimi
casi siempre; GLM, a veces.

### 3. Dos fuentes para el coste

1. **El proveedor**, cuando lo da. OpenCode manda en cada respuesta lo que
   la llamada cuenta contra el límite mensual (`usage.opencode.allowance`).
2. **El catálogo**, cuando no: un TOML con los precios de todos los modelos
   de cada proveedor, con la fecha en que se comprobaron, y el tuyo en
   `~/.config/maha/models.toml`, que manda.

```toml
[models."opencode-go/gpt-6-luna"]
input = 0.10            # USD por millón de tokens
output = 0.50

[[models."opencode-go/gpt-6-luna".tiers]]
above = 272_000         # por encima, toda la llamada a estos precios
input = 0.20
output = 0.75
```

Por qué el proveedor primero, medido en la verificación:

| Modelo | Precio de lista | Cuenta contra el límite de Go |
|---|---|---|
| GLM-5.3-Flash | 1× | 1× |
| DeepSeek V4.1 Flash (valle) | 1× | 0,75× |
| Kimi K3 | 1× | **4×** |

Nada de eso está en la documentación: solo el proveedor lo sabe. El
catálogo sigue siendo útil (proveedores que no dan coste, modelos propios),
y se cruzó con lo que dice OpenCode: el precio de lista coincide al dígito.

- **`Decimal`, nunca `float`:** 41 tokens a 0,003 $ el millón no se redondean
  por el camino. En JSON, como texto: `"0.000000123"`.
- **Sin precio, sin `$`:** nunca un `$0.0000` que parezca gratis. Un coste
  diminuto sale `<$0.0001`; la sesión, `≥$…` si algún turno no tuvo precio.
- **Avisos:** un modelo fuera del catálogo, o que puede entrenar con tus
  datos, se dice al arrancar, con `/model` y al retomar.

### 4. Sin credenciales en la traza

La traza es para auditar, y puede acabar compartida. Antes de escribir un
registro, todo su texto pasa por `mask()`:

- **Valores conocidos:** la clave del proveedor y cada variable cuyo nombre
  parece de credencial (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`),
  también tal como quedan escapados dentro de un JSON.
- **Formas conocidas:** `sk-…`, `ghp_…`, `AKIA…`, `xoxb-…`, claves PEM (aunque
  estén cortadas).

```
sesión: "Repite exactamente: sk-inventada-1234567890"
traza:  "Repite exactamente: [redacted]"
```

La sesión no se enmascara: retomarla necesita el texto real. **El
enmascarado reduce el riesgo, no lo elimina:** un secreto con otra forma
pasa. Por eso la traza es `0600` y local.

### 5. El registro de la aplicación: diagnóstico, nunca contenido

`~/.local/state/maha/maha.log`, para quien mantiene `maha`: fallos del
disco, el `fsync` de una carpeta que falla, errores internos de una
herramienta. Nunca lo que se habló.

```
2026-10-27 11:18:28 WARNING mharness.adapters.storage.sessions: cannot save session 20261027-101826-3b75: cannot create the folder …/sessions: File exists
```

Solo lo escriben los adaptadores (`logging` de la biblioteca estándar); el
dominio y la aplicación hablan con el exterior por puertos.

### 6. Lo que costó dejarlo bien

Tres revisiones independientes del código y la verificación a mano
encontraron 15 fallos, todos arreglados con su test. Tres enseñan algo
general:
- **Un fichero de solo añadir se repara al abrirlo:** si `maha` murió a
  mitad de una línea, la siguiente se pegaba a ella y se perdían las dos.
- **Reservar un nombre es atómico o no es:** el id de una sesión nueva se
  reserva creando su traza en exclusiva (`O_EXCL`), tras comprobar que
  ninguna sesión lo tiene; si está tomado, otro, sin tope.
- **Un `FileExistsError` no siempre es el que crees:** el de `mkdir` se
  tomaba por el de `O_EXCL`, y una carpeta bloqueada parecía un choque de
  ids.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Trazas | JSONL propio por sesión | OpenTelemetry con las convenciones GenAI; Langfuse, LangSmith, Arize Phoenix, Helicone; OpenLLMetry, OpenLIT | Equipos, varios servicios, paneles: el exportador del hito 20 |
| Coste | El del proveedor; si no, tokens × precio en `Decimal` | Solo la tabla de precios (LiteLLM, Langfuse); solo la factura | Proveedores que no dan coste |
| Catálogo | TOML propio con fecha, y el del usuario | models.dev (datos abiertos de OpenCode); `model_prices_and_context_window.json` de LiteLLM | Muchos proveedores; precios siempre al día |
| Secretos en logs | Valores conocidos (también escapados) + formas | Filtros de structlog, detect-secrets, el enmascarado de Langfuse | Volúmenes grandes |
| Registro | `logging` + `RotatingFileHandler` en XDG | structlog, loguru | Logs estructurados de un servicio |

*OpenTelemetry:* un estándar abierto para trazas, métricas y logs. Una
traza se compone de *spans* (un tramo con nombre, inicio y fin: una llamada
al modelo, una herramienta). El hito 20 exporta la traza de `maha` a ese
formato, para verla en Langfuse o Phoenix sin depender de ellos.
