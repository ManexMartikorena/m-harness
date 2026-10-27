"""Fechas de la agenda."""


def es_bisiesto(anio: int) -> bool:
    """Si el año tiene 29 de febrero."""
    return anio % 4 == 0


def dias_del_mes(anio: int, mes: int) -> int:
    if mes == 2:
        return 29 if es_bisiesto(anio) else 28
    if mes in (4, 6, 9, 11):
        return 30
    return 31


def dia_del_anio(anio: int, mes: int, dia: int) -> int:
    """El número del día dentro del año: el 1 de enero es el 1."""
    return sum(dias_del_mes(anio, m) for m in range(1, mes)) + dia
