# =============================================================================
#  admision.py  -  ADMISION: COLAS, CUPO DE MULTIPROGRAMACION (5) Y SUSPENDIDOS
# -----------------------------------------------------------------------------
#  QUE HACE:  Es el "portero" del sistema. Decide QUIEN entra y A DONDE:
#               - Cuando llega un proceso (arribo), lo pone en NUEVO.
#               - Si hay CUPO (menos de 5 admitidos) intenta darle memoria:
#                    con hueco  -> LISTO
#                    sin hueco  -> LISTO_SUSPENDIDO
#               - Si NO hay cupo, se queda esperando en NUEVO.
#               - Cuando termina un proceso, reintenta a los suspendidos
#                 (primero) y despues a los NUEVO que esperaban cupo.
#             Ademas es el DUENO de las colas (listos, suspendidos, en
#             ejecucion) y el unico que llama a cambiar_estado().
#
#  LOS 3 PLANIFICADORES DE LA TEORIA (pregunta clasica):
#    - LARGO plazo   -> aca: procesar_arribos() + _admitir_nuevos()
#                       (deja entrar procesos al sistema, respeta el grado 5)
#    - MEDIANO plazo -> aca: reintentar_suspendidos() (+ la decision de
#                       mandar a LISTO_SUSPENDIDO en _intentar_cargar)
#    - CORTO plazo   -> NO esta aca: es planificador.py (SRTF)
#
#  LO USAN:   planificador.py -> procesar_arribos, reintentar_suspendidos,
#                                obtener_listos, enviar_a_ejecucion,
#                                devolver_a_listo, finalizar,
#                                extraer_transiciones, grado_multiprogramacion
#             presentacion.py -> obtener_listos, obtener_listos_suspendidos,
#                                grado_multiprogramacion
#             main.py         -> crea Admision y pregunta
#                                hay_procesos_pendientes() en cada vuelta
#  USA A:     memoria.py (asignar y consultas de huecos), estados.py
#             (cambiar_estado) y proceso.py (Proceso y nombres de estados).
#
#  REGLA DE ORO DEL GRADO DE MULTIPROGRAMACION:
#    grado = EJECUCION + LISTO + LISTO_SUSPENDIDO      (maximo 5)
#    Los NUEVO NO cuentan: todavia no fueron admitidos.
#    Los SUSPENDIDOS SI cuentan: ya fueron admitidos, solo les falta memoria.
# =============================================================================
"""Llegadas, colas y admision de procesos con grado maximo cinco."""

from dataclasses import dataclass
from typing import List, Optional, Sequence
# >> Sequence = "cualquier cosa recorrible en orden" (lista, tupla...).

from core.estados import cambiar_estado
from core.memoria import GestorMemoria
from core.proceso import (
    ESTADO_EJECUCION,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_NUEVO,
    ESTADO_TERMINADO,
    Proceso,
)


GRADO_MAXIMO_MULTIPROGRAMACION = 5
# >> El 5 de la consigna. Lo importa tambien presentacion.py para mostrar
#    "MULTIPROGRAMACION: 3/5". Si piden cambiarlo, se cambia SOLO aca.


class ErrorAdmision(ValueError):
    """Indica que la entrada no permite iniciar una simulacion valida."""
    # >> Un tipo de error propio. Hereda de ValueError (por eso va entre
    #    parentesis). main.py lo atrapa con "except ErrorAdmision" para
    #    mostrar "Error: ..." sin que el programa se cuelgue.


@dataclass(frozen=True)
class Transicion:
    """Registro de un intento de admision y su resultado.

    Si ``origen`` y ``destino`` coinciden, el proceso no cambio de estado
    (por ejemplo, un suspendido que todavia no entra en memoria) y ``motivo``
    explica por que.
    """
    # >> Es una "anotacion en la libreta": cada vez que admision intenta
    #    cargar un proceso, deja escrito QUE paso y POR QUE. Despues el
    #    planificador lee la libreta (extraer_transiciones) y arma los
    #    mensajes que se ven en pantalla.
    # >> Admision NO imprime nada; solo anota. Asi la logica queda separada
    #    de la pantalla.

    proceso: Proceso
    origen: str
    # >> Estado de donde venia (NUEVO o LISTO_SUSPENDIDO).
    destino: str
    # >> Estado al que paso (LISTO o LISTO_SUSPENDIDO).
    motivo: str
    # >> Texto explicativo, ej: "Best-Fit crea la particion 2 de 60K en ..."
    #    o "requiere 200K; hay 250K libres pero el mayor hueco ... (fragmentacion externa)".


class Admision:
    """Administra el cupo, la residencia en memoria y las colas de procesos.

    Los arribos se atienden por tiempo y, ante empate, por orden de entrada.
    Cuando se libera memoria, los suspendidos se reintentan en orden FIFO antes
    de admitir procesos NUEVO que esperan un cupo de multiprogramacion.
    """

    def __init__(self, procesos: Sequence[Proceso], memoria: GestorMemoria) -> None:
        # >> Se crea UNA vez en main.ejecutar_simulacion:
        #    admision = Admision(procesos, memoria)
        # >> Recibe la lista de procesos del CSV y EL MISMO gestor de memoria
        #    que despues usa el planificador (comparten el objeto).
        self.procesos = list(procesos)
        # >> Copia de TODOS los procesos (no se saca ninguno nunca). Se usa
        #    para hay_procesos_pendientes().
        self.memoria = memoria
        self._sin_arribar = sorted(
            enumerate(self.procesos),
            key=lambda item: (item[1].tiempo_arribo, item[0]),
        )
        # >> "Agenda de llegadas": los procesos que TODAVIA NO llegaron,
        #    ordenados por tiempo de arribo.
        # >> enumerate(...) arma pares (posicion_en_el_csv, proceso):
        #    [(0, P1), (1, P2), (2, P3) ...]
        # >> sorted(..., key=...) ordena segun lo que devuelve la "key".
        #    lambda item: (...) es una funcion chiquita sin nombre que, para
        #    cada par, devuelve (tiempo_arribo, posicion).
        #    => ordena por ARRIBO y, si dos llegan al mismo tiempo, respeta
        #       el ORDEN DEL CSV (item[0]).
        self._nuevos_pendientes: List[Proceso] = []
        # >> COLA NUEVO: ya llegaron pero NO tienen cupo (habia 5 admitidos).
        self._listos: List[Proceso] = []
        # >> COLA LISTO: admitidos y con memoria. De aca elige SRTF.
        self._suspendidos: List[Proceso] = []
        # >> COLA LISTO_SUSPENDIDO: admitidos SIN memoria. Orden FIFO.
        self._en_ejecucion: Optional[Proceso] = None
        # >> El proceso que esta en la CPU (o None si la CPU esta libre).
        #    Admision lo guarda para poder contar el grado.
        self._transiciones: List[Transicion] = []
        # >> LA LIBRETA: lista de Transicion que despues lee el planificador.

        # --- Validaciones de seguridad (carga.py ya filtro todo esto; es
        #     una segunda red por si alguien crea Admision a mano) ----------
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
                # >> Un proceso de mas de 450K quedaria suspendido PARA
                #    SIEMPRE y la simulacion nunca terminaria. Por eso se
                #    rechaza antes de empezar.

    # =========================================================================
    #  PLANIFICADOR DE LARGO PLAZO
    # =========================================================================
    def procesar_arribos(self, tiempo: int) -> List[Proceso]:
        """Registra los arribos hasta ``tiempo`` y admite los que tienen cupo."""
        # >> LA LLAMA: planificador.procesar_instante() en CADA instante t,
        #    y planificador._finalizar() cuando termina un proceso.
        # >> ENTRA: el instante actual t (el reloj).
        # >> SALE:  la lista de procesos que llegaron en este t (para que el
        #           planificador muestre "P3 llega y pasa a ...").
        arribados: List[Proceso] = []
        while self._sin_arribar and self._sin_arribar[0][1].tiempo_arribo <= tiempo:
            # >> Mientras la agenda no este vacia Y el primero de la agenda
            #    ya tenga que haber llegado (arribo <= t)...
            # >> [0] = primer par de la agenda; [1] = el proceso del par.
            _, proceso = self._sin_arribar.pop(0)
            # >> .pop(0) SACA el primer elemento y lo devuelve.
            #    "_" descarta la posicion del CSV, ya no hace falta.
            self._nuevos_pendientes.append(proceso)
            # >> Pasa a la cola de NUEVO (sigue en estado NUEVO).
            arribados.append(proceso)
        self._admitir_nuevos()
        # >> Ahora que llegaron, se intenta admitirlos (si hay cupo).
        return arribados

    def extraer_transiciones(self) -> List[Transicion]:
        """Retorna y vacia las transiciones de admision registradas."""
        # >> "Leer y borrar la libreta". El planificador la llama justo
        #    despues de procesar_arribos o reintentar_suspendidos para saber
        #    que paso y armar los mensajes.
        transiciones = self._transiciones
        self._transiciones = []
        # >> Se entrega la lista vieja y se empieza una vacia, asi la
        #    proxima vez no se repiten mensajes.
        return transiciones

    # --- Consultas de las colas (devuelven COPIAS) ---------------------------

    def obtener_nuevos(self) -> List[Proceso]:
        """Retorna los procesos en NUEVO, incluidos los que aun no arribaron."""
        return list(self._nuevos_pendientes) + [
            proceso for _, proceso in self._sin_arribar
        ]
        # >> Los que esperan cupo + los que ni llegaron todavia (ambos estan
        #    en estado NUEVO). La usa la interfaz con colores.

    def obtener_listos(self) -> List[Proceso]:
        """Retorna una copia de la cola LISTO en su orden actual."""
        return list(self._listos)
        # >> LA USA el planificador para elegir con SRTF, y presentacion
        #    para mostrar "LISTO: P2(3), P4(5)".

    def obtener_listos_suspendidos(self) -> List[Proceso]:
        """Retorna una copia de la cola LISTO_SUSPENDIDO en orden FIFO."""
        return list(self._suspendidos)

    def grado_multiprogramacion(self) -> int:
        """Cuenta EJECUCION, LISTO y LISTO_SUSPENDIDO."""
        return len(self._listos) + len(self._suspendidos) + int(
            self._en_ejecucion is not None
        )
        # >> len() = cantidad de elementos de la lista.
        # >> int(True) = 1, int(False) = 0  -> suma 1 si hay alguien en CPU.
        # >> EJEMPLO: 1 en CPU + 2 en LISTO + 2 suspendidos = 5 -> lleno.
        # >> PREGUNTA: "Por que cuentan los suspendidos?"
        #    RESPUESTA: porque ya fueron admitidos al sistema (pasaron el
        #    planificador de largo plazo); solo esperan memoria. Si no los
        #    contaramos, podriamos tener mas de 5 procesos admitidos.

    # --- Movimientos que pide el PLANIFICADOR (corto plazo) ------------------

    def enviar_a_ejecucion(self, proceso: Proceso) -> None:
        """Mueve un proceso LISTO a la CPU seleccionada por el planificador."""
        # >> LA LLAMA: planificador._asignar_cpu() y _reevaluar_cpu().
        #    El planificador DECIDE quien; admision EJECUTA el movimiento.
        if self._en_ejecucion is not None:
            raise ValueError("La CPU ya tiene un proceso en EJECUCION.")
            # >> Hay UNA sola CPU: nunca puede haber dos en ejecucion.
        if proceso not in self._listos:
            raise ValueError(f"El proceso '{proceso.id}' no esta en LISTO.")
        cambiar_estado(proceso, ESTADO_EJECUCION)       # LISTO -> EJECUCION
        self._listos.remove(proceso)                     # sale de la cola LISTO
        self._en_ejecucion = proceso                     # ocupa la CPU

    def devolver_a_listo(self, proceso: Proceso) -> None:
        """Devuelve a LISTO el proceso cuya CPU fue apropiada."""
        # >> LA LLAMA: planificador._reevaluar_cpu() cuando hay APROPIACION.
        if proceso is not self._en_ejecucion:
            raise ValueError(f"El proceso '{proceso.id}' no esta en EJECUCION.")
            # >> "is not" compara si es EL MISMO objeto (no solo igual).
        cambiar_estado(proceso, ESTADO_LISTO)            # EJECUCION -> LISTO
        self._en_ejecucion = None
        self._listos.append(proceso)
        # >> Vuelve al final de la cola LISTO, CONSERVANDO su memoria
        #    (sigue con su particion; no se libera nada).

    def finalizar(self, proceso: Proceso) -> None:
        """Pasa a TERMINADO el proceso que completo su tiempo de CPU."""
        # >> LA LLAMA: planificador._finalizar().
        # >> OJO: aca NO se libera la memoria. Eso lo hace el planificador
        #    llamando a memoria.liberar() justo despues.
        if proceso is not self._en_ejecucion:
            raise ValueError(f"El proceso '{proceso.id}' no esta en EJECUCION.")
        cambiar_estado(proceso, ESTADO_TERMINADO)        # EJECUCION -> TERMINADO
        self._en_ejecucion = None
        # >> Al quedar la CPU en None, el grado baja en 1: se libera un CUPO.

    # =========================================================================
    #  PLANIFICADOR DE MEDIANO PLAZO
    # =========================================================================
    def reintentar_suspendidos(self) -> List[Proceso]:
        """Reintenta suspendidos y ocupa cupos liberados con procesos NUEVO."""
        # >> LA LLAMA: planificador._finalizar(), justo DESPUES de liberar la
        #    memoria del proceso que termino.
        # >> PREGUNTA: "Por que se reintenta solo cuando termina un proceso?"
        #    RESPUESTA: porque es el UNICO momento en que se libera memoria.
        #    En cualquier otro instante el suspendido seguiria sin entrar.
        admitidos: List[Proceso] = []
        for proceso in list(self._suspendidos):
            # >> Se recorre una COPIA (list(...)) porque adentro del for se
            #    SACAN elementos de la lista original; recorrer la original
            #    mientras se modifica saltearia elementos.
            # >> ORDEN FIFO: el primero que se suspendio es el primero que se
            #    reintenta.
            if self._intentar_cargar(proceso, ESTADO_LISTO_SUSPENDIDO):
                self._suspendidos.remove(proceso)
                self._listos.append(proceso)
                admitidos.append(proceso)
                # >> Entro en memoria: LISTO_SUSPENDIDO -> LISTO.
            # >> Si no entra, NO se corta el for: se sigue probando con el
            #    siguiente. Asi un suspendido chico que esta atras puede
            #    entrar aunque el primero (grande) no entre.
        admitidos.extend(self._admitir_nuevos())
        # >> Despues de los suspendidos, se llenan los cupos libres con los
        #    NUEVO que esperaban (el que termino libero un cupo).
        # >> ORDEN IMPORTANTE: primero suspendidos, despues nuevos. Los
        #    suspendidos ya estaban admitidos; tienen prioridad.
        return admitidos

    def hay_procesos_pendientes(self) -> bool:
        """Indica si falta completar al menos un proceso de la entrada."""
        return any(proceso.estado != ESTADO_TERMINADO for proceso in self.procesos)
        # >> True si al menos uno NO termino. main.py lo usa como condicion
        #    para seguir el ciclo de la simulacion.

    # =========================================================================
    #  FUNCIONES INTERNAS (las usan solo los metodos de arriba)
    # =========================================================================
    def _admitir_nuevos(self) -> List[Proceso]:
        # >> Toma procesos de la cola NUEVO mientras haya cupo (< 5).
        # >> LA LLAMAN: procesar_arribos() y reintentar_suspendidos().
        admitidos: List[Proceso] = []
        while (
            self._nuevos_pendientes
            and self.grado_multiprogramacion() < GRADO_MAXIMO_MULTIPROGRAMACION
        ):
            # >> Condicion doble: que haya alguien esperando Y que haya cupo.
            #    Se recalcula el grado en cada vuelta porque va cambiando.
            proceso = self._nuevos_pendientes.pop(0)
            # >> FIFO: sale el primero que llego.
            if self._intentar_cargar(proceso, ESTADO_NUEVO):
                self._listos.append(proceso)
                admitidos.append(proceso)
                # >> Hubo hueco: NUEVO -> LISTO.
            else:
                self._suspendidos.append(proceso)
                # >> No hubo hueco: NUEVO -> LISTO_SUSPENDIDO.
                # >> CLAVE: igual OCUPA UN CUPO (los suspendidos cuentan).
        return admitidos
        # >> Si el while corta porque grado == 5, los que quedan en
        #    _nuevos_pendientes siguen en NUEVO esperando cupo. El planificador
        #    muestra: "P6 llega y permanece en NUEVO (sin cupo ...)".

    def _intentar_cargar(self, proceso: Proceso, origen: str) -> bool:
        """Intenta asignar memoria Best-Fit y registra el resultado.

        Retorna ``True`` si el proceso paso a LISTO. Si no hay hueco, un
        proceso NUEVO pasa a LISTO_SUSPENDIDO y uno suspendido permanece alli.
        """
        # >> ENTRA: el proceso y de que estado viene (NUEVO o LISTO_SUSPENDIDO).
        # >> SALE:  True si consiguio memoria, False si no.
        # >> Ademas anota una Transicion en la libreta con el motivo.

        # PASO 1: "foto" de la memoria ANTES de asignar (para el mensaje).
        mayor_hueco = self.memoria.mayor_hueco_libre()
        libre_total = self.memoria.memoria_libre_total()
        huecos = [hueco.tamanio for hueco in self.memoria.obtener_huecos()]
        # >> Se toma antes porque si asignar() tiene exito, los huecos cambian.

        # PASO 2: pedirle a memoria un hueco con Best-Fit.
        particion = self.memoria.asignar(proceso)

        # PASO 3a: CONSIGUIO MEMORIA -> LISTO
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
                # >> Si habia varios huecos, el mensaje los lista para que se
                #    vea que se eligio el MAS CHICO donde entraba (Best-Fit).
            self._transiciones.append(
                Transicion(proceso, origen, ESTADO_LISTO, motivo)
            )
            return True

        # PASO 3b: NO CONSIGUIO MEMORIA -> armar el motivo
        if libre_total >= proceso.tamanio:
            motivo = (
                f"requiere {proceso.tamanio}K; hay {libre_total}K libres pero "
                f"el mayor hueco contiguo es de {mayor_hueco}K "
                "(fragmentacion externa)"
            )
            # >> FRAGMENTACION EXTERNA: en TOTAL alcanza, pero repartido en
            #    huecos separados, y en ninguno entra entero.
            #    Ej.: pide 200K, libres 150K + 100K = 250K, pero no hay 200K juntos.
        else:
            motivo = (
                f"requiere {proceso.tamanio}K y solo hay {libre_total}K libres"
            )
            # >> Simplemente no alcanza la memoria libre total (no es
            #    fragmentacion: esta todo ocupado).
        if origen != ESTADO_LISTO_SUSPENDIDO:
            cambiar_estado(proceso, ESTADO_LISTO_SUSPENDIDO)
            # >> Si venia de NUEVO: NUEVO -> LISTO_SUSPENDIDO.
            # >> Si ya era suspendido, NO se llama a cambiar_estado: el
            #    diagrama no tiene LISTO_SUSPENDIDO -> LISTO_SUSPENDIDO y daria
            #    error. Simplemente se queda donde estaba.
        self._transiciones.append(
            Transicion(proceso, origen, ESTADO_LISTO_SUSPENDIDO, motivo)
        )
        # >> Si origen == destino (suspendido que sigue suspendido), el
        #    planificador lo muestra como "P4 permanece en LISTO_SUSPENDIDO (...)".
        return False
        # >> Ojo: quien mete al proceso en la cola _suspendidos es
        #    _admitir_nuevos (si venia de NUEVO). Si ya estaba suspendido,
        #    ya esta en la cola y se queda.
