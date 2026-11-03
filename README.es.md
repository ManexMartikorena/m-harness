# maha

**Español** · [English](README.md)

[![CI](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/ManexMartikorena/m-harness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ManexMartikorena/m-harness)](https://github.com/ManexMartikorena/m-harness/releases)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)

**Un agente de IA para la terminal.** Le pides algo en lenguaje natural y
`maha` lee tu código, busca, escribe, edita y ejecuta comandos para
hacerlo, **preguntándote antes de cada cambio**. Funciona con el proveedor y
el modelo que elijas, y te dice en cada turno lo que ha costado.

> 🚧 **En desarrollo: `v0.9.0`.** Ya es usable para trabajar en un
> proyecto: conversar, leer y cambiar ficheros, ejecutar comandos, guardar y
> retomar sesiones y ver el coste, con modelos del formato de OpenAI y con
> Claude; y en scripts, con `maha -p`. Lo que viene, en la [hoja de
> ruta](#hoja-de-ruta).

```
$ maha -m claude-haiku-5-5
maha 0.9.0 · opencode-go · claude-haiku-5-5 · /help for commands
> Lee notas.txt con read_file y dime qué pone, en una frase.
  → read_file(path="notas.txt")
  ✓ 2 lines
El archivo notas.txt contiene solo dos palabras, una por línea: "uno" y "dos".
  [tokens: 4027 in · 87 out · 1 call · $0.0013 · session $0.0013]
> Cambia la segunda línea de notas.txt por 'tres' con edit_file.
  → edit_file(path="notas.txt", old_string="dos", new_string="tres")
  ┌ edit notas.txt
  │ @@ -1,2 +1,2 @@
  │  uno
  │ -dos
  │ +tres
  └ Allow? [y] yes · [a] always this session · [n] no: y
  ✓ 1 replacement
He cambiado la segunda línea de notas.txt: ahora el archivo dice "uno" y "tres".
  [tokens: 4415 in · 204 out (65 reasoning) · 1 call · $0.0007 · session $0.0020]
> /trace
  20261103-154631-4b20 · claude-haiku-5-5 · 2 turns · 4 model calls · 2 tools
  1  16:46:32  2 calls · 1 tool · 4027 in · 87 out · $0.0013 · 3.2 s
  2  16:46:35  2 calls · 1 tool · 4415 in · 204 out · $0.0007 · 3.9 s
  total: 8442 in · 291 out · $0.0020
  [trace: ~/.local/share/maha/traces/20261103-154631-4b20.jsonl]
> /exit
$ maha -c -p "¿Qué pone ahora en notas.txt? Una frase." --allow read_file
  [resumed 20261103-154631-4b20 · 8 messages · claude-haiku-5-5]
  → read_file(path="notas.txt")
  ✓ 2 lines
  [tokens: 4795 in · 85 out · 1 call · $0.0004 · session $0.0024]
El archivo notas.txt ahora contiene "uno" y "tres", una palabra por línea.
```

*(Una sesión real. Los totales son exactos; cada turno se redondea a cuatro
decimales. Con `-p`, por stdout sale solo la respuesta; las líneas entre
corchetes y las llamadas van a stderr. Claude Haiku 5.5 por OpenCode Go:
desde el segundo turno lee la conversación de la caché del prompt, y cada
turno cuesta menos.)*

## Qué hace

- **Trabaja en tu proyecto.** Lee, lista y busca ficheros (`read_file`,
  `list_dir`, `glob`, `grep`; `glob` y `grep` se saltan lo que ignora
  `.gitignore`), los escribe y edita (`write_file`, `edit_file`, con el diff
  a la vista) y ejecuta comandos (`run_command`).
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
  aprobaciones empiezan de cero.
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
uv tool install git+https://github.com/ManexMartikorena/m-harness@v0.9.0
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
del modelo) y topes para cada turno.

```toml
fallback_model = "glm-5.3"
effort = "high"

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
la caché en `.maha/config.toml`, y apretar los topes (nunca aflojarlos),
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
  `--effort NIVEL`, `--max-steps N`, `--max-cost USD`, `--max-tokens N` y `--timeout S`.
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

- **Instrucciones del proyecto** (`AGENTS.md`, `/init`), compactación del
  contexto y **deshacer** cambios.
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
