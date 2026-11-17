"""KernelFlow - nucleo del simulador (TPI Sistemas Operativos, UTN FRRe).

Este archivo contiene el TPI completo en su version base, sin decoracion:

    1. Modelo de proceso y estados
    2. Lectura y validacion del CSV
    3. Memoria MVT con Best-Fit (100K para el SO + 450K de usuario)
    4. Admision, colas y grado de multiprogramacion 5
    5. Planificacion SRTF apropiativa
    6. Informe estadistico (retorno, espera, respuesta y rendimiento)
    7. Salida de texto por consola
    8. Menu y ejecucion de la simulacion

Se ejecuta solo, sin librerias externas:

    python3 core.py                    (menu)
    python3 core.py data/lote.csv      (simula ese archivo)

``interfaz.py`` importa este modulo y agrega la presentacion con colores,
tablas con bordes, graficos, diagrama de Gantt y exportacion. Toda la logica
de la simulacion esta aca; la interfaz solo la muestra.
"""

import argparse
import csv
from dataclasses import dataclass, field
from itertools import zip_longest
import os
from pathlib import Path
import shutil
import sys
import textwrap
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, Union


# ============================================================================
# 1. MODELO DE PROCESO
# Modelo de dominio para los procesos del simulador.
# ============================================================================

ESTADO_NUEVO = "NUEVO"
ESTADO_LISTO = "LISTO"
ESTADO_LISTO_SUSPENDIDO = "LISTO_SUSPENDIDO"
ESTADO_EJECUCION = "EJECUCION"
ESTADO_TERMINADO = "TERMINADO"

ESTADOS_VALIDOS = (
    ESTADO_NUEVO,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_EJECUCION,
    ESTADO_TERMINADO,
)


def _es_entero(valor: object) -> bool:
    """Verifica que el valor sea un entero puro (excluyendo booleanos)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


@dataclass
class Proceso:
    """Representa un proceso dentro de la simulacion.

    Atributos requeridos por el contrato tecnico:
        id: Identificador unico del proceso.
        tamanio: Tamanio de memoria requerido por el proceso (en KB).
        tiempo_arribo: Instante discreto de llegada al sistema.
        tiempo_irrupcion: Duracion total de rafaga de CPU requerida.
        tiempo_restante: Unidades de CPU pendientes de ejecucion.
        estado: Estado actual del proceso (inicia en ``NUEVO``).
        tiempo_inicio: Instante en que el proceso accede por primera vez a CPU.
        tiempo_finalizacion: Instante en que el proceso completa su ejecucion.
    """

    id: str
    tamanio: int
    tiempo_arribo: int
    tiempo_irrupcion: int
    tiempo_restante: Optional[int] = None
    estado: str = ESTADO_NUEVO
    tiempo_inicio: Optional[int] = None
    tiempo_finalizacion: Optional[int] = None

    def __post_init__(self) -> None:
        if self.id is None:
            raise ValueError("El ID del proceso no puede ser nulo.")
        self.id = str(self.id).strip()
        if not self.id:
            raise ValueError("El ID del proceso no puede estar vacio.")

        if not _es_entero(self.tamanio) or self.tamanio <= 0:
            raise ValueError(
                f"El tamanio del proceso '{self.id}' debe ser un entero positivo."
            )

        if not _es_entero(self.tiempo_arribo) or self.tiempo_arribo < 0:
            raise ValueError(
                f"El tiempo de arribo del proceso '{self.id}' debe ser un entero mayor o igual a 0."
            )

        if not _es_entero(self.tiempo_irrupcion) or self.tiempo_irrupcion <= 0:
            raise ValueError(
                f"El tiempo de irrupcion del proceso '{self.id}' debe ser un entero positivo."
            )

        if self.tiempo_restante is None:
            self.tiempo_restante = self.tiempo_irrupcion
        elif (
            not _es_entero(self.tiempo_restante)
            or self.tiempo_restante < 0
            or self.tiempo_restante > self.tiempo_irrupcion
        ):
            raise ValueError(
                f"El tiempo restante del proceso '{self.id}' debe estar entre 0 y {self.tiempo_irrupcion}."
            )

        if self.estado not in ESTADOS_VALIDOS:
            raise ValueError(
                f"El estado '{self.estado}' no es valido. Estados permitidos: {', '.join(ESTADOS_VALIDOS)}."
            )


# ============================================================================
# 1.1 ESTADOS Y TRANSICIONES
# Estados y transiciones permitidas del ciclo de vida de un proceso.
# ============================================================================

TRANSICIONES_PERMITIDAS = {
    ESTADO_NUEVO: {ESTADO_LISTO, ESTADO_LISTO_SUSPENDIDO},
    ESTADO_LISTO: {ESTADO_EJECUCION},
    ESTADO_LISTO_SUSPENDIDO: {ESTADO_LISTO},
    ESTADO_EJECUCION: {ESTADO_LISTO, ESTADO_TERMINADO},
    ESTADO_TERMINADO: set(),
}


def cambiar_estado(proceso: Proceso, estado_destino: str) -> None:
    """Cambia el estado si la transicion pertenece al ciclo de vida acordado."""
    if estado_destino not in TRANSICIONES_PERMITIDAS.get(proceso.estado, set()):
        raise ValueError(
            f"No se puede pasar el proceso '{proceso.id}' "
            f"de {proceso.estado} a {estado_destino}."
        )
    proceso.estado = estado_destino


# ============================================================================
# 2. CARGA DEL CSV
# Lectura y validacion de procesos desde archivos CSV.
# ============================================================================

MAX_PROCESOS = 10
COLUMNAS_ESPERADAS = ("id", "tamanio", "tiempo_arribo", "tiempo_irrupcion")


class ErrorCargaProcesos(ValueError):
    """Error controlado durante la lectura o validacion del archivo de procesos."""


def _es_fila_vacia(fila: Sequence[str]) -> bool:
    return not fila or all(celda.strip() == "" for celda in fila)


def _parsear_entero(valor: str, nombre_campo: str, numero_linea: int) -> int:
    texto = valor.strip()
    if not texto:
        raise ErrorCargaProcesos(
            f"Linea {numero_linea}: el campo '{nombre_campo}' esta vacio."
        )
    try:
        return int(texto)
    except ValueError as exc:
        raise ErrorCargaProcesos(
            f"Linea {numero_linea}: el campo '{nombre_campo}' ('{texto}') debe ser un numero entero."
        ) from exc


def cargar_procesos_desde_csv(ruta_archivo: Union[str, Path]) -> List[Proceso]:
    """Lee y valida un archivo CSV sin encabezado devolviendo los procesos en estado NUEVO.

    Cada fila debe tener el formato: ``id,tamanio,tiempo_arribo,tiempo_irrupcion``.

    Argumentos:
        ruta_archivo: Ruta al archivo CSV a cargar.

    Retorna:
        Lista de instancias ``Proceso`` validadas (entre 1 y ``MAX_PROCESOS``).

    Excepciones:
        ErrorCargaProcesos: Si el archivo no existe, no puede leerse, tiene formato
            invalido, datos fuera de rango o supera los 10 procesos permitidos.
    """
    if ruta_archivo is None or str(ruta_archivo).strip() == "":
        raise ErrorCargaProcesos("Debe especificar una ruta de archivo CSV valida.")

    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ErrorCargaProcesos(f"No se encontro el archivo '{ruta}'.")
    if not ruta.is_file():
        raise ErrorCargaProcesos(f"La ruta '{ruta}' no corresponde a un archivo.")

    try:
        with ruta.open(mode="r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.reader(archivo)
            filas_datos = [
                (numero_linea, fila)
                for numero_linea, fila in enumerate(lector, start=1)
                if not _es_fila_vacia(fila)
            ]
    except UnicodeDecodeError as exc:
        raise ErrorCargaProcesos(
            f"El archivo '{ruta}' no tiene una codificacion de texto UTF-8 valida."
        ) from exc
    except (OSError, csv.Error) as exc:
        raise ErrorCargaProcesos(
            f"No se pudo leer el archivo CSV '{ruta}': {exc}"
        ) from exc

    if not filas_datos:
        raise ErrorCargaProcesos(f"El archivo '{ruta}' esta vacio.")

    if len(filas_datos) > MAX_PROCESOS:
        raise ErrorCargaProcesos(
            f"El archivo contiene {len(filas_datos)} procesos, pero el maximo permitido es {MAX_PROCESOS}."
        )

    procesos: List[Proceso] = []
    ids_vistos = set()

    for numero_linea, fila in filas_datos:
        if len(fila) != len(COLUMNAS_ESPERADAS):
            raise ErrorCargaProcesos(
                f"Linea {numero_linea}: se esperaban 4 columnas "
                f"({', '.join(COLUMNAS_ESPERADAS)}), pero se encontraron {len(fila)}."
            )

        id_crudo, tamanio_crudo, arribo_crudo, irrupcion_cruda = fila
        id_proceso = id_crudo.strip()
        if not id_proceso:
            raise ErrorCargaProcesos(
                f"Linea {numero_linea}: el campo 'id' no puede estar vacio."
            )
        if id_proceso in ids_vistos:
            raise ErrorCargaProcesos(
                f"Linea {numero_linea}: el ID de proceso '{id_proceso}' esta duplicado."
            )

        tamanio = _parsear_entero(tamanio_crudo, "tamanio", numero_linea)
        tiempo_arribo = _parsear_entero(arribo_crudo, "tiempo_arribo", numero_linea)
        tiempo_irrupcion = _parsear_entero(
            irrupcion_cruda, "tiempo_irrupcion", numero_linea
        )

        try:
            proceso = Proceso(
                id=id_proceso,
                tamanio=tamanio,
                tiempo_arribo=tiempo_arribo,
                tiempo_irrupcion=tiempo_irrupcion,
                estado=ESTADO_NUEVO,
            )
        except ValueError as exc:
            raise ErrorCargaProcesos(f"Linea {numero_linea}: {exc}") from exc

        ids_vistos.add(id_proceso)
        procesos.append(proceso)

    return procesos


cargar_procesos = cargar_procesos_desde_csv


# ============================================================================
# 3. MEMORIA MVT CON BEST-FIT
# Administracion de memoria con particiones variables y Best-Fit.
# ============================================================================

MEMORIA_SO_KB = 100
MEMORIA_USUARIO_KB = 450
MEMORIA_TOTAL_KB = MEMORIA_SO_KB + MEMORIA_USUARIO_KB
DIRECCION_INICIO_SO = 0
DIRECCION_INICIO_USUARIO = MEMORIA_SO_KB


def _es_entero_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _es_entero_no_negativo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


@dataclass(frozen=True)
class ParticionMemoria:
    """Representa una particion ocupada o un hueco libre en la memoria.

    ``numero`` es el ID de particion: se asigna al crear la particion para un
    proceso y no cambia aunque otras particiones se liberen o fusionen. El SO
    usa el 0 y los huecos libres no tienen numero.
    """

    direccion_inicio: int
    tamanio: int
    proceso_id: Optional[str] = None
    numero: Optional[int] = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not _es_entero_no_negativo(self.direccion_inicio):
            raise ValueError(
                "La direccion de inicio de la particion debe ser un entero mayor o igual a 0."
            )
        if not _es_entero_positivo(self.tamanio):
            raise ValueError(
                "El tamanio de la particion debe ser un entero positivo."
            )
        if self.proceso_id is not None:
            id_limpio = str(self.proceso_id).strip()
            if not id_limpio:
                raise ValueError("El ID del proceso en la particion no puede estar vacio.")
            object.__setattr__(self, "proceso_id", id_limpio)

    @property
    def direccion_fin(self) -> int:
        """Direccion limite exclusiva donde termina la particion."""
        return self.direccion_inicio + self.tamanio

    @property
    def libre(self) -> bool:
        """Indica si la particion es un hueco libre."""
        return self.proceso_id is None


class GestorMemoria:
    """Gestiona la memoria de usuario mediante particiones variables (MVT) y Best-Fit.

    La memoria total es de 550K:
        - [0, 100): 100K reservados para el Sistema Operativo.
        - [100, 550): 450K disponibles para procesos de usuario.
    """

    def __init__(
        self,
        memoria_so_kb: int = MEMORIA_SO_KB,
        memoria_usuario_kb: int = MEMORIA_USUARIO_KB,
    ) -> None:
        if not _es_entero_no_negativo(memoria_so_kb):
            raise ValueError("La memoria reservada al SO debe ser un entero no negativo.")
        if not _es_entero_positivo(memoria_usuario_kb):
            raise ValueError("La memoria de usuario debe ser un entero positivo.")

        self._memoria_so_kb = memoria_so_kb
        self._memoria_usuario_kb = memoria_usuario_kb
        self._direccion_inicio_usuario = memoria_so_kb
        self._siguiente_numero_particion = 1
        self._particiones: List[ParticionMemoria] = [
            ParticionMemoria(
                direccion_inicio=self._direccion_inicio_usuario,
                tamanio=self._memoria_usuario_kb,
                proceso_id=None,
            )
        ]

    @property
    def memoria_so_kb(self) -> int:
        """Tamanio en KB reservado para el sistema operativo."""
        return self._memoria_so_kb

    @property
    def memoria_usuario_kb(self) -> int:
        """Tamanio total en KB de la memoria de usuario."""
        return self._memoria_usuario_kb

    @property
    def memoria_total_kb(self) -> int:
        """Tamanio total en KB de la memoria del sistema (SO + usuario)."""
        return self._memoria_so_kb + self._memoria_usuario_kb

    @property
    def direccion_inicio_usuario(self) -> int:
        """Direccion donde comienza el espacio de memoria de usuario."""
        return self._direccion_inicio_usuario

    def particion_sistema_operativo(self) -> ParticionMemoria:
        """Retorna la particion reservada al Sistema Operativo."""
        return ParticionMemoria(
            direccion_inicio=DIRECCION_INICIO_SO,
            tamanio=self._memoria_so_kb,
            proceso_id="SO",
            numero=0,
        )

    def obtener_particiones(self) -> List[ParticionMemoria]:
        """Retorna una copia ordenada de todas las particiones del area de usuario."""
        return list(self._particiones)

    def obtener_huecos(self) -> List[ParticionMemoria]:
        """Retorna la lista de huecos libres actuales en el area de usuario."""
        return [particion for particion in self._particiones if particion.libre]

    def obtener_particiones_ocupadas(self) -> List[ParticionMemoria]:
        """Retorna la lista de particiones asignadas a procesos de usuario."""
        return [particion for particion in self._particiones if not particion.libre]

    def obtener_asignacion(
        self, proceso_o_id: Union[Proceso, str]
    ) -> Optional[ParticionMemoria]:
        """Retorna la particion asignada a un proceso especifico o ``None`` si no reside en memoria."""
        id_buscado = self._extraer_id_proceso(proceso_o_id)
        for particion in self._particiones:
            if particion.proceso_id == id_buscado:
                return particion
        return None

    def memoria_libre_total(self) -> int:
        """Suma total en KB de los huecos libres en el area de usuario."""
        return sum(hueco.tamanio for hueco in self.obtener_huecos())

    def memoria_ocupada_total(self) -> int:
        """Suma total en KB de las particiones ocupadas en el area de usuario."""
        return sum(
            particion.tamanio for particion in self.obtener_particiones_ocupadas()
        )

    def mayor_hueco_libre(self) -> int:
        """Retorna el tamanio en KB del hueco libre mas grande disponible (o 0 si no hay huecos)."""
        huecos = self.obtener_huecos()
        if not huecos:
            return 0
        return max(hueco.tamanio for hueco in huecos)

    def puede_asignar(self, tamanio: int) -> bool:
        """Indica si existe un hueco libre capaz de alojar ``tamanio`` KB."""
        if not _es_entero_positivo(tamanio):
            raise ValueError("El tamanio a consultar debe ser un entero positivo.")
        if tamanio > self._memoria_usuario_kb:
            return False
        return any(
            particion.libre and particion.tamanio >= tamanio
            for particion in self._particiones
        )

    def asignar(
        self,
        proceso_o_id: Union[Proceso, str],
        tamanio: Optional[int] = None,
    ) -> Optional[ParticionMemoria]:
        """Intenta asignar memoria mediante Best-Fit para el proceso indicado.

        Elige el hueco libre mas pequenio en el que entre el proceso. En caso de
        empate de tamanio entre dos huecos libres, selecciona el de menor direccion
        inicial.

        Argumentos:
            proceso_o_id: Instancia de ``Proceso`` o identificador ``str`` del proceso.
            tamanio: Tamanio en KB a asignar (opcional si se recibe un ``Proceso``).

        Retorna:
            La ``ParticionMemoria`` asignada con su direccion inicial y tamanio,
            o ``None`` si no existe un hueco libre suficiente.
        """
        id_proceso, tamanio_requerido = self._extraer_datos_asignacion(
            proceso_o_id, tamanio
        )

        if self.obtener_asignacion(id_proceso) is not None:
            raise ValueError(
                f"El proceso '{id_proceso}' ya tiene una particion de memoria asignada."
            )

        if tamanio_requerido > self._memoria_usuario_kb:
            return None

        indice_mejor_hueco = self._buscar_indice_best_fit(tamanio_requerido)
        if indice_mejor_hueco is None:
            return None

        hueco_seleccionado = self._particiones[indice_mejor_hueco]
        particion_asignada = ParticionMemoria(
            direccion_inicio=hueco_seleccionado.direccion_inicio,
            tamanio=tamanio_requerido,
            proceso_id=id_proceso,
            numero=self._siguiente_numero_particion,
        )
        self._siguiente_numero_particion += 1

        tamanio_remanente = hueco_seleccionado.tamanio - tamanio_requerido
        if tamanio_remanente == 0:
            self._particiones[indice_mejor_hueco] = particion_asignada
        else:
            hueco_remanente = ParticionMemoria(
                direccion_inicio=particion_asignada.direccion_fin,
                tamanio=tamanio_remanente,
                proceso_id=None,
            )
            self._particiones[indice_mejor_hueco : indice_mejor_hueco + 1] = [
                particion_asignada,
                hueco_remanente,
            ]

        return particion_asignada

    def liberar(self, proceso_o_id: Union[Proceso, str]) -> bool:
        """Libera la particion ocupada por el proceso y fusiona huecos libres contiguos.

        Argumentos:
            proceso_o_id: Instancia de ``Proceso`` o identificador ``str`` del proceso.

        Retorna:
            ``True`` si el proceso tenia memoria asignada y fue liberada;
            ``False`` si el proceso no se encontraba en memoria.
        """
        id_proceso = self._extraer_id_proceso(proceso_o_id)

        for indice, particion in enumerate(self._particiones):
            if particion.proceso_id == id_proceso:
                self._particiones[indice] = ParticionMemoria(
                    direccion_inicio=particion.direccion_inicio,
                    tamanio=particion.tamanio,
                    proceso_id=None,
                )
                self._compactar_huecos_adyacentes()
                return True

        return False

    def obtener_resumen_memoria(self) -> Dict[str, object]:
        """Retorna una instantanea observable del estado de memoria para presentacion."""
        return {
            "memoria_total_kb": self.memoria_total_kb,
            "memoria_so_kb": self._memoria_so_kb,
            "memoria_usuario_kb": self._memoria_usuario_kb,
            "memoria_ocupada_usuario_kb": self.memoria_ocupada_total(),
            "memoria_libre_usuario_kb": self.memoria_libre_total(),
            "particion_so": self.particion_sistema_operativo(),
            "particiones_usuario": self.obtener_particiones(),
            "huecos_libres": self.obtener_huecos(),
            "particiones_ocupadas": self.obtener_particiones_ocupadas(),
        }

    def _buscar_indice_best_fit(self, tamanio_requerido: int) -> Optional[int]:
        candidatos: List[Tuple[int, int, int]] = []
        for indice, particion in enumerate(self._particiones):
            if particion.libre and particion.tamanio >= tamanio_requerido:
                candidatos.append(
                    (particion.tamanio, particion.direccion_inicio, indice)
                )

        if not candidatos:
            return None

        _, _, indice_elegido = min(candidatos)
        return indice_elegido

    def _compactar_huecos_adyacentes(self) -> None:
        if not self._particiones:
            return

        compactadas: List[ParticionMemoria] = [self._particiones[0]]
        for actual in self._particiones[1:]:
            anterior = compactadas[-1]
            if anterior.libre and actual.libre:
                compactadas[-1] = ParticionMemoria(
                    direccion_inicio=anterior.direccion_inicio,
                    tamanio=anterior.tamanio + actual.tamanio,
                    proceso_id=None,
                )
            else:
                compactadas.append(actual)

        self._particiones = compactadas

    @staticmethod
    def _extraer_id_proceso(proceso_o_id: Union[Proceso, str]) -> str:
        if isinstance(proceso_o_id, Proceso):
            return proceso_o_id.id
        if isinstance(proceso_o_id, str):
            id_limpio = proceso_o_id.strip()
            if id_limpio:
                return id_limpio
        raise ValueError("Debe proporcionar un Proceso o un ID de proceso valido.")

    @classmethod
    def _extraer_datos_asignacion(
        cls,
        proceso_o_id: Union[Proceso, str],
        tamanio: Optional[int],
    ) -> Tuple[str, int]:
        if isinstance(proceso_o_id, Proceso):
            tamanio_final = (
                proceso_o_id.tamanio if tamanio is None else tamanio
            )
            if not _es_entero_positivo(tamanio_final):
                raise ValueError("El tamanio del proceso debe ser un entero positivo.")
            return proceso_o_id.id, tamanio_final

        id_proceso = cls._extraer_id_proceso(proceso_o_id)
        if not _es_entero_positivo(tamanio):
            raise ValueError(
                "Debe indicar un tamanio entero positivo al asignar por ID de proceso."
            )
        return id_proceso, int(tamanio)


# ============================================================================
# 4. ADMISION Y COLAS
# Llegadas, colas y admision de procesos con grado maximo cinco.
# ============================================================================

GRADO_MAXIMO_MULTIPROGRAMACION = 5


class ErrorAdmision(ValueError):
    """Indica que la entrada no permite iniciar una simulacion valida."""


@dataclass(frozen=True)
class Transicion:
    """Registro de un intento de admision y su resultado.

    Si ``origen`` y ``destino`` coinciden, el proceso no cambio de estado
    (por ejemplo, un suspendido que todavia no entra en memoria) y ``motivo``
    explica por que.
    """

    proceso: Proceso
    origen: str
    destino: str
    motivo: str


class Admision:
    """Administra el cupo, la residencia en memoria y las colas de procesos.

    Los arribos se atienden por tiempo y, ante empate, por orden de entrada.
    Cuando se libera memoria, los suspendidos se reintentan en orden FIFO antes
    de admitir procesos NUEVO que esperan un cupo de multiprogramacion.
    """

    def __init__(self, procesos: Sequence[Proceso], memoria: GestorMemoria) -> None:
        self.procesos = list(procesos)
        self.memoria = memoria
        self._sin_arribar = sorted(
            enumerate(self.procesos),
            key=lambda item: (item[1].tiempo_arribo, item[0]),
        )
        self._nuevos_pendientes: List[Proceso] = []
        self._listos: List[Proceso] = []
        self._suspendidos: List[Proceso] = []
        self._en_ejecucion: Optional[Proceso] = None
        self._transiciones: List[Transicion] = []

        ids = set()
        for proceso in self.procesos:
            if proceso.id in ids:
                raise ErrorAdmision(f"El ID '{proceso.id}' esta repetido.")
            ids.add(proceso.id)
            if proceso.estado != ESTADO_NUEVO:
                raise ErrorAdmision(
                    f"El proceso '{proceso.id}' debe comenzar en estado NUEVO."
                )
            if proceso.tamanio > memoria.memoria_usuario_kb:
                raise ErrorAdmision(
                    f"El proceso '{proceso.id}' requiere {proceso.tamanio}K, "
                    f"pero la memoria de usuario tiene {memoria.memoria_usuario_kb}K."
                )

    def procesar_arribos(self, tiempo: int) -> List[Proceso]:
        """Registra los arribos hasta ``tiempo`` y admite los que tienen cupo."""
        arribados: List[Proceso] = []
        while self._sin_arribar and self._sin_arribar[0][1].tiempo_arribo <= tiempo:
            _, proceso = self._sin_arribar.pop(0)
            self._nuevos_pendientes.append(proceso)
            arribados.append(proceso)
        self._admitir_nuevos()
        return arribados

    def extraer_transiciones(self) -> List[Transicion]:
        """Retorna y vacia las transiciones de admision registradas."""
        transiciones = self._transiciones
        self._transiciones = []
        return transiciones

    def obtener_nuevos(self) -> List[Proceso]:
        """Retorna los procesos en NUEVO, incluidos los que aun no arribaron."""
        return list(self._nuevos_pendientes) + [
            proceso for _, proceso in self._sin_arribar
        ]

    def obtener_listos(self) -> List[Proceso]:
        """Retorna una copia de la cola LISTO en su orden actual."""
        return list(self._listos)

    def obtener_listos_suspendidos(self) -> List[Proceso]:
        """Retorna una copia de la cola LISTO_SUSPENDIDO en orden FIFO."""
        return list(self._suspendidos)

    def grado_multiprogramacion(self) -> int:
        """Cuenta EJECUCION, LISTO y LISTO_SUSPENDIDO."""
        return len(self._listos) + len(self._suspendidos) + int(
            self._en_ejecucion is not None
        )

    def enviar_a_ejecucion(self, proceso: Proceso) -> None:
        """Mueve un proceso LISTO a la CPU seleccionada por el planificador."""
        if self._en_ejecucion is not None:
            raise ValueError("La CPU ya tiene un proceso en EJECUCION.")
        if proceso not in self._listos:
            raise ValueError(f"El proceso '{proceso.id}' no esta en LISTO.")
        cambiar_estado(proceso, ESTADO_EJECUCION)
        self._listos.remove(proceso)
        self._en_ejecucion = proceso

    def devolver_a_listo(self, proceso: Proceso) -> None:
        """Devuelve a LISTO el proceso cuya CPU fue apropiada."""
        if proceso is not self._en_ejecucion:
            raise ValueError(f"El proceso '{proceso.id}' no esta en EJECUCION.")
        cambiar_estado(proceso, ESTADO_LISTO)
        self._en_ejecucion = None
        self._listos.append(proceso)

    def finalizar(self, proceso: Proceso) -> None:
        """Pasa a TERMINADO el proceso que completo su tiempo de CPU."""
        if proceso is not self._en_ejecucion:
            raise ValueError(f"El proceso '{proceso.id}' no esta en EJECUCION.")
        cambiar_estado(proceso, ESTADO_TERMINADO)
        self._en_ejecucion = None

    def reintentar_suspendidos(self) -> List[Proceso]:
        """Reintenta suspendidos y ocupa cupos liberados con procesos NUEVO."""
        admitidos: List[Proceso] = []
        for proceso in list(self._suspendidos):
            if self._intentar_cargar(proceso, ESTADO_LISTO_SUSPENDIDO):
                self._suspendidos.remove(proceso)
                self._listos.append(proceso)
                admitidos.append(proceso)
        admitidos.extend(self._admitir_nuevos())
        return admitidos

    def hay_procesos_pendientes(self) -> bool:
        """Indica si falta completar al menos un proceso de la entrada."""
        return any(proceso.estado != ESTADO_TERMINADO for proceso in self.procesos)

    def _admitir_nuevos(self) -> List[Proceso]:
        admitidos: List[Proceso] = []
        while (
            self._nuevos_pendientes
            and self.grado_multiprogramacion() < GRADO_MAXIMO_MULTIPROGRAMACION
        ):
            proceso = self._nuevos_pendientes.pop(0)
            if self._intentar_cargar(proceso, ESTADO_NUEVO):
                self._listos.append(proceso)
                admitidos.append(proceso)
            else:
                self._suspendidos.append(proceso)
        return admitidos

    def _intentar_cargar(self, proceso: Proceso, origen: str) -> bool:
        """Intenta asignar memoria Best-Fit y registra el resultado.

        Retorna ``True`` si el proceso paso a LISTO. Si no hay hueco, un
        proceso NUEVO pasa a LISTO_SUSPENDIDO y uno suspendido permanece alli.
        """
        mayor_hueco = self.memoria.mayor_hueco_libre()
        libre_total = self.memoria.memoria_libre_total()
        huecos = [hueco.tamanio for hueco in self.memoria.obtener_huecos()]
        particion = self.memoria.asignar(proceso)

        if particion is not None:
            cambiar_estado(proceso, ESTADO_LISTO)
            motivo = (
                f"Best-Fit crea la particion {particion.numero} de "
                f"{particion.tamanio}K en "
                f"[{particion.direccion_inicio}K - {particion.direccion_fin}K)"
            )
            if len(huecos) > 1:
                motivo += (
                    "; elige el hueco mas chico donde entra entre: "
                    + ", ".join(f"{tamanio}K" for tamanio in huecos)
                )
            self._transiciones.append(
                Transicion(proceso, origen, ESTADO_LISTO, motivo)
            )
            return True

        if libre_total >= proceso.tamanio:
            motivo = (
                f"requiere {proceso.tamanio}K; hay {libre_total}K libres pero "
                f"el mayor hueco contiguo es de {mayor_hueco}K "
                "(fragmentacion externa)"
            )
        else:
            motivo = (
                f"requiere {proceso.tamanio}K y solo hay {libre_total}K libres"
            )
        if origen != ESTADO_LISTO_SUSPENDIDO:
            cambiar_estado(proceso, ESTADO_LISTO_SUSPENDIDO)
        self._transiciones.append(
            Transicion(proceso, origen, ESTADO_LISTO_SUSPENDIDO, motivo)
        )
        return False


# ============================================================================
# 5. PLANIFICADOR SRTF
# Planificacion apropiativa SRTF y reloj discreto de la simulacion.
# ============================================================================

TIPO_INICIO = "INICIO_EJECUCION"
TIPO_ARRIBO = "ARRIBO"
TIPO_APROPIACION = "APROPIACION"
TIPO_FINALIZACION = "FINALIZACION"
TIPO_CPU_OCIOSA = "CPU_OCIOSA"
TIPO_MEMORIA_LIBERADA = "MEMORIA_LIBERADA"
TIPO_NUEVA_ADMISION = "NUEVA_ADMISION"
TIPO_SIGUE_SUSPENDIDO = "SIGUE_SUSPENDIDO"


class TransicionAdmision(Protocol):
    """Datos minimos de una transicion registrada por admision."""

    proceso: Proceso
    origen: str
    destino: str
    motivo: str


@dataclass(frozen=True)
class EventoPlanificador:
    """Describe un cambio relevante producido por el planificador."""

    tiempo: int
    tipo: str
    proceso_id: Optional[str] = None
    detalle: str = ""


class AdministradorAdmision(Protocol):
    """Contrato que HU-03 debe ofrecer al planificador.

    La admision conserva la propiedad de las colas y de las transiciones de
    estado. El planificador solo solicita los cambios que corresponden a SRTF.
    """

    def procesar_arribos(self, tiempo: int) -> Sequence[Proceso]:
        """Procesa los procesos cuyo tiempo de arribo coincide con ``tiempo``."""

    def obtener_listos(self) -> Sequence[Proceso]:
        """Retorna una vista de los procesos que pueden usar la CPU."""

    def obtener_listos_suspendidos(self) -> Sequence[Proceso]:
        """Retorna la cola de procesos que esperan memoria."""

    def enviar_a_ejecucion(self, proceso: Proceso) -> None:
        """Pasa un proceso LISTO a EJECUCION."""

    def devolver_a_listo(self, proceso: Proceso) -> None:
        """Devuelve a LISTO un proceso apropiado."""

    def finalizar(self, proceso: Proceso) -> None:
        """Pasa un proceso en EJECUCION a TERMINADO."""

    def reintentar_suspendidos(self) -> Sequence[Proceso]:
        """Reintenta admitir procesos luego de liberar memoria."""

    def hay_procesos_pendientes(self) -> bool:
        """Indica si quedan procesos sin terminar."""

    def extraer_transiciones(self) -> Sequence[TransicionAdmision]:
        """Retorna y vacia los cambios de estado producidos por admision."""

    def grado_multiprogramacion(self) -> int:
        """Cuenta los procesos en EJECUCION, LISTO y LISTO_SUSPENDIDO."""


ObservadorEventos = Callable[[EventoPlanificador], None]


class PlanificadorSRTF:
    """Coordina la CPU con Shortest Remaining Time First apropiativo.

    Convencion temporal: los arribos del instante ``t`` se procesan antes de
    elegir la CPU. Una unidad ejecutada en ``t`` termina en ``t + 1``.

    Desempate: el proceso que ya ocupa la CPU continua si empata en tiempo
    restante con el mejor proceso LISTO. Cuando la CPU esta libre, se elige por
    menor tiempo restante, luego menor tiempo de arribo y finalmente menor ID.
    """

    def __init__(
        self,
        admision: AdministradorAdmision,
        memoria: GestorMemoria,
        observador: Optional[ObservadorEventos] = None,
    ) -> None:
        self.admision = admision
        self.memoria = memoria
        self.observador = observador
        self.reloj = 0
        self.proceso_en_ejecucion: Optional[Proceso] = None
        self.cambios_contexto = 0
        self._cpu_ociosa_informada = False

    @staticmethod
    def seleccionar_srtf(procesos: Sequence[Proceso]) -> Optional[Proceso]:
        """Selecciona en forma determinista el proceso con menor tiempo restante."""
        if not procesos:
            return None

        for proceso in procesos:
            if proceso.tiempo_restante is None or proceso.tiempo_restante <= 0:
                raise ValueError(
                    f"El proceso '{proceso.id}' no tiene tiempo restante positivo."
                )

        return min(
            procesos,
            key=lambda proceso: (
                proceso.tiempo_restante,
                proceso.tiempo_arribo,
                proceso.id,
            ),
        )

    def simular(self) -> None:
        """Ejecuta automaticamente hasta que admision no tenga trabajo pendiente."""
        while self.admision.hay_procesos_pendientes():
            self.avanzar_unidad()

    def avanzar_unidad(self) -> None:
        """Procesa arribos, reevalua SRTF y avanza una unidad discreta."""
        self.procesar_instante()
        self.ejecutar_unidad()

    def procesar_instante(self) -> None:
        """Atiende los arribos del instante actual y reevalua la CPU (SRTF).

        No avanza el reloj: luego de llamarlo, el estado observable es el del
        instante ``self.reloj``.
        """
        arribados = self.admision.procesar_arribos(self.reloj)
        self._informar_arribos(arribados, self.admision.extraer_transiciones())
        self._reevaluar_cpu()
        if self.proceso_en_ejecucion is None:
            self._informar_cpu_ociosa()

    def ejecutar_unidad(self) -> None:
        """Ejecuta una unidad de CPU y avanza el reloj de ``t`` a ``t + 1``.

        Si el proceso termina, se informa en ``t + 1`` junto con la liberacion
        de memoria, las nuevas admisiones y el siguiente proceso en CPU.
        """
        if self.proceso_en_ejecucion is None:
            self.reloj += 1
            return

        self._cpu_ociosa_informada = False
        proceso = self.proceso_en_ejecucion
        if proceso.tiempo_inicio is None:
            proceso.tiempo_inicio = self.reloj

        proceso.tiempo_restante -= 1
        self.reloj += 1

        if proceso.tiempo_restante == 0:
            self._finalizar(proceso)

    def _reevaluar_cpu(self) -> None:
        listos = list(self.admision.obtener_listos())
        elegido = self.seleccionar_srtf(listos)
        actual = self.proceso_en_ejecucion

        if actual is not None:
            if elegido is None or actual.tiempo_restante <= elegido.tiempo_restante:
                return

            self.admision.devolver_a_listo(actual)
            self.admision.enviar_a_ejecucion(elegido)
            self.proceso_en_ejecucion = elegido
            self.cambios_contexto += 1
            self._emitir(
                TIPO_APROPIACION,
                elegido,
                f"{elegido.id} apropia la CPU a {actual.id}: tiene menor "
                f"tiempo restante ({elegido.tiempo_restante} ut contra "
                f"{actual.tiempo_restante} ut). {elegido.id} pasa de LISTO a "
                f"EJECUCION y {actual.id} pasa de EJECUCION a LISTO.",
            )
            return

        if elegido is not None:
            self._asignar_cpu(elegido)
            self._informar_inicio(elegido)

    def _asignar_cpu(self, proceso: Proceso) -> None:
        """Ocupa una CPU libre con un proceso LISTO en el mismo instante."""
        self.admision.enviar_a_ejecucion(proceso)
        self.proceso_en_ejecucion = proceso
        self.cambios_contexto += 1

    def _finalizar(self, proceso: Proceso) -> None:
        proceso.tiempo_finalizacion = self.reloj
        self.admision.finalizar(proceso)
        self.proceso_en_ejecucion = None

        particion = self.memoria.obtener_asignacion(proceso)
        memoria_liberada = self.memoria.liberar(proceso)
        libre_tras_liberar = self.memoria.memoria_libre_total()
        self.admision.reintentar_suspendidos()
        transiciones_reintento = self.admision.extraer_transiciones()
        # Los arribos de este mismo instante participan de la eleccion SRTF.
        arribados = self.admision.procesar_arribos(self.reloj)
        transiciones_arribo = self.admision.extraer_transiciones()
        siguiente = self.seleccionar_srtf(self.admision.obtener_listos())
        if siguiente is not None:
            self._asignar_cpu(siguiente)

        # Se informan los cambios en el orden en que ocurrieron.
        self._emitir(
            TIPO_FINALIZACION,
            proceso,
            f"{proceso.id} finaliza: completa su tiempo de irrupcion "
            f"({proceso.tiempo_irrupcion} ut) y pasa de EJECUCION a TERMINADO.",
        )

        if memoria_liberada and particion is not None:
            self._emitir(
                TIPO_MEMORIA_LIBERADA,
                proceso,
                f"Se libera la memoria de {proceso.id} (particion "
                f"{particion.numero}): {particion.tamanio}K en "
                f"[{particion.direccion_inicio}K - {particion.direccion_fin}K). "
                f"Quedan {libre_tras_liberar}K libres para reintentar admisiones.",
            )

        for transicion in transiciones_reintento:
            self._informar_transicion(transicion)

        self._informar_arribos(arribados, transiciones_arribo)

        if siguiente is not None:
            self._informar_inicio(siguiente)

    def _informar_inicio(self, proceso: Proceso) -> None:
        self._emitir(
            TIPO_INICIO,
            proceso,
            f"{proceso.id} pasa de LISTO a EJECUCION (ingresa a la CPU con "
            f"{proceso.tiempo_restante} ut restantes).",
        )

    def _informar_arribos(
        self,
        arribados: Sequence[Proceso],
        transiciones: Sequence[TransicionAdmision],
    ) -> None:
        """Informa cada arribo junto con el estado al que pasa y el motivo."""
        ids_arribados = {proceso.id for proceso in arribados}
        por_proceso: Dict[str, TransicionAdmision] = {}
        otras: List[TransicionAdmision] = []
        for transicion in transiciones:
            proceso_id = transicion.proceso.id
            if (
                proceso_id in ids_arribados
                and transicion.origen == ESTADO_NUEVO
                and proceso_id not in por_proceso
            ):
                por_proceso[proceso_id] = transicion
            else:
                otras.append(transicion)

        for proceso in arribados:
            transicion = por_proceso.get(proceso.id)
            if transicion is None:
                detalle = (
                    f"{proceso.id} llega y permanece en NUEVO (sin cupo de "
                    "multiprogramacion: ya hay "
                    f"{self.admision.grado_multiprogramacion()} procesos "
                    "admitidos)."
                )
            else:
                detalle = (
                    f"{proceso.id} llega y pasa a {transicion.destino} "
                    f"({transicion.motivo})."
                )
            self._emitir(TIPO_ARRIBO, proceso, detalle)

        for transicion in otras:
            self._informar_transicion(transicion)

    def _informar_transicion(self, transicion: TransicionAdmision) -> None:
        proceso = transicion.proceso
        if transicion.origen == transicion.destino:
            self._emitir(
                TIPO_SIGUE_SUSPENDIDO,
                proceso,
                f"{proceso.id} permanece en {transicion.destino} "
                f"({transicion.motivo}).",
            )
            return
        self._emitir(
            TIPO_NUEVA_ADMISION,
            proceso,
            f"{proceso.id} pasa de {transicion.origen} a {transicion.destino} "
            f"({transicion.motivo}).",
        )

    def _informar_cpu_ociosa(self) -> None:
        if not self._cpu_ociosa_informada:
            self._emitir(
                TIPO_CPU_OCIOSA,
                detalle="La CPU se encuentra ociosa (no hay procesos en LISTO).",
            )
            self._cpu_ociosa_informada = True

    def _emitir(
        self,
        tipo: str,
        proceso: Optional[Proceso] = None,
        detalle: str = "",
    ) -> None:
        if self.observador is not None:
            self.observador(
                EventoPlanificador(
                    tiempo=self.reloj,
                    tipo=tipo,
                    proceso_id=None if proceso is None else proceso.id,
                    detalle=detalle,
                )
            )


# ============================================================================
# 6. INFORME ESTADISTICO
# Calculo del informe estadistico final de la simulacion.
# ============================================================================
#
# Convenciones (unidades de tiempo discretas, ut):
#   - Tiempo de retorno = tiempo de finalizacion - tiempo de arribo.
#   - Tiempo de espera  = tiempo de retorno - tiempo de irrupcion.
#     Incluye todo el tiempo que el proceso estuvo en el sistema sin usar la
#     CPU: en NUEVO esperando cupo, en LISTO_SUSPENDIDO y en LISTO.
#   - Tiempo de respuesta = primer instante en CPU - tiempo de arribo.
#   - Rendimiento = trabajos terminados / tiempo total de la simulacion.
#     El tiempo total es el instante en que termina el ultimo proceso.


@dataclass(frozen=True)
class EstadisticaProceso:
    """Tiempos calculados para un proceso terminado."""

    id: str
    tiempo_arribo: int
    tiempo_irrupcion: int
    tiempo_inicio: int
    tiempo_finalizacion: int
    tiempo_retorno: int
    tiempo_espera: int
    tiempo_respuesta: int


@dataclass(frozen=True)
class InformeEstadistico:
    """Resumen completo de la simulacion."""

    procesos: List[EstadisticaProceso]
    retorno_promedio: float
    espera_promedio: float
    respuesta_promedio: float
    tiempo_total: int
    trabajos_terminados: int
    rendimiento: float


def calcular_estadisticas(
    procesos: Sequence[Proceso], tiempo_total: int
) -> InformeEstadistico:
    """Calcula retorno, espera, promedios y rendimiento de los terminados."""
    filas: List[EstadisticaProceso] = []
    for proceso in procesos:
        if proceso.estado != ESTADO_TERMINADO or proceso.tiempo_finalizacion is None:
            continue
        retorno = proceso.tiempo_finalizacion - proceso.tiempo_arribo
        filas.append(
            EstadisticaProceso(
                id=proceso.id,
                tiempo_arribo=proceso.tiempo_arribo,
                tiempo_irrupcion=proceso.tiempo_irrupcion,
                tiempo_inicio=proceso.tiempo_inicio,
                tiempo_finalizacion=proceso.tiempo_finalizacion,
                tiempo_retorno=retorno,
                tiempo_espera=retorno - proceso.tiempo_irrupcion,
                tiempo_respuesta=proceso.tiempo_inicio - proceso.tiempo_arribo,
            )
        )

    cantidad = len(filas)
    retorno_promedio = (
        sum(fila.tiempo_retorno for fila in filas) / cantidad if cantidad else 0.0
    )
    espera_promedio = (
        sum(fila.tiempo_espera for fila in filas) / cantidad if cantidad else 0.0
    )
    respuesta_promedio = (
        sum(fila.tiempo_respuesta for fila in filas) / cantidad if cantidad else 0.0
    )
    rendimiento = cantidad / tiempo_total if tiempo_total > 0 else 0.0

    return InformeEstadistico(
        procesos=filas,
        retorno_promedio=retorno_promedio,
        espera_promedio=espera_promedio,
        respuesta_promedio=respuesta_promedio,
        tiempo_total=tiempo_total,
        trabajos_terminados=cantidad,
        rendimiento=rendimiento,
    )


# ============================================================================
# 7. SALIDA DE TEXTO
# Salida de consola para los eventos y el estado observable del simulador.
# ============================================================================

def seleccionar_archivo_csv(directorio_inicial: Path) -> Optional[Path]:
    """Abre un explorador de archivos para elegir un CSV de procesos."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print(
            "No se pudo abrir el explorador: "
            "falta tkinter en esta instalacion de Python."
        )
        return None

    ventana = None
    try:
        ventana = tk.Tk()
        ventana.withdraw()
        ruta = filedialog.askopenfilename(
            parent=ventana,
            title="Seleccionar archivo CSV de procesos",
            initialdir=str(directorio_inicial),
            filetypes=(("Archivos CSV", "*.csv"), ("Todos los archivos", "*")),
        )
        return Path(ruta) if ruta else None
    except (tk.TclError, OSError):
        print(
            "No se pudo abrir el explorador. "
            "Verifique que haya un entorno grafico disponible."
        )
        return None
    finally:
        if ventana is not None:
            ventana.destroy()


def tabla_ascii(encabezados: Sequence[str], filas: Sequence[Sequence[object]]) -> str:
    """Construye una tabla ASCII apta para cualquier consola."""
    celdas = [[str(valor) for valor in fila] for fila in filas]
    anchos = [
        max([len(nombre)] + [len(fila[indice]) for fila in celdas])
        for indice, nombre in enumerate(encabezados)
    ]
    borde = "+" + "+".join("-" * (ancho + 2) for ancho in anchos) + "+"

    def formar_fila(valores: Sequence[str]) -> str:
        return "| " + " | ".join(
            f"{valor:<{ancho}}" for valor, ancho in zip(valores, anchos)
        ) + " |"

    lineas = [borde, formar_fila(encabezados), borde]
    lineas.extend(formar_fila(fila) for fila in celdas)
    lineas.append(borde)
    return "\n".join(lineas)


class PresentacionConsola:
    """Muestra instantaneas cuando ocurre un evento relevante.

    Los estados pertenecen a los procesos, las colas a admision y las
    particiones al gestor de memoria. Esta clase solo consulta esos datos.
    """

    def __init__(
        self,
        procesos: Sequence[Proceso],
        admision: AdministradorAdmision,
        memoria: GestorMemoria,
    ) -> None:
        self.procesos = procesos
        self.admision = admision
        self.memoria = memoria

    def mostrar_inicio(self, ruta_csv: Path) -> None:
        """Informa el archivo cargado antes del primer evento."""
        print(f"KernelFlow | Procesos cargados desde: {ruta_csv}")

    def mostrar_evento(self, evento: EventoPlanificador) -> None:
        """Imprime el evento y una instantanea del sistema en ese momento."""
        print("\n" + "-" * 60)
        print(f"t = {evento.tiempo} | {evento.detalle}")
        for linea in self.lineas_resumen(evento.tiempo):
            print(linea)
        print("PROCESOS:")
        print(self.tabla_procesos())
        print("TABLA DE PARTICIONES DE MEMORIA (KB):")
        print(self.tabla_memoria())

    def mostrar_fin(self, tiempo: int) -> None:
        """Cierra la salida y presenta el informe estadistico."""
        print("\n" + "-" * 60)
        print(f"Simulacion finalizada en t = {tiempo}.")
        print(f"Libre usuario: {self.memoria.memoria_libre_total()}K")
        print()
        for linea in self.lineas_informe(tiempo):
            print(linea)

    # ------------------------------------------------------------------
    # Construccion de contenido reutilizable por las distintas vistas.
    # ------------------------------------------------------------------

    def proceso_en_cpu(self) -> Optional[Proceso]:
        return next(
            (proceso for proceso in self.procesos if proceso.estado == ESTADO_EJECUCION),
            None,
        )

    def lineas_resumen(self, tiempo: int) -> List[str]:
        """Estado del procesador y de las colas en el instante actual."""
        en_cpu = self.proceso_en_cpu()
        if en_cpu is None:
            cpu = "CPU: OCIOSA"
        else:
            cpu = (
                f"CPU: {en_cpu.id} (T. restante: {en_cpu.tiempo_restante} ut "
                f"de {en_cpu.tiempo_irrupcion} ut de irrupcion)"
            )
        return [
            f"TIEMPO: {tiempo} ut   {cpu}",
            f"LISTO: {self._formatear_cola(self.admision.obtener_listos())}",
            "LISTO_SUSPENDIDO: "
            f"{self._formatear_cola(self.admision.obtener_listos_suspendidos())}",
        ]

    def tabla_procesos(self) -> str:
        filas = [
            (
                proceso.id,
                proceso.tamanio,
                proceso.tiempo_arribo,
                proceso.tiempo_irrupcion,
                proceso.tiempo_irrupcion - proceso.tiempo_restante,
                proceso.tiempo_restante,
                "L/SUSP."
                if proceso.estado == ESTADO_LISTO_SUSPENDIDO
                else proceso.estado,
            )
            for proceso in self.procesos
        ]
        return tabla_ascii(
            (
                "ID",
                "KB",
                "T. Arribo",
                "T. Irrupcion",
                "T. Ejecutado",
                "T. Restante",
                "Estado",
            ),
            filas,
        )

    def tabla_memoria(self) -> str:
        """Tabla de particiones exigida por la consigna.

        El ID de particion lo asigna memoria al crear cada particion y no
        cambia mientras exista (0 es el SO); los huecos libres se muestran
        con "-". En MVT cada particion se crea del tamanio exacto del
        proceso, por lo que la fragmentacion interna es siempre 0K.
        """
        resumen = self.memoria.obtener_resumen_memoria()
        particiones = [resumen["particion_so"], *resumen["particiones_usuario"]]
        filas = []
        for particion in particiones:
            if particion.libre:
                asignado, fragmentacion = "LIBRE", "-"
            else:
                asignado = particion.proceso_id
                fragmentacion = "-" if particion.proceso_id == "SO" else "0"
            filas.append(
                (
                    "-" if particion.numero is None else particion.numero,
                    particion.direccion_inicio,
                    particion.tamanio,
                    asignado,
                    fragmentacion,
                )
            )
        return tabla_ascii(
            ("ID Part.", "Inicio", "Tamanio", "Proceso", "Frag. Int."),
            filas,
        )

    def linea_memoria_libre(self) -> str:
        huecos = self.memoria.obtener_huecos()
        return (
            f"Libre usuario: {self.memoria.memoria_libre_total()}K en "
            f"{len(huecos)} hueco(s); mayor hueco: "
            f"{self.memoria.mayor_hueco_libre()}K"
        )

    def lineas_informe(self, tiempo: int) -> List[str]:
        """Informe estadistico final: retorno, espera, promedios y rendimiento."""
        informe = calcular_estadisticas(self.procesos, tiempo)
        return formatear_informe(informe).splitlines()

    @staticmethod
    def _formatear_ids(procesos: Sequence[Proceso]) -> str:
        return ", ".join(proceso.id for proceso in procesos) or "-"

    @staticmethod
    def _formatear_cola(procesos: Sequence[Proceso]) -> str:
        """Muestra cada proceso con su tiempo restante entre parentesis."""
        return ", ".join(
            f"{proceso.id}({proceso.tiempo_restante})" for proceso in procesos
        ) or "-"


def formatear_informe(informe: InformeEstadistico) -> str:
    """Convierte el informe estadistico en texto con tablas ASCII."""
    filas = [
        (
            fila.id,
            fila.tiempo_arribo,
            fila.tiempo_irrupcion,
            fila.tiempo_inicio,
            fila.tiempo_finalizacion,
            fila.tiempo_retorno,
            fila.tiempo_espera,
            fila.tiempo_respuesta,
        )
        for fila in informe.procesos
    ]
    filas.append(
        (
            "PROMEDIO",
            "",
            "",
            "",
            "",
            f"{informe.retorno_promedio:.2f}",
            f"{informe.espera_promedio:.2f}",
            f"{informe.respuesta_promedio:.2f}",
        )
    )
    lineas = [
        "INFORME ESTADISTICO FINAL",
        tabla_ascii(
            (
                "ID",
                "T. Arribo",
                "T. Irrupcion",
                "T. Inicio",
                "T. Finalizacion",
                "T. Retorno",
                "T. Espera",
                "T. Respuesta",
            ),
            filas,
        ),
        "T. Inicio    = primer instante en que el proceso usa la CPU",
        "T. Retorno   = T. Finalizacion - T. Arribo",
        "T. Espera    = T. Retorno - T. Irrupcion",
        "T. Respuesta = T. Inicio - T. Arribo",
        "",
        f"Tiempo de retorno promedio:   {informe.retorno_promedio:.2f} ut",
        f"Tiempo de espera promedio:    {informe.espera_promedio:.2f} ut",
        f"Tiempo de respuesta promedio: {informe.respuesta_promedio:.2f} ut",
        (
            f"Rendimiento del sistema: {informe.trabajos_terminados} trabajos / "
            f"{informe.tiempo_total} ut = {informe.rendimiento:.4f} "
            "trabajos por unidad de tiempo"
        ),
    ]
    return "\n".join(lineas)


# ============================================================================
# 8. MENU Y EJECUCION
# Punto de entrada, panel de texto y menu del simulador.
# ============================================================================

if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: data/ se distribuye junto al ejecutable.
    DIRECTORIO_PROYECTO = Path(sys.executable).resolve().parent
else:
    DIRECTORIO_PROYECTO = Path(__file__).resolve().parent
DIRECTORIO_DATOS = DIRECTORIO_PROYECTO / "data"
RUTA_CSV_PREDETERMINADA = DIRECTORIO_DATOS / "procesos_demo.csv"
RUTA_LOGO_UTN = DIRECTORIO_DATOS / "logo_utn.txt"


def ancho_terminal() -> int:
    """Obtiene el ancho disponible para presentar el contenido."""
    return shutil.get_terminal_size(fallback=(100, 24)).columns


def prefijo_centrado(texto: str) -> str:
    """Agrega espacios a la izquierda sin rellenar el final de la linea."""
    return " " * max(0, (ancho_terminal() - len(texto)) // 2) + texto


def imprimir_linea_centrada(texto: str) -> None:
    print(prefijo_centrado(texto))


def imprimir_bloque_centrado(lineas: Sequence[str]) -> None:
    """Centra un bloque conservando la alineacion interna de sus lineas."""
    if not lineas:
        return
    ancho_bloque = max(len(linea) for linea in lineas)
    margen = " " * max(0, (ancho_terminal() - ancho_bloque) // 2)
    for linea in lineas:
        print(margen + linea if linea else "")


class PanelTexto(PresentacionConsola):
    """Vista compacta para la ejecucion desde la terminal.

    Los datos siguen perteneciendo a admision, memoria y los procesos. El
    panel solo los consulta; no decide transiciones ni selecciona la CPU.
    """

    def __init__(
        self,
        procesos: Sequence[Proceso],
        admision: Admision,
        memoria: GestorMemoria,
    ) -> None:
        super().__init__(procesos, admision, memoria)
        self._interactivo = sys.stdout.isatty()

    def mostrar_inicio(self, ruta_csv: Path) -> None:
        ancho = ancho_terminal()
        print("#" * ancho)
        imprimir_linea_centrada("PROCESOS CARGADOS")
        print("#" * ancho)
        imprimir_linea_centrada(f"Archivo: {ruta_csv.name}")
        imprimir_linea_centrada(
            f"{len(self.procesos)} proceso(s) leido(s) correctamente. Todos "
            "comienzan en NUEVO y esperan su tiempo de arribo."
        )
        print()
        imprimir_bloque_centrado(self.tabla_procesos().splitlines())
        print()
        imprimir_bloque_centrado((
            "Memoria: 100K para el SO + 450K para usuario (MVT, Best-Fit).",
            "Planificacion: SRTF apropiativo. Multiprogramacion maxima: 5.",
        ))

    def mostrar_paso(
        self, eventos: Sequence[EventoPlanificador], tiempo: int, numero: int
    ) -> None:
        """Muestra juntos los cambios observados durante un avance del reloj."""
        ancho = ancho_terminal()
        print("\n\n" + "#" * ancho)
        imprimir_linea_centrada(
            f"COMIENZO DEL PASO {numero} | RELOJ: t = {tiempo} ut"
        )
        print("#" * ancho)
        print()
        imprimir_linea_centrada("EVENTOS DE ESTE PASO")
        lineas_eventos = []
        for evento in eventos:
            lineas_eventos.extend(textwrap.wrap(
                f"- t = {evento.tiempo} | {evento.detalle}",
                width=max(20, min(ancho - 8, 110)),
                subsequent_indent="    ",
            ))
        imprimir_bloque_centrado(lineas_eventos)
        print("-" * ancho)
        self._mostrar_resumen(tiempo)
        self._mostrar_tablas()
        print(f" FIN DEL PASO {numero} ".center(ancho, "="))

    def mostrar_fin(self, tiempo: int) -> None:
        ancho = ancho_terminal()
        print("\n" + "#" * ancho)
        imprimir_linea_centrada(f"SIMULACION FINALIZADA EN t = {tiempo} ut")
        print("#" * ancho)
        imprimir_linea_centrada(
            f"Memoria de usuario libre: {self.memoria.memoria_libre_total()}K."
        )
        print()
        imprimir_bloque_centrado(self.lineas_informe(tiempo))

    def _mostrar_resumen(self, tiempo: int) -> None:
        terminados = sum(
            proceso.estado == ESTADO_TERMINADO for proceso in self.procesos
        )
        resumen, listos, suspendidos = self.lineas_resumen(tiempo)
        imprimir_linea_centrada(resumen)
        imprimir_linea_centrada(
            f"TERMINADOS: {terminados}/{len(self.procesos)}   "
            "MULTIPROGRAMACION: "
            f"{self.admision.grado_multiprogramacion()}/"
            f"{GRADO_MAXIMO_MULTIPROGRAMACION}"
        )
        print()
        imprimir_linea_centrada(f"COLA {listos}")
        imprimir_linea_centrada(f"COLA {suspendidos}")
        imprimir_linea_centrada("(entre parentesis: tiempo restante en ut)")

    def _mostrar_tablas(self) -> None:
        tabla_procesos = self.tabla_procesos().splitlines()
        tabla_memoria = self.tabla_memoria().splitlines()
        ancho_procesos = len(tabla_procesos[0])
        ancho_memoria = len(tabla_memoria[0])
        ancho_disponible = ancho_terminal()

        print()
        if self._interactivo and ancho_procesos + ancho_memoria + 3 <= ancho_disponible:
            lineas = [
                "ESTADO DE LOS PROCESOS".ljust(ancho_procesos)
                + "   TABLA DE PARTICIONES (KB)"
            ]
            for izquierda, derecha in zip_longest(
                tabla_procesos, tabla_memoria, fillvalue=""
            ):
                lineas.append(f"{izquierda:<{ancho_procesos}}   {derecha}")
            imprimir_bloque_centrado(lineas)
        else:
            imprimir_linea_centrada("ESTADO DE LOS PROCESOS")
            imprimir_bloque_centrado(tabla_procesos)
            print()
            imprimir_linea_centrada("TABLA DE PARTICIONES (KB)")
            imprimir_bloque_centrado(tabla_memoria)

        imprimir_linea_centrada(self.linea_memoria_libre())


OPCIONES_MENU = (
    (
        "1",
        "Iniciar simulacion con el CSV de prueba",
        "Ejecuta data/procesos_demo.csv: 6 procesos que muestran apropiacion "
        "SRTF, un proceso en LISTO_SUSPENDIDO y la reutilizacion de memoria.",
    ),
    (
        "2",
        "Elegir otro archivo CSV",
        "Lista los lotes de prueba de la carpeta data/ y permite escribir la "
        "ruta de un archivo propio (hasta 10 procesos, formato: "
        "id,tamanio,arribo,irrupcion).",
    ),
    (
        "3",
        "Ver guia rapida",
        "Explica el formato del CSV, las reglas del simulador (MVT, Best-Fit, "
        "SRTF, multiprogramacion 5), los estados y los controles.",
    ),
    ("0", "Salir", "Cierra el simulador."),
)


def mostrar_menu() -> None:
    ancho = ancho_terminal()

    try:
        logo = RUTA_LOGO_UTN.read_text(encoding="utf-8").splitlines()
    except OSError:
        logo = []
    if logo:
        margen_logo = min(
            len(linea) - len(linea.lstrip()) for linea in logo if linea.strip()
        )
        imprimir_bloque_centrado([linea[margen_logo:] for linea in logo])

    print("=" * ancho)
    imprimir_linea_centrada("K E R N E L F L O W")
    imprimir_linea_centrada(
        "Simulador de planificacion SRTF y memoria MVT (Best-Fit)"
    )
    print("=" * ancho)
    imprimir_linea_centrada("GRUPO 15")
    imprimir_bloque_centrado((
        "BADER SORAIRE Cain Abel",
        "GONZALEZ Carlos Alfredo",
        "LEIVA ROMERO Agustin Nazareno",
        "SEELAFF Mauricio Guillermo",
        "TORRES Alejandro Valentin",
        "WOLKOWYSKI Braian Leonel",
        "ZURANO LANG Lucas Maximiliano",
    ))
    print("-" * ancho)
    lineas = []
    ancho_texto = max(30, min(ancho - 10, 72))
    for clave, titulo, descripcion in OPCIONES_MENU:
        lineas.append(f"[{clave}] {titulo}")
        lineas.extend(
            textwrap.wrap(
                descripcion,
                width=ancho_texto,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
        lineas.append("")
    imprimir_bloque_centrado(lineas[:-1])
    print("-" * ancho)


def mostrar_guia_rapida() -> None:
    """Explica la entrada, las reglas y la lectura de la simulacion."""
    guia = """
============================================================
  GUIA RAPIDA DE KERNELFLOW
============================================================
1. Preparar el archivo CSV
   Una fila representa un proceso. No escriba encabezados.
   Formato: id,tamanio,tiempo_arribo,tiempo_irrupcion
   Ejemplo: P1,120,0,8
   - id: nombre unico del proceso.
   - tamanio: memoria requerida en KB, entre 1 y 450.
   - tiempo_arribo: instante de llegada, desde 0.
   - tiempo_irrupcion: tiempo de irrupcion (rafaga), mayor que 0.
   Se admiten entre 1 y 10 procesos. Los numeros deben ser enteros.

2. Elegir como iniciar
   [1] Usa el CSV de prueba incluido en data/procesos_demo.csv.
   [2] Lista los CSV de la carpeta data/ para elegir uno por
       numero, o permite escribir la ruta de otro archivo.
   [3] Muestra esta guia.
   [0] Cierra el simulador.

3. Que hace el simulador
   - Reserva 100K para el sistema operativo y 450K para procesos.
   - MVT crea particiones variables. Best-Fit asigna el hueco libre
     mas pequeno donde entre cada proceso.
   - Pueden estar admitidos hasta 5 procesos al mismo tiempo
     (EJECUCION + LISTO + LISTO_SUSPENDIDO).
   - SRTF ejecuta el proceso LISTO con menor tiempo restante.
     Si llega otro mas corto, le quita la CPU (apropiacion).
   - Al terminar un proceso, libera su memoria y se vuelve a
     intentar el ingreso de los que esperan.

4. Como leer la pantalla
   Cada paso empieza con "COMIENZO DEL PASO" y termina con
   "FIN DEL PASO". Dentro de cada paso se listan todos los
   cambios de estado ocurridos (llegadas, admisiones,
   suspensiones, apropiaciones y finalizaciones) con su motivo.
   Luego se muestran la CPU, las colas LISTO y LISTO_SUSPENDIDO
   (con el tiempo restante entre parentesis), la tabla de
   procesos y la tabla de particiones de memoria.
   NUEVO espera su llegada o un cupo; LISTO espera la CPU;
   LISTO_SUSPENDIDO espera memoria; EJECUCION usa la CPU;
   TERMINADO ya completo su trabajo. La CPU puede estar OCIOSA.

5. Columnas de la tabla de procesos
   T. Irrupcion: tiempo total de CPU que necesita el proceso.
   T. Ejecutado: tiempo de CPU ya consumido.
   T. Restante: tiempo de CPU que le falta (lo usa SRTF).

6. Informe final
   Al terminar se muestran, por proceso, el tiempo de retorno
   (finalizacion - arribo), de espera (retorno - irrupcion) y de
   respuesta (primer uso de CPU - arribo), sus promedios y el
   rendimiento (trabajos terminados / tiempo total).

7. Controles durante la simulacion
   Espacio, Enter o N: ver el siguiente cambio relevante.
   Q: detener la simulacion y volver al menu.
   El reloj avanza internamente; no hace falta pulsar una tecla
   por cada unidad de tiempo.
============================================================"""
    imprimir_bloque_centrado(guia.strip("\n").splitlines())


def limpiar_pantalla() -> None:
    """Borra la pantalla (incluido el menu) al entrar en otra seccion."""
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def leer_tecla() -> str:
    """Lee una sola tecla sin esperar Enter, en Linux y en Windows."""
    if os.name == "nt":
        import msvcrt

        return msvcrt.getwch()

    import termios
    import tty

    descriptor = sys.stdin.fileno()
    configuracion_anterior = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, configuracion_anterior)


def esperar_avance() -> bool:
    """Espera una tecla; ``q`` permite volver al menu."""
    print(
        "\n" + prefijo_centrado(
            "[Espacio/Enter] siguiente cambio  [q] volver al menu: "
        ),
        end="",
        flush=True,
    )
    return esperar_tecla_avance()


def esperar_tecla_avance() -> bool:
    """Retorna ``True`` para avanzar y ``False`` si se pidio volver al menu."""
    while True:
        tecla = leer_tecla()
        if tecla in (" ", "\r", "\n", "n", "N"):
            print()
            return True
        if tecla in ("q", "Q", "", "\x1b"):
            print()
            return False


def contar_procesos(ruta: Path) -> str:
    """Cuenta las filas no vacias de un CSV para mostrarlas en la lista."""
    try:
        with ruta.open(encoding="utf-8-sig") as archivo:
            cantidad = sum(1 for linea in archivo if linea.strip())
    except (OSError, UnicodeDecodeError):
        return "no se puede leer"
    return f"{cantidad} proceso(s)"


def elegir_csv() -> Optional[Path]:
    """Muestra los CSV de data/ y permite elegir uno o escribir otra ruta.

    No depende de un entorno grafico; el explorador de archivos queda como
    opcion adicional para quien tenga tkinter disponible.
    """
    archivos = sorted(
        ruta for ruta in DIRECTORIO_DATOS.glob("*.csv") if ruta.is_file()
    )
    while True:
        limpiar_pantalla()
        ancho = ancho_terminal()
        print("=" * ancho)
        imprimir_linea_centrada("SELECCIONAR ARCHIVO CSV")
        print("=" * ancho)
        lineas = []
        if archivos:
            ancho_nombre = max(len(ruta.name) for ruta in archivos)
            for numero, ruta in enumerate(archivos, start=1):
                lineas.append(
                    f"[{numero}] {ruta.name:<{ancho_nombre}}  "
                    f"({contar_procesos(ruta)})"
                )
        else:
            lineas.append(f"No hay archivos CSV en {DIRECTORIO_DATOS}.")
        lineas.extend((
            "",
            "[R] Escribir la ruta de otro archivo CSV",
            "[E] Buscarlo con el explorador de archivos (requiere entorno grafico)",
            "[0] Volver al menu",
        ))
        imprimir_bloque_centrado(lineas)
        print("-" * ancho)

        opcion = input(prefijo_centrado("Opcion: ")).strip().lower()
        if opcion == "0":
            return None
        if opcion.isdigit() and 1 <= int(opcion) <= len(archivos):
            return archivos[int(opcion) - 1]
        if opcion == "r":
            texto = input(prefijo_centrado("Ruta del archivo CSV: "))
            ruta = Path(texto.strip().strip('"').strip("'")).expanduser()
            if ruta.is_file():
                return ruta
            imprimir_linea_centrada(f"No se encontro el archivo '{ruta}'.")
        elif opcion == "e":
            ruta = seleccionar_archivo_csv(DIRECTORIO_DATOS)
            if ruta is not None:
                return ruta
            imprimir_linea_centrada("No se selecciono ningun archivo.")
        else:
            imprimir_linea_centrada("Opcion no valida.")
        input(prefijo_centrado("Presione Enter para continuar..."))


def menu_interactivo() -> int:
    """Permite elegir el archivo y volver al menu tras la simulacion."""
    while True:
        limpiar_pantalla()
        mostrar_menu()
        try:
            opcion = input(prefijo_centrado("Opcion: ")).strip()
        except EOFError:
            return 0

        if opcion == "0":
            return 0
        if opcion == "1":
            ruta = RUTA_CSV_PREDETERMINADA
            limpiar_pantalla()
        elif opcion == "2":
            ruta = elegir_csv()
            if ruta is None:
                continue
            limpiar_pantalla()
        elif opcion == "3":
            limpiar_pantalla()
            mostrar_guia_rapida()
            input("\n" + prefijo_centrado("Presione Enter para volver al menu..."))
            continue
        else:
            imprimir_linea_centrada("Opcion no valida.")
            input(prefijo_centrado("Presione Enter para continuar..."))
            continue

        ejecutar_simulacion(ruta, modo_visual=True)
        input("\n" + prefijo_centrado("Presione Enter para volver al menu..."))


def crear_argumentos(argumentos: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Interpreta los argumentos de la aplicacion de consola."""
    analizador = argparse.ArgumentParser(
        description="Simulador de procesos con SRTF y memoria MVT Best-Fit."
    )
    analizador.add_argument(
        "archivo",
        nargs="?",
        type=Path,
        default=None,
        help="CSV de procesos (por defecto: data/procesos_demo.csv).",
    )
    return analizador.parse_args(argumentos)


def ejecutar_simulacion(ruta_csv: Path, modo_visual: bool = False) -> int:
    """Compone los modulos del simulador y ejecuta el ciclo principal."""
    try:
        procesos = cargar_procesos(ruta_csv)
    except ErrorCargaProcesos as error:
        imprimir_linea_centrada(f"Error: {error}")
        return 1

    memoria = GestorMemoria()
    try:
        admision = Admision(procesos, memoria)
    except ErrorAdmision as error:
        imprimir_linea_centrada(f"Error: {error}")
        return 1
    clase_presentacion = PanelTexto if modo_visual else PresentacionConsola
    presentacion = clase_presentacion(procesos, admision, memoria)

    presentacion.mostrar_inicio(ruta_csv)

    if modo_visual:
        eventos_paso = []
        planificador = PlanificadorSRTF(admision, memoria, eventos_paso.append)
        numero_paso = 0
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
        if interactivo:
            print(
                "\n" + prefijo_centrado(
                    "[Espacio/Enter] comenzar la simulacion  [q] volver al menu: "
                ),
                end="",
                flush=True,
            )
            if not esperar_tecla_avance():
                return 0
        while True:
            # Los eventos de una finalizacion en t (producidos al ejecutar la
            # unidad t-1) se muestran junto con los arribos del mismo t.
            if admision.hay_procesos_pendientes():
                planificador.procesar_instante()
            if eventos_paso:
                numero_paso += 1
                presentacion.mostrar_paso(
                    eventos_paso, planificador.reloj, numero_paso
                )
                eventos_paso.clear()
                if interactivo and admision.hay_procesos_pendientes():
                    if not esperar_avance():
                        imprimir_linea_centrada(
                            f"Simulacion detenida en t = {planificador.reloj}."
                        )
                        return 0
            if not admision.hay_procesos_pendientes():
                break
            planificador.ejecutar_unidad()
    else:
        planificador = PlanificadorSRTF(
            admision, memoria, presentacion.mostrar_evento
        )
        planificador.simular()

    presentacion.mostrar_fin(planificador.reloj)
    return 0


def main(argumentos: Optional[Sequence[str]] = None) -> int:
    """Ejecuta KernelFlow y retorna un codigo apto para la consola de Linux."""
    opciones = crear_argumentos(argumentos)
    try:
        if opciones.archivo is not None:
            return ejecutar_simulacion(opciones.archivo, modo_visual=True)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return menu_interactivo()
        return ejecutar_simulacion(RUTA_CSV_PREDETERMINADA, modo_visual=True)
    except (EOFError, KeyboardInterrupt):
        print()
        imprimir_linea_centrada("Simulacion interrumpida.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
