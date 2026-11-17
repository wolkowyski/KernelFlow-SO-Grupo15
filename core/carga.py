"""Lectura y validacion de los procesos desde un archivo CSV.

Formato: una fila por proceso, ``id,tamanio,tiempo_arribo,tiempo_irrupcion``
(tamanio en KB y tiempos en unidades discretas). Tambien se aceptan ``;`` y
tabulacion como separador (Excel en espanol guarda con ``;``), una fila de
encabezado, lineas vacias y comentarios que empiezan con ``#``.

``cargar_lote`` es tolerante: cada fila con un error se descarta con un aviso
que indica la linea y el motivo, y se simulan los procesos validos. Nunca
corrige ni inventa datos. ``cargar_procesos_desde_csv`` es la version
estricta: ante cualquier problema rechaza el archivo completo.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Union

from core.proceso import ESTADO_NUEVO, Proceso

MAX_PROCESOS = 10
MEMORIA_USUARIO_KB = 450
# Limite de los tiempos para que un valor exagerado (por ejemplo, un arribo
# de 999999999) no deje al simulador avanzando el reloj sin fin.
MAX_TIEMPO = 999
MAX_LARGO_ID = 10
COLUMNAS_ESPERADAS = ("id", "tamanio", "tiempo_arribo", "tiempo_irrupcion")
_PATRON_ENTERO = re.compile(r"[0-9]+")
_PATRON_ID = re.compile(r"[\w.\-]+")  # letras (incluida la n con tilde), numeros, _ . -


class ErrorCargaProcesos(ValueError):
    """Error controlado durante la lectura o validacion del archivo de procesos."""


@dataclass
class ResultadoCarga:
    """Procesos validos del archivo y avisos de las filas descartadas."""

    procesos: List[Proceso]
    avisos: List[str] = field(default_factory=list)
    lineas_leidas: int = 0


def _leer_texto(ruta: Path) -> str:
    try:
        datos = ruta.read_bytes()
    except OSError as exc:
        raise ErrorCargaProcesos(f"No se pudo leer el archivo '{ruta}': {exc}") from exc
    if b"\x00" in datos:
        raise ErrorCargaProcesos(
            f"El archivo '{ruta}' no es un archivo de texto (CSV)."
        )
    for codificacion in ("utf-8-sig", "cp1252"):  # cp1252: CSV de Excel en Windows
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ErrorCargaProcesos(
        f"El archivo '{ruta}' no tiene una codificacion de texto valida."
    )


def _separar(linea: str) -> List[str]:
    """Divide una fila usando la coma, el punto y coma o la tabulacion."""
    separador = "," if "," in linea else ";" if ";" in linea else "\t" if "\t" in linea else ","
    try:
        celdas = next(csv.reader([linea], delimiter=separador))
    except csv.Error:
        celdas = linea.split(separador)
    celdas = [celda.strip() for celda in celdas]
    while celdas and celdas[-1] == "":  # "P1,10,0,2," o columnas vacias de Excel
        celdas.pop()
    return celdas


def _es_encabezado(celdas: Sequence[str]) -> bool:
    return len(celdas) >= 2 and not any(_PATRON_ENTERO.fullmatch(c) for c in celdas[1:])


def _entero(texto: str, nombre: str, minimo: int, maximo: int) -> int:
    if not texto:
        raise ValueError(f"el campo '{nombre}' esta vacio")
    if not _PATRON_ENTERO.fullmatch(texto):
        raise ValueError(
            f"el campo '{nombre}' ('{texto}') debe ser un numero entero sin signo"
        )
    valor = int(texto)
    if not minimo <= valor <= maximo:
        raise ValueError(
            f"el campo '{nombre}' ({valor}) debe estar entre {minimo} y {maximo}"
        )
    return valor


def _validar_fila(celdas: Sequence[str], ids_vistos: set) -> Proceso:
    """Convierte una fila en un Proceso o lanza ValueError con el motivo."""
    if len(celdas) != len(COLUMNAS_ESPERADAS):
        raise ValueError(
            f"se esperaban 4 columnas ({', '.join(COLUMNAS_ESPERADAS)}), "
            f"pero se encontraron {len(celdas)}"
        )
    id_proceso, tamanio_txt, arribo_txt, irrupcion_txt = celdas
    if not id_proceso:
        raise ValueError("el campo 'id' no puede estar vacio")
    if len(id_proceso) > MAX_LARGO_ID or not _PATRON_ID.fullmatch(id_proceso):
        raise ValueError(
            f"el ID '{id_proceso[:20]}' no es valido (hasta {MAX_LARGO_ID} "
            "letras, numeros, '_', '-' o '.', sin espacios)"
        )
    if id_proceso in ids_vistos:
        raise ValueError(f"el ID de proceso '{id_proceso}' esta duplicado")
    tamanio = _entero(tamanio_txt, "tamanio", 1, 10**9)
    if tamanio > MEMORIA_USUARIO_KB:
        raise ValueError(
            f"el proceso '{id_proceso}' requiere {tamanio}K y la memoria de "
            f"usuario tiene {MEMORIA_USUARIO_KB}K: nunca podria cargarse"
        )
    arribo = _entero(arribo_txt, "tiempo_arribo", 0, MAX_TIEMPO)
    irrupcion = _entero(irrupcion_txt, "tiempo_irrupcion", 1, MAX_TIEMPO)
    return Proceso(
        id=id_proceso,
        tamanio=tamanio,
        tiempo_arribo=arribo,
        tiempo_irrupcion=irrupcion,
        estado=ESTADO_NUEVO,
    )


def cargar_lote(ruta_archivo: Union[str, Path, None]) -> ResultadoCarga:
    """Lee el CSV y retorna los procesos validos y los avisos de lo descartado.

    Lanza ErrorCargaProcesos si el archivo no se puede leer o si no tiene
    ningun proceso valido.
    """
    if ruta_archivo is None or str(ruta_archivo).strip() == "":
        raise ErrorCargaProcesos("Debe especificar una ruta de archivo CSV valida.")
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ErrorCargaProcesos(f"No se encontro el archivo '{ruta}'.")
    if not ruta.is_file():
        raise ErrorCargaProcesos(f"La ruta '{ruta}' no corresponde a un archivo.")

    resultado = ResultadoCarga(procesos=[])
    ids_vistos = set()
    primera_fila = True
    for numero_linea, linea in enumerate(_leer_texto(ruta).splitlines(), start=1):
        texto = linea.strip()
        if not texto or texto.startswith("#"):
            continue
        resultado.lineas_leidas += 1
        celdas = _separar(texto)
        if not celdas:
            continue
        if primera_fila and _es_encabezado(celdas):
            primera_fila = False
            resultado.avisos.append(
                f"Linea {numero_linea}: se toma como encabezado y se omite."
            )
            continue
        primera_fila = False
        try:
            proceso = _validar_fila(celdas, ids_vistos)
        except ValueError as error:
            resultado.avisos.append(f"Linea {numero_linea}: {error}. Se descarta.")
            continue
        if len(resultado.procesos) >= MAX_PROCESOS:
            resultado.avisos.append(
                f"Linea {numero_linea}: el proceso '{proceso.id}' supera el maximo "
                f"de {MAX_PROCESOS} procesos que permite la consigna. Se descarta."
            )
            continue
        ids_vistos.add(proceso.id)
        resultado.procesos.append(proceso)

    if not resultado.procesos:
        detalle = (" Problemas encontrados: " + " ".join(resultado.avisos)
                   if resultado.avisos else "")
        raise ErrorCargaProcesos(
            f"El archivo '{ruta}' no tiene ningun proceso valido "
            f"(esta vacio o todas sus filas tienen errores).{detalle}"
        )
    return resultado


def cargar_procesos_desde_csv(ruta_archivo: Union[str, Path, None]) -> List[Proceso]:
    """Version estricta: rechaza el archivo ante el primer problema."""
    resultado = cargar_lote(ruta_archivo)
    problemas = [a for a in resultado.avisos if "encabezado" not in a]
    excedidos = [a for a in problemas if "supera el maximo" in a]
    if excedidos:
        total = len(resultado.procesos) + len(excedidos)
        raise ErrorCargaProcesos(
            f"El archivo contiene {total} procesos, pero el maximo permitido es "
            f"{MAX_PROCESOS}."
        )
    if problemas:
        raise ErrorCargaProcesos(problemas[0])
    return resultado.procesos


cargar_procesos = cargar_procesos_desde_csv


def describir_avisos(resultado: ResultadoCarga) -> Optional[str]:
    """Texto breve para la pantalla cuando se descartaron filas."""
    if not resultado.avisos:
        return None
    return (f"Se cargaron {len(resultado.procesos)} proceso(s) validos. "
            f"Avisos de la carga ({len(resultado.avisos)}):")
