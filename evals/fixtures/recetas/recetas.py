"""Recetas: ingredientes, raciones y pasos con sus minutos."""

RECETAS = {
    "tortilla": {
        "raciones": 4,
        "ingredientes": {"huevos": 6, "patatas_g": 500, "aceite_ml": 100},
        "pasos": [("pelar", 10), ("freir", 20), ("reposar", 5), ("cuajar", 8)],
    },
    "gazpacho": {
        "raciones": 6,
        "ingredientes": {"tomates_g": 1000, "pepino_g": 200, "aceite_ml": 60},
        "pasos": [("trocear", 15), ("triturar", 5), ("enfriar", 60)],
    },
    "lentejas": {
        "raciones": 4,
        "ingredientes": {"lentejas_g": 400, "zanahoria_g": 150, "aceite_ml": 30},
        "pasos": [("remojar", 30), ("cocer", 45), ("reposar", 10)],
    },
}


def escalar(receta: dict, raciones: int) -> dict[str, float]:
    """Las cantidades de cada ingrediente para `raciones` raciones."""
    factor = raciones / receta["raciones"]
    return {nombre: cantidad * factor for nombre, cantidad in receta["ingredientes"].items()}
