# maha

**Español** · [English](README.md)

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ManexMartikorena/m-harness)](https://github.com/ManexMartikorena/m-harness/releases)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)

**Un agente de IA para la terminal.** Le pides algo en lenguaje natural y
`maha` lee tu código, busca, escribe, edita y ejecuta comandos para
hacerlo, **preguntándote antes de cada cambio**. Funciona con el proveedor y
el modelo que elijas, y te dice en cada turno lo que ha costado.

> 🚧 **En desarrollo: `v0.10.0`.** Ya es usable para trabajar en un
> proyecto: conversar, leer y cambiar ficheros, ejecutar comandos, seguir el
> `AGENTS.md` del proyecto, guardar y retomar sesiones y ver el coste, con
> modelos del formato de OpenAI y con Claude; y en scripts, con `maha -p`.
> Lo que viene, en la [hoja de ruta](#hoja-de-ruta).

```
$ maha -m claude-haiku-5-5
maha 0.10.0 · opencode-go · claude-haiku-5-5 · /help for commands
> Lee notas.txt con read_file y dime qué pone, en una frase.
  → read_file(path="notas.txt")
  ✓ 2 lines
El archivo `notas.txt` tiene dos líneas: "uno" y "dos".
  [tokens: 8803 in · 82 out · 1 call · $0.0026 · session $0.0026]
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(path="notas.txt", old_string="dos", new_string="tres")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
He cambiado la segunda línea de `notas.txt` por "tres". La primera línea ("uno") no se ha tocado.
  [tokens: 9115 in · 144 out · 1 call · $0.0007 · session $0.0033]
> /trace
  20261110-173406-17e4 · claude-haiku-5-5, glm-5.3-flash · 2 turns · 5 model calls · 2 tools
  1  18:34:06  2 calls · 1 tool · 8803 in (4364 cached) · 82 out · $0.0026 · 1.9 s
  2  18:34:08  2 calls · 1 tool · 9115 in (8927 cached) · 144 out · $0.0007 · 2.3 s
  title by glm-5.3-flash · 102 in · 11 out · <$0.0001
  total: 18020 in (13291 cached) · 237 out · $0.0033
  [trace: ~/.local/share/maha/traces/20261110-173406-17e4.jsonl]
> /exit
$ maha -c -p "¿Qué pone ahora en notas.txt? Una frase." --allow read_file
  [resumed 20261110-173406-17e4 · 8 messages · claude-haiku-5-5]
  → read_file(path="notas.txt")
  ✓ 2 lines
  [tokens: 7845 in · 111 out (29 reasoning) · 1 call · $0.0024 · session $0.0057]
`notas.txt` ahora contiene dos líneas: "uno" y "tres".
```

*(Una sesión real. Los totales son exactos; cada turno se redondea a cuatro
decimales. Con `-p`, por stdout sale solo la respuesta; las líneas entre
corchetes y las llamadas van a stderr. Claude Haiku 5.5 por OpenCode Go:
la mayor parte de cada petición sale de la caché del prompt (`cached` en
`/trace`) y cuesta mucho menos; la línea `title by` es el modelo barato que
tituló la sesión.)*

## Qué hace

- **Trabaja en tu proyecto.** Lee, lista y busca ficheros (`read_file`,
  `list_dir`, `glob`, `grep`; `glob` y `grep` se saltan lo que ignora
  `.gitignore`), los escribe y edita (`write_file`, `edit_file`, con el diff
  a la vista) y ejecuta comandos (`run_command`).
- **Conoce tu proyecto.** Antes de tu primer mensaje, el modelo lee el
  `AGENTS.md` del proyecto (o `CLAUDE.md`, si no lo hay), tu
  `~/.config/maha/AGENTS.md` y dónde trabaja: directorio, raíz git,
  plataforma y fecha. Al arrancar, `maha` dice qué ficheros de
  instrucciones ha cargado, y nunca cambian los permisos. `/init` escribe o
  mejora el `AGENTS.md` del proyecto, y `maha prompt` enseña el system
  prompt entero.

  ```
  > /init los tests se lanzan con unittest, nunca con pytest
    ┌ create AGENTS.md (49 lines)
    └ Allow? [y] yes · [a] always this session · [n] no: y
    [AGENTS.md takes effect in the next session: /new]
  ```
- **Planifica, y pregunta cuando hace falta.** En un trabajo de varios
  cambios, el modelo lleva una lista de tareas que ves avanzar (`☑ ▸ ☐`);
  cuando no puede seguir sin ti, pregunta con opciones, y siempre puedes
  escribir tu propia respuesta.
- **Nada cambia sin tu permiso.** Cada escritura y cada comando te preguntan
  antes, con el diff o el comando: una vez, siempre en esta sesión, o no.
  "Siempre" cubre todas las ediciones siguientes dentro del directorio de
  trabajo, pero solo ese comando exacto; los ficheros que ejecutan código
  solos (`.git`, CI, configuración de editores y agentes, `.venv`,
  `node_modules`, `*.pth`) y los que tienen más de un enlace duro preguntan
  cada vez. Leer fuera del directorio o un fichero secreto también
  pregunta, cada vez, y el modelo no sabe nada de esos ficheros antes de
  que apruebes; un secreto se reconoce por
  el nombre (`.env`, claves, `.ssh`…), no por el contenido. Los comandos
  corren con un tiempo límite, sin terminal (uno que pide algo, como una
  contraseña o un editor, falla al momento) y sin tu clave del proveedor en
  el entorno, pero **con tus permisos: lee el comando antes de
  aprobarlo**.
- **El modelo y el proveedor que quieras.** Habla dos formatos de API, el
  de OpenAI y el de Anthropic, y elige el de cada modelo, también cuando
  cambias con `/model` a mitad de sesión. OpenCode Go y Zen y la API de
  Anthropic vienen configurados, y puedes declarar cualquier servidor
  compatible. Eliges cuánto se esfuerza el modelo con `--effort` o
  `/effort`.
- **Aprovecha la caché del prompt del proveedor.** Con el formato de
  Anthropic, cada paso lee de la caché lo que escribió el anterior: mucho
  más barato que reenviar la conversación entera. Con Claude, el
  razonamiento del modelo se guarda y se le devuelve intacto, como pide
  Anthropic.
- **También en scripts.** `maha -p "…"` hace una instrucción y sale: solo
  la respuesta en stdout, o JSON; lo que le llega por stdin va debajo
  (`git diff | maha -p "revisa este diff"`). Sin nadie a quien preguntar,
  solo se ejecutan las herramientas que permitas con `--allow`, y nunca lo
  que pediría permiso cada vez. Con topes por turno (pasos, dólares, tokens
  y tiempo) y un código de salida que dice cómo acabó.
- **Aguanta un proveedor caído.** Un 429 o un fallo del servidor antes de
  que la respuesta empiece se reintenta solo, hasta tres veces; si sigue
  fallando y tienes un modelo de respaldo, este responde el resto del turno.
  Siempre te lo dice.
- **Sesiones que no se pierden.** Cada conversación se guarda sola, turno a
  turno (también la respuesta que cortas), y se retoma desde cualquier
  directorio, también al arrancar (`maha -c`, `maha -r ID`). Se exportan
  en Markdown o JSON y se importan en otro PC. Al retomar, las
  aprobaciones empiezan de cero. Un modelo barato titula cada sesión tras
  su primer turno; `/rename` le pone el tuyo.
- **Sabes lo que gastas.** Cada turno dice sus tokens y su coste, y la
  sesión lo que lleva: el coste que da el proveedor (con OpenCode Go, lo
  que cuenta contra tu límite mensual) o, si no lo da, el de un catálogo con
  los precios de todos los modelos de OpenCode Go, Zen y Anthropic. `maha
  stats` lo suma por día y por modelo.
- **Todo queda registrado, sin tus secretos.** Cada sesión deja una traza
  de lo que hizo el agente; `/trace` la resume.

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/) (instala también Python 3.14 si
falta).

```
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.10.0
```

Después, elige proveedor y modelo:

```toml
# ~/.config/maha/config.toml
provider = "opencode-go"   # o "opencode-zen"
model = "glm-5.3-flash"
```

y deja la clave en una variable de entorno (la sacas de la consola de
OpenCode, en https://opencode.ai):

```
export OPENCODE_API_KEY=...
maha
```

`maha` trabaja sobre el directorio donde lo abres.

Opcional, en el mismo fichero: un modelo de respaldo, cuánto se esfuerza
el modelo (`effort`: `low`, `medium`, `high`, `xhigh` o `max`; sin él, el
del modelo), el modelo que titula las sesiones, más ficheros de
instrucciones y topes para cada turno.

```toml
fallback_model = "glm-5.3"
effort = "high"
small_model = "glm-5.3-flash"      # títulos; por defecto, el barato del proveedor
instructions = ["CONTRIBUTING.md"] # se añaden al system prompt

[limits]
max_steps = 25       # llamadas al modelo
max_cost = 0.50      # dólares
max_tokens = 400000  # entrada + salida
timeout = 600        # segundos
```

**Qué modelos funcionan hoy:** los que se sirven con el formato Chat
Completions de OpenAI o con la Messages API de Anthropic. En OpenCode Go y
Zen son GLM, Kimi, DeepSeek, MiMo, Claude, MiniMax, Qwen y muchos más. GPT,
Gemini y Grok usan otras APIs que `maha` aún no habla: `maha models` los
marca con `*`, y elegir uno lo dice antes de llamar.

**Claude con tu propia cuenta de Anthropic:** crea una clave en la Claude
Console (https://platform.claude.com/settings/keys) y después:

```
export ANTHROPIC_API_KEY=...
```

```toml
# ~/.config/maha/config.toml
provider = "anthropic"
model = "claude-opus-5-5"
cache_ttl = "1h"   # opcional: la caché del prompt dura una hora (5m por defecto)
```

Pagas por uso en tu cuenta de la Console. La suscripción de Claude (Pro,
Max) no se puede usar: Anthropic no permite su acceso en herramientas de
terceros.

### Otro proveedor

Cualquier servidor con el formato de OpenAI, declarado en tu configuración:

```toml
# ~/.config/maha/config.toml
provider = "local"
model = "el-id-de-tu-modelo"

[providers.local]
base_url = "http://localhost:11434/v1"
# api_key_env = "MI_CLAVE"   # sin ella, no se envía clave
```

Un proyecto puede elegir su proveedor, su modelo, su respaldo, el effort y
la caché en `.maha/config.toml` (se lee desde cualquier carpeta del
proyecto, hasta su raíz git), y apretar los topes (nunca aflojarlos),
pero nunca declarar proveedores: así un repositorio ajeno no puede llevarse
tu clave a otro servidor. Lo que elige un proyecto se dice al arrancar, para
que no pueda subirte el coste sin que lo veas: `[from .maha/config.toml:
effort max, cache 1h]`.

## Uso

| Comando | Qué hace |
|---|---|
| `/help` | Lista los comandos |
| `/model [ID]` | Enseña el modelo, o lo cambia |
| `/effort [NIVEL]` | Enseña o cambia cuánto se esfuerza el modelo; `default` vuelve al del modelo |
| `/sessions` | Las sesiones recientes, de todos los directorios |
| `/resume [ID]` | Retoma una sesión; sin ID, la última de este directorio |
| `/delete ID` | Borra una sesión y su traza |
| `/trace [ID]` | Lo que hizo y costó una sesión, turno a turno |
| `/new` | Una sesión nueva sin salir, con el mismo modelo |
| `/init [TEXTO]` | Escribe o mejora el `AGENTS.md` del proyecto; TEXTO, lo que destacar |
| `/rename [TÍTULO]` | Enseña el título de la sesión, o le pone uno |
| `/export [FICHERO]` | Esta conversación en Markdown; por defecto, `ID.md` |
| `/exit` | Sale (también Ctrl+D) |

- Tras cada respuesta, la línea de tokens dice: tokens de entrada y de
  salida (y, dentro de la salida, los de razonamiento), llamadas a
  herramientas, coste del turno y de la sesión. En `/trace`, "calls" son
  las llamadas al modelo.
- Mientras espera la respuesta, gira un spinner con "maha".
- **Ctrl+C** a mitad de una respuesta la corta y vuelve al prompt; el
  modelo sabe que la cortaste. En el prompt, sale.
- **Sin terminal** (`maha < instrucciones.txt`), todo lo que tiene efecto
  se deniega. Para scripts, mejor `maha -p`.

### Desde la shell

| Comando | Qué hace |
|---|---|
| `maha -p "…"` | Una instrucción y salir; lo de stdin va debajo |
| `maha -c`, `maha -r ID` | Seguir la última sesión de aquí, o una por su id |
| `maha models [--all]` | Los modelos del catálogo, con su formato de API, ventana y precios |
| `maha sessions` | Las sesiones recientes; `sessions delete ID` borra una |
| `maha trace [ID]` | Lo que hizo y costó una sesión; sin id, la última de aquí |
| `maha prompt` | El system prompt que tendría una sesión aquí, sin llamar al modelo |
| `maha stats [--days N]` | Coste y tokens por día y por modelo |
| `maha export ID [--format md\|json]` | Una sesión en Markdown o JSON, a stdout |
| `maha import FICHERO` | Una sesión exportada en JSON, como nueva |

Con `-p`:
- `--output-format text|json|stream-json`: solo la respuesta (por
  defecto; las llamadas y los tokens van a stderr), un objeto JSON al
  final o un evento JSON por línea. En JSON, `session_id` es la sesión
  que se retoma con `-r` (`null` si la ejecución no guardó nada) y
  `trace_id`, lo que enseña `maha trace`, también de una que falló.
- `--allow TOOL` (repetible): esa herramienta se ejecuta sin preguntar
  dentro del directorio. Fuera de él, un secreto o un fichero que ejecuta
  código se deniegan siempre.
- Con `-p` o sin él: `-m ID` (modelo), `--fallback-model ID`,
  `--effort NIVEL`, `--max-steps N`, `--max-cost USD`, `--max-tokens N` y `--timeout S`;
  y para el system prompt, `--append-system-prompt TEXTO`,
  `--append-system-prompt-file FICHERO` (se añaden al final) y
  `--system-prompt-file FICHERO` (tu propia base en lugar de la de maha;
  las instrucciones y el entorno se quedan).
- Código de salida: 0 bien, 1 error (también si el modelo se niega), 2 uso
  incorrecto, 3 un tope paró el turno (también si la respuesta llegó a la
  salida máxima del modelo o la conversación llenó su ventana de
  contexto), 4 se denegó una llamada; con Ctrl+C o una
  señal, 128 + la señal.

```
$ git diff | maha -p "revisa este diff" --output-format json | jq -r .result
```

### Dónde guarda cada cosa

| Qué | Dónde |
|---|---|
| Configuración | `~/.config/maha/config.toml` |
| Precios propios (opcional) | `~/.config/maha/models.toml` |
| Sesiones | `~/.local/share/maha/sessions/` |
| Trazas | `~/.local/share/maha/traces/` |
| Registro de diagnóstico | `~/.local/state/maha/maha.log` |

Todo es local. Las sesiones, las trazas y el registro solo los puede leer
tu usuario. Respeta las variables `XDG_*`.

## Hoja de ruta

`maha` crece hito a hito hasta la versión 1.0. Lo siguiente:

- **Compactación del contexto**, para conversaciones largas, y **deshacer**
  cambios.
- **Skills y comandos propios, memoria entre sesiones, sandbox, modos de
  permiso, subagentes, MCP y hooks.**
- **Web e imágenes.**
- **Una interfaz a pantalla completa**, con menú de comandos y navegación
  sencilla.
- **La 1.0**, instalable para cualquier usuario y con su documentación.

El plan completo, hito a hito: [el proyecto](docs/PROYECTO.md#hoja-de-ruta).

## El proyecto

`maha` se construye desde cero y a la vista: sin frameworks de agentes, cada
pieza en su propio PR, con su spec, sus tests y una nota que explica el
concepto. Si quieres saber cómo funciona un agente por dentro, o construir
el tuyo, empieza por **[cómo se ha hecho](docs/PROYECTO.md)**.

## Licencia

[MIT](LICENSE)
