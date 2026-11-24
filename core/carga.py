# =============================================================================
#  carga.py  -  LECTURA Y VALIDACION DEL ARCHIVO CSV
# -----------------------------------------------------------------------------
#  QUE HACE:  Abre el CSV, lo lee linea por linea y convierte cada fila
#             valida en un objeto Proceso. Las filas con errores NO frenan
#             el programa: se descartan con un aviso que dice la LINEA y el
#             MOTIVO, y se simula con las validas. NUNCA corrige ni inventa
#             datos.
#  LO USA:    main.py -> cargar_lote() y describir_avisos() al empezar.
#             (cargar_procesos_desde_csv, la version estricta, la usan los tests.)
#  USA A:     proceso.py (crea los Proceso).
#
#  CUANDO ES ERROR "GRAVE" (no se simula y vuelve al menu):
#    - la ruta esta vacia, no existe o es una carpeta
#    - el archivo no se puede leer o no es texto (ej. una imagen)
#    - no quedo NINGUN proceso valido
#  CUANDO ES SOLO UN AVISO (se descarta la fila y se sigue):
#    - columnas de mas o de menos, letras donde van numeros, negativos,
#      decimales, ID repetido o invalido, mas de 450K, tiempos fuera de
#      rango, o el proceso numero 11 en adelante (maximo 10).
# =============================================================================
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
# >> Libreria estandar para leer CSV. Sabe manejar comillas, por ejemplo
#    "P,1" con una coma adentro.
import re
# >> Expresiones regulares: patrones para validar texto ("solo digitos").
from dataclasses import dataclass, field
from pathlib import Path
# >> Path representa una ruta de archivo y trae metodos como .exists(),
#    .is_file() y .read_bytes(). Funciona igual en Windows y Linux.
from typing import List, Optional, Sequence, Union

from core.proceso import ESTADO_NUEVO, Proceso

# --- Limites de la consigna --------------------------------------------------
MAX_PROCESOS = 10
# >> La consigna permite hasta 10 procesos. Del 11 en adelante se descartan.
MEMORIA_USUARIO_KB = 450
# >> Un proceso de mas de 450K nunca entraria en memoria.
# Limite de los tiempos para que un valor exagerado (por ejemplo, un arribo
# de 999999999) no deje al simulador avanzando el reloj sin fin.
MAX_TIEMPO = 999
MAX_LARGO_ID = 10
COLUMNAS_ESPERADAS = ("id", "tamanio", "tiempo_arribo", "tiempo_irrupcion")
_PATRON_ENTERO = re.compile(r"[0-9]+")
# >> Patron: "uno o mas digitos del 0 al 9". Con fullmatch, el texto ENTERO
#    tiene que ser digitos: acepta "15"; rechaza "-3", "2.5", "+4", "10K".
_PATRON_ID = re.compile(r"[\w.\-]+")  # letras (incluida la n con tilde), numeros, _ . -
# >> \w = letra, numero o guion bajo. Tambien se permiten "." y "-".
#    Un espacio en el medio ("P 1") hace que no coincida -> ID invalido.


class ErrorCargaProcesos(ValueError):
    """Error controlado durante la lectura o validacion del archivo de procesos."""
    # >> Error propio para los casos GRAVES. main.py lo atrapa y muestra
    #    "Error: ..." en vez de cerrarse con un error feo de Python.


@dataclass
class ResultadoCarga:
    """Procesos validos del archivo y avisos de las filas descartadas."""

    procesos: List[Proceso]
    # >> Los procesos validos, en el orden del archivo.
    avisos: List[str] = field(default_factory=list)
    # >> Un texto por cada fila descartada (o encabezado omitido).
    # >> field(default_factory=list): cada ResultadoCarga recibe SU PROPIA
    #    lista vacia. Si se escribiera "= []", todas compartirian la misma
    #    lista (trampa clasica de Python; dataclass ni siquiera lo permite).
    lineas_leidas: int = 0
    # >> Cuantas lineas con contenido se procesaron.


def _leer_texto(ruta: Path) -> str:
    # >> Lee el archivo y lo devuelve como texto.
    try:
        datos = ruta.read_bytes()
        # >> Lee los BYTES crudos (sin interpretar todavia como texto).
    except OSError as exc:
        raise ErrorCargaProcesos(f"No se pudo leer el archivo '{ruta}': {exc}") from exc
        # >> try/except: si falla la lectura (permisos, archivo abierto por
        #    otro programa...), se convierte en nuestro error con un mensaje
        #    claro. "from exc" conserva el error original como causa.
    if b"\x00" in datos:
        raise ErrorCargaProcesos(
            f"El archivo '{ruta}' no es un archivo de texto (CSV)."
        )
        # >> Un byte 0 (NUL) no aparece en archivos de texto pero si en
        #    binarios (imagen, exe, Word...). Asi se detecta "esto no es un CSV".
    for codificacion in ("utf-8-sig", "cp1252"):  # cp1252: CSV de Excel en Windows
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
        # >> Prueba primero UTF-8 (el "-sig" ignora la marca BOM que pone
        #    Excel al principio) y si falla, cp1252 (Windows en espanol).
        #    "continue" = pasar a la siguiente codificacion.
    raise ErrorCargaProcesos(
        f"El archivo '{ruta}' no tiene una codificacion de texto valida."
    )


def _separar(linea: str) -> List[str]:
    """Divide una fila usando la coma, el punto y coma o la tabulacion."""
    separador = "," if "," in linea else ";" if ";" in linea else "\t" if "\t" in linea else ","
    # >> Expresion condicional encadenada. Se lee:
    #    si hay coma -> ","; si no, si hay ";" -> ";"; si no, si hay
    #    tabulacion -> "\t"; si no, "," por defecto.
    try:
        celdas = next(csv.reader([linea], delimiter=separador))
        # >> csv.reader lee la linea respetando comillas; next() toma la
        #    primera (y unica) fila que produce.
    except csv.Error:
        celdas = linea.split(separador)
        # >> Si el modulo csv falla, se corta "a mano" por el separador.
    celdas = [celda.strip() for celda in celdas]
    # >> Le saca los espacios a cada celda: " 60 " -> "60".
    while celdas and celdas[-1] == "":  # "P1,10,0,2," o columnas vacias de Excel
        celdas.pop()
        # >> Saca celdas vacias del FINAL (una coma de mas al final no
        #    deberia contar como una 5ta columna).
    return celdas
    # >> Ej.: "P1, 60, 0, 3"  ->  ["P1", "60", "0", "3"]


def _es_encabezado(celdas: Sequence[str]) -> bool:
    return len(celdas) >= 2 and not any(_PATRON_ENTERO.fullmatch(c) for c in celdas[1:])
    # >> Es encabezado si tiene 2 o mas celdas y NINGUNA de las celdas
    #    despues de la primera es un numero.
    #    "id,tamanio,arribo,irrupcion" -> si.   "P1,60,0,3" -> no.
    # >> Se mira desde la 2da ([1:]) porque el ID ya es texto siempre.


def _entero(texto: str, nombre: str, minimo: int, maximo: int) -> int:
    # >> Convierte un texto a numero entero, validando que este en rango.
    #    Si algo esta mal lanza ValueError con el motivo (que despues se
    #    convierte en el aviso de la linea).
    if not texto:
        raise ValueError(f"el campo '{nombre}' esta vacio")
    if not _PATRON_ENTERO.fullmatch(texto):
        raise ValueError(
            f"el campo '{nombre}' ('{texto}') debe ser un numero entero sin signo"
        )
    valor = int(texto)
    # >> int("60") -> 60. Recien ahora es seguro convertir.
    if not minimo <= valor <= maximo:
        raise ValueError(
            f"el campo '{nombre}' ({valor}) debe estar entre {minimo} y {maximo}"
        )
        # >> "minimo <= valor <= maximo": comparacion encadenada de Python.
    return valor


def _validar_fila(celdas: Sequence[str], ids_vistos: set) -> Proceso:
    """Convierte una fila en un Proceso o lanza ValueError con el motivo."""
    # >> Las validaciones se hacen EN ORDEN; la primera que falla corta y
    #    es el motivo que se muestra.
    if len(celdas) != len(COLUMNAS_ESPERADAS):
        raise ValueError(
            f"se esperaban 4 columnas ({', '.join(COLUMNAS_ESPERADAS)}), "
            f"pero se encontraron {len(celdas)}"
        )
    id_proceso, tamanio_txt, arribo_txt, irrupcion_txt = celdas
    # >> Desempaqueta las 4 celdas en 4 variables (por eso antes se
    #    verifico que sean exactamente 4).
    if not id_proceso:
        raise ValueError("el campo 'id' no puede estar vacio")
    if len(id_proceso) > MAX_LARGO_ID or not _PATRON_ID.fullmatch(id_proceso):
        raise ValueError(
            f"el ID '{id_proceso[:20]}' no es valido (hasta {MAX_LARGO_ID} "
            "letras, numeros, '_', '-' o '.', sin espacios)"
        )
        # >> id_proceso[:20] = los primeros 20 caracteres (por si es enorme,
        #    para no llenar la pantalla).
    if id_proceso in ids_vistos:
        raise ValueError(f"el ID de proceso '{id_proceso}' esta duplicado")
    tamanio = _entero(tamanio_txt, "tamanio", 1, 10**9)
    # >> 10**9 = mil millones (solo para que sea un numero razonable)...
    if tamanio > MEMORIA_USUARIO_KB:
        raise ValueError(
            f"el proceso '{id_proceso}' requiere {tamanio}K y la memoria de "
            f"usuario tiene {MEMORIA_USUARIO_KB}K: nunca podria cargarse"
        )
        # >> ...y aca el control real, con un mensaje mas claro: > 450K.
    arribo = _entero(arribo_txt, "tiempo_arribo", 0, MAX_TIEMPO)
    # >> El arribo puede ser 0.
    irrupcion = _entero(irrupcion_txt, "tiempo_irrupcion", 1, MAX_TIEMPO)
    # >> La irrupcion minima es 1.
    return Proceso(
        id=id_proceso,
        tamanio=tamanio,
        tiempo_arribo=arribo,
        tiempo_irrupcion=irrupcion,
        estado=ESTADO_NUEVO,
    )
    # >> Todo bien: se crea el Proceso (que nace en NUEVO).


def cargar_lote(ruta_archivo: Union[str, Path, None]) -> ResultadoCarga:
    """Lee el CSV y retorna los procesos validos y los avisos de lo descartado.

    Lanza ErrorCargaProcesos si el archivo no se puede leer o si no tiene
    ningun proceso valido.
    """
    # >> FUNCION PRINCIPAL DEL ARCHIVO. La llama main.ejecutar_simulacion().
    # >> ENTRA: la ruta del CSV.  SALE: ResultadoCarga (procesos + avisos).

    # --- 1) Controles de la RUTA (errores graves) ---------------------------
    if ruta_archivo is None or str(ruta_archivo).strip() == "":
        raise ErrorCargaProcesos("Debe especificar una ruta de archivo CSV valida.")
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ErrorCargaProcesos(f"No se encontro el archivo '{ruta}'.")
    if not ruta.is_file():
        raise ErrorCargaProcesos(f"La ruta '{ruta}' no corresponde a un archivo.")
        # >> Por ejemplo, si se pasa una carpeta.

    # --- 2) Recorrer el archivo linea por linea -----------------------------
    resultado = ResultadoCarga(procesos=[])
    ids_vistos = set()
    # >> IDs ya aceptados, para detectar duplicados.
    primera_fila = True
    # >> Solo la PRIMERA fila con contenido puede ser encabezado.
    for numero_linea, linea in enumerate(_leer_texto(ruta).splitlines(), start=1):
        # >> splitlines() corta el texto en lineas.
        # >> enumerate(..., start=1): numera desde 1, igual que el editor,
        #    asi "Linea 7" del aviso coincide con la linea 7 del archivo.
        texto = linea.strip()
        if not texto or texto.startswith("#"):
            continue
            # >> Linea vacia o comentario (#): se saltea sin aviso.
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
            # >> AQUI ESTA LA "TOLERANCIA": el error de UNA fila se convierte
            #    en aviso y se sigue con la siguiente; el programa no se corta.
        if len(resultado.procesos) >= MAX_PROCESOS:
            resultado.avisos.append(
                f"Linea {numero_linea}: el proceso '{proceso.id}' supera el maximo "
                f"de {MAX_PROCESOS} procesos que permite la consigna. Se descarta."
            )
            continue
            # >> Ya hay 10 validos: este se descarta. Se controla DESPUES de
            #    validar, asi una fila con error no "gasta" un lugar de los 10.
        ids_vistos.add(proceso.id)
        resultado.procesos.append(proceso)

    # --- 3) Si no quedo ninguno valido -> error grave ------------------------
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
    # >> No la usa el simulador; la usan los tests. Reutiliza cargar_lote y,
    #    si hubo algun aviso (que no sea el encabezado), rechaza todo.
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
# >> Otro nombre para la misma funcion (alias). Lo usan algunos tests.


def describir_avisos(resultado: ResultadoCarga) -> Optional[str]:
    """Texto breve para la pantalla cuando se descartaron filas."""
    # >> La usa main.py para el titulo antes de listar los avisos:
    #    "Se cargaron 3 proceso(s) validos. Avisos de la carga (13):"
    if not resultado.avisos:
        return None
    return (f"Se cargaron {len(resultado.procesos)} proceso(s) validos. "
            f"Avisos de la carga ({len(resultado.avisos)}):")
