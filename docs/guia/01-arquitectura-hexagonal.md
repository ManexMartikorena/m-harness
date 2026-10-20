# 01. La arquitectura hexagonal de un agente

Hito 1 (`v0.1.0`). Spec: `docs/specs/hito-1-esqueleto.md`. Diseño:
`docs/DESIGN.md` §3.

## El problema

Un agente es un núcleo pequeño rodeado de muchos exteriores: el modelo (por
red), el disco, la terminal, los servidores MCP y el sandbox. Si el núcleo
llama directamente a cada exterior:
- cambiar de proveedor de modelos obliga a tocar el bucle;
- probar el bucle exige red y un modelo de verdad;
- una regla rota ("el dominio no habla con la red") no la ve nadie hasta que
  hace daño.

## Cómo lo resuelve M-Harness

### 1. Un núcleo y muchos exteriores

*Arquitectura hexagonal (puertos y adaptadores, Alistair Cockburn):* el
núcleo está en el centro y cada contacto con el exterior pasa por una
interfaz.
- *Puerto:* la interfaz que el núcleo necesita ("algo que me dé una respuesta
  del modelo").
- *Adaptador:* la pieza que cumple esa interfaz con una tecnología concreta
  (la API de OpenAI, la de Anthropic o un fake de los tests).

### 2. Cuatro capas y una regla

```
adapters      →  cli (hito 1); modelos, herramientas, disco… (después)
application   →  casos de uso: el bucle del agente
ports         →  interfaces
domain        →  tipos y reglas: mensajes, llamadas a herramientas
```

**La regla:** una capa solo importa las que tiene debajo, y ningún adaptador
importa a otro.

Una regla que depende de que alguien se acuerde acaba rota, así que la
comprueba una máquina. import-linter la lee de `pyproject.toml`:

```toml
[[tool.importlinter.contracts]]
name = "Hexagonal layers"
type = "layers"
containers = ["mharness"]
layers = ["__main__", "bootstrap", "adapters", "application", "ports", "domain"]
exhaustive = true
```

Si `domain` importa un adaptador, `uv run lint-imports` falla:

```
Hexagonal layers BROKEN
- mharness.domain -> mharness.adapters (l.5)
```

import-linter solo mira los imports entre módulos del proyecto. Un test aparte
(`tests/architecture/test_core_imports.py`) mira las librerías externas: el
núcleo solo puede usar la biblioteca estándar y Pydantic. Un `import httpx`
en `domain` es un puerto que alguien se ha saltado.

### 3. La raíz de composición

*Raíz de composición (composition root, Mark Seemann):* el único punto donde
se crean las piezas y se conectan entre sí. En M-Harness es `bootstrap.py`,
y el comando `maha` entra por ahí:

```python
# bootstrap.py (hito 1: todavía no hay nada que cablear)
def main(argv: Sequence[str] | None = None) -> int:
    return cli.run(argv)
```

```toml
[project.scripts]
maha = "mharness.bootstrap:main"
```

**Por qué no entrar directamente por `cli`:** desde el hito 2, `main()` creará
el cliente del modelo y se lo pasará al bucle. Si el comando entrara por el
adaptador, ese cableado acabaría dentro de un adaptador, y los adaptadores
empezarían a conocerse entre sí.

### 4. La base que lo vigila todo

| Pieza | Qué para |
|---|---|
| `uv.lock` | Que dos máquinas instalen versiones distintas |
| ruff | Errores típicos, imports desordenados y formato |
| mypy estricto | Errores de tipos, también en los tests |
| pytest | Que el comportamiento cambie sin querer |
| import-linter | Que se rompan las capas |
| gitleaks (pre-commit y CI) | Que un secreto llegue a un commit |
| CI (Python 3.14 y 3.15) | Que algo funcione solo "en mi máquina" |
| Release al hacer push de un tag | Versiones a mano y sin notas |

Cada hito se apoya en esta base. Por ejemplo, el fake del modelo del hito 2
tendrá que cumplir el mismo `Protocol` que el adaptador real, y mypy lo
comprueba porque también mira los tests.

## En la industria

| Pieza | M-Harness | Alternativas | Cuándo se elegirían |
|---|---|---|---|
| Arquitectura | Hexagonal | Clean Architecture, Onion; capas clásicas | Clean y Onion son parientes, con más capas. Capas clásicas: aplicaciones con un solo exterior (una web y su base de datos) |
| Entorno y dependencias | uv | Poetry, PDM, Hatch; pip + venv | Poetry o PDM: proyectos que ya los usan. pip: sin herramientas extra |
| Lint y formato | ruff | black + flake8 + isort | Proyectos antiguos ya configurados |
| Tipos | mypy | pyright, ty, pyrefly | pyright: integración con VS Code. ty y pyrefly: mucho más rápidos |
| Reglas de arquitectura | import-linter | tach, pytestarch | tach: módulos con interfaz pública declarada. pytestarch: reglas escritas como tests |
| Hooks de git | pre-commit | lefthook, husky | lefthook: repos con varios lenguajes |
| Secretos | gitleaks | trufflehog, detect-secrets | trufflehog: comprueba si la clave sigue viva |
| Releases | `gh` + notas generadas | release-please, semantic-release | Versión y changelog automáticos a partir de commits con formato Conventional Commits |

Los frameworks de agentes (LangChain, Pydantic AI) dan hecha la separación
entre el núcleo y los proveedores. Aquí se escribe a mano para verla (DESIGN
§7.1).
