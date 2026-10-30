# 08. Cómo se evalúa un agente

Hito 8 (`v0.8.0`). Spec: `docs/specs/hito-8-evals-no-interactivo.md`.
Diseño: `docs/DESIGN.md` §8, §9 y §14.

## El problema

Hasta el hito 7, cada cambio en el bucle, en las herramientas o en sus
descripciones se juzgaba a ojo: se probaba un par de veces y "parecía ir
bien". Eso no basta con un modelo:

- **No es determinista:** la misma pregunta da respuestas distintas, y una
  prueba que pasa una vez puede fallar la siguiente.
- **Los cambios pequeños tienen efectos grandes:** una frase de más en la
  descripción de `edit_file` cambia cómo edita el modelo en todas las
  tareas.

Además, `maha` solo servía con una persona delante: no se podía usar en un
script, ni ponerle un tope de gasto, y un 429 del proveedor cortaba el
turno.

## Cómo lo resuelve M-Harness

### 1. Una tarea y una comprobación automática

- *Eval:* una tarea que el agente de verdad ejecuta, con una comprobación
  que dice sola si salió bien.

```toml
# evals/tasks/06-arreglar-descuento/task.toml
instruction = "El test de descuentos falla. Arregla el código para que pase, sin tocar el test."
fixture = "tienda"                  # un repo de prueba, con datos inventados
allow = ["write_file", "edit_file"]

[check]                             # todo tiene que cumplirse
command = "PYTHONPATH=src python3 -m unittest -q tests.test_descuentos"
file = "tests/test_descuentos.py"   # y el test, sin tocar
contains = ["self.assertEqual(aplicar_descuento(100, 20), 80)"]
```

- Cada ejecución trabaja en **su copia** del repo de prueba.
- **La comprobación la ejecuta el arnés, no el modelo:** el modelo no
  puede "decir" que pasó.
- Cada tarea se valida antes de usarla: su comprobación tiene que **fallar**
  sobre el repo sin tocar. Si no, la tarea no mide nada.
- Veinte tareas, de "¿qué versión declara `pyproject.toml`?" a "migra las
  notas a JSON". Cinco son en inglés: el producto es multilingüe.

Lo que se mide, por tarea y en total:

| Métrica | Qué es |
|---|---|
| Éxito | Ejecuciones cuya comprobación pasa |
| Pasos | Llamadas al modelo |
| Errores de herramienta | Resultados con error (un `old_string` que no está) |
| Tokens, coste y tiempo | Lo que gastó el turno |

Un 429 o un 5xx que no se recupera es un **error de infraestructura**: no
cuenta como fallo del agente, se informa aparte y se puede repetir.

### 2. Ruido, línea base y regresión

Una pasada es ruido. Por eso:

- **Cinco repeticiones** de cada tarea, con **dos modelos** de familias
  distintas (`glm-5.3-flash` y `kimi-k2.7-code`): un cambio que ayuda a uno
  y perjudica al otro solo se ve con dos.
- *Línea base:* el resultado de la batería en una fecha y con un modelo,
  guardado en el repo (`evals/baselines/`), solo con números.
- *Regresión:* un ⚠ cuando una tarea que pasaba siempre ahora falla, cuando
  baja el éxito total, o cuando el coste o los pasos suben más de un 20 %.

```
glm-5.3-flash · baseline 2026-10-27 (5 runs each)
  task                    pass    steps  tool errors  tokens  cost     time
  06-arreglar-descuento   5/5     5.4    0.0          7732    $0.0007  13.4 s
  20-total-value          3/5     4.2    0.0          7928    $0.0009  13.6 s
  total                   95/100  95%    $0.0666 in all
  ⚠ 20-total-value: passed every time in the baseline, now 3/5
```

**Un ⚠ no decide solo: lo decide una persona,** con los datos. En el PR de
reintentos salieron tres ⚠, pero en las 200 ejecuciones no hubo ni un
reintento: el código nuevo no llegó a actuar y el modelo recibió las mismas
peticiones que antes. Era ruido del modelo, y el mantenedor lo aceptó
dejándolo anotado en la spec.

- *Conjunto de validación:* cuatro de las veinte tareas no se miran al
  ajustar prompts. Si una mejora sube "train" y no "validation", se está
  ajustando al examen (*sobreajuste*).

### 3. Sin persona delante: `maha -p`

- *Modo no interactivo (headless):* el agente recibe una instrucción,
  trabaja y sale con un código. Las evals usan exactamente el mismo camino
  (`run_once()`): miden lo que hace `-p`.

```
$ git diff | maha -p "revisa este diff" > revision.md
  → read_file(path="src/app.py")          (stderr)
  ✓ 120 lines                             (stderr)
```

- **Solo la respuesta en stdout**, para que `x=$(maha -p …)` guarde eso y
  nada más. O `--output-format json` (un objeto al final) y `stream-json`
  (un evento por línea).
- **Lo que llega por stdin es dato, no instrucción:** va debajo, entre
  `<stdin>` y `</stdin>`.
- **El código de salida dice cómo acabó:** 0 bien, 1 error, 2 uso, 3 un tope
  paró el turno (reintentar con más tope), 4 se denegó una llamada
  (reintentar con más permisos).

### 4. Permisos sin persona: `--allow`

Sin nadie a quien preguntar, la regla es la de siempre (nota 05): el modelo
propone y el código decide.

```
maha -p "arregla el test" --allow edit_file
  edit_file src/app.py     → aprobado (dentro del directorio)
  edit_file .github/ci.yml → denegado (ejecuta código)
  run_command "pytest"     → denegado (no está en --allow)
```

- `--allow TOOL` aprueba esa herramienta **solo dentro del directorio**.
- Lo que con persona preguntaría "cada vez" (fuera del directorio, un
  secreto, un fichero que ejecuta código) se deniega **siempre**.
- Los permisos solo llegan por la línea de comandos, nunca por el
  `.maha/config.toml` de un repo ajeno.

### 5. Topes por turno, en código

```toml
[limits]
max_steps = 25      # llamadas al modelo
max_cost = 0.50     # dólares
max_tokens = 400000
timeout = 600       # segundos
```

- Se comprueban **antes de cada llamada**: el turno puede pasarse como
  mucho en una llamada, y lo ejecutado queda en el historial.
- **`max_cost` falla cerrado:** si una llamada no tiene precio, el turno se
  para. Un tope de dinero que no se puede comprobar no es un tope.
- Un proyecto puede apretar los topes del usuario, nunca aflojarlos.

### 6. Reintentos y modelo de respaldo

- *Backoff exponencial:* esperar cada vez el doble antes de reintentar
  (1, 2, 4 s). *Jitter:* un poco de azar en la espera, para que muchos
  clientes no vuelvan a la vez.

```
  [glm-5.3-flash: HTTP 503; retrying in 1 s (1/3)]
  [glm-5.3-flash: HTTP 503; retrying in 2 s (2/3)]
  [glm-5.3-flash: HTTP 503; retrying in 4 s (3/3)]
  [glm-5.3-flash keeps failing (HTTP 503); glm-5.3 goes on]
```

- Se reintenta un 429 o un 5xx **solo antes del primer evento**: una
  respuesta empezada ya se vio, y no se repite.
- Si el proveedor manda `Retry-After`, se respeta (hasta 60 s).
- Un 401 o un 400 no se reintentan: repetirlos no los arregla.
- Con `fallback_model`, el respaldo responde el resto del turno; el
  siguiente vuelve al principal. **Siempre se avisa:** un respaldo
  silencioso escondería un modelo que falla.
- Las evals reintentan, pero sin respaldo: miden el modelo que nombran.

### 7. Lo que se aprendió

- **Medir antes de cambiar:** la batería entró antes que `-p` y los
  reintentos, para que el cambio del bucle se comparara con algo.
- **Un tope de tiempo alrededor de un generador corta a quien lo lee:** el
  plazo va en cada espera del bucle, nunca a través de un `yield`.
- **Un stream que solo manda comentarios** (`: keep-alive`) no avanza:
  ahora se corta a los 120 s sin datos. Lo encontró una eval que se quedó
  cinco minutos parada.
- **`Decimal("0") == False` es verdadero en Python:** `--max-cost 0` se
  tomaba por "no dado". Se encontró revisando el PR, y ahora se comprueba
  por identidad.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Batería de evals | Tareas TOML propias y comprobación por comando | Inspect AI (UK AISI), promptfoo, OpenAI Evals; benchmarks como SWE-bench o Terminal-Bench | Muchas tareas y modelos; comparar con otros agentes |
| Seguimiento | JSON de línea base en el repo | LangSmith, Braintrust, Langfuse (datasets y experimentos) | Equipos, históricos largos, revisión humana |
| Juez | Comprobación determinista | Un modelo como juez (*LLM-as-judge*) | Tareas abiertas sin respuesta comprobable |
| Modo no interactivo | `maha -p` | `claude -p`, `opencode run`, `codex exec` | — (es la convención) |
| Reintentos | A mano en el bucle | `tenacity`, `backoff`; los SDK oficiales reintentan dos veces | Sin necesidad de enseñarlo ni de cambiar de modelo |
| Modelo de respaldo | En el bucle | Pasarelas: LiteLLM Router, OpenRouter | Muchos proveedores a la vez |

*SWE-bench:* un benchmark con issues reales de proyectos de GitHub; el
agente tiene que arreglarlas y pasar los tests del proyecto. Mide lo mismo
que esta batería, a mucha más escala y comparable entre agentes.
