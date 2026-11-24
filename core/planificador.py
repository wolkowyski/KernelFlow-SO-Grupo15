# =============================================================================
#  planificador.py  -  LA CPU: PLANIFICACION SRTF APROPIATIVA Y EL RELOJ
# -----------------------------------------------------------------------------
#  QUE HACE:  Es el PLANIFICADOR DE CORTO PLAZO y el DUENO DEL RELOJ.
#               - Elige quien usa la CPU con SRTF (Shortest Remaining Time
#                 First): gana el de MENOR TIEMPO RESTANTE.
#               - Es APROPIATIVO: si llega uno con menos restante que el que
#                 esta en CPU, se la saca (apropiacion).
#               - Avanza el reloj de a 1 unidad de tiempo (ut).
#               - Cuando un proceso termina: libera su memoria y le pide a
#                 admision que reintente suspendidos y nuevos.
#               - NO IMPRIME NADA: "emite eventos" (patron Observador) que
#                 main.py junta en una lista y presentacion.py muestra.
#  LO USA:    main.py (crea el PlanificadorSRTF y llama a procesar_instante
#             y ejecutar_unidad en el ciclo). presentacion.py importa
#             EventoPlanificador solo para saber que tipo de dato muestra.
#  USA A:     admision.py (colas y movimientos), memoria.py (liberar al
#             terminar), proceso.py (Proceso y ESTADO_NUEVO).
#
#  CONVENCION DE TIEMPO
#    Una unidad que se ejecuta "en t" termina "en t+1". Si P1 entra a la CPU
#    en t=0 con irrupcion 3, ejecuta en t=0, 1, 2 y TERMINA EN t=3.
#
#  DESEMPATES:
#    - Si el que esta en CPU EMPATA con el mejor de LISTO -> SIGUE el actual
#      (no se hace un cambio de contexto inutil). Es el "<=" de _reevaluar_cpu.
#    - Si la CPU esta libre: menor restante; si empatan, menor arribo; si
#      empatan, menor ID.
# =============================================================================
"""Planificacion apropiativa SRTF y reloj discreto de la simulacion."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence
# >> Callable[[X], None] = "una funcion que recibe un X y no devuelve nada".

from core.admision import Admision, Transicion
from core.memoria import GestorMemoria
from core.proceso import ESTADO_NUEVO, Proceso


# --- Tipos de evento: etiquetas para cada cosa que puede pasar --------------
TIPO_INICIO = "INICIO_EJECUCION"            # un proceso entra a la CPU libre
TIPO_ARRIBO = "ARRIBO"                      # llega un proceso
TIPO_APROPIACION = "APROPIACION"            # uno le saca la CPU a otro
TIPO_FINALIZACION = "FINALIZACION"          # un proceso termina
TIPO_CPU_OCIOSA = "CPU_OCIOSA"              # no hay nadie para ejecutar
TIPO_MEMORIA_LIBERADA = "MEMORIA_LIBERADA"  # se libera la particion del que termino
TIPO_NUEVA_ADMISION = "NUEVA_ADMISION"      # un suspendido/nuevo pasa a LISTO
TIPO_SIGUE_SUSPENDIDO = "SIGUE_SUSPENDIDO"  # un suspendido sigue sin entrar


@dataclass(frozen=True)
class EventoPlanificador:
    """Describe un cambio relevante producido por el planificador."""
    # >> Cada "renglon" que despues aparece en "EVENTOS DE ESTE PASO".
    #    Ej.: EventoPlanificador(tiempo=4, tipo="APROPIACION",
    #         proceso_id="P3", detalle="P3 apropia la CPU a P1: ...")

    tiempo: int
    tipo: str
    proceso_id: Optional[str] = None
    detalle: str = ""
    # >> "detalle" es el texto ya armado que imprime presentacion.


ObservadorEventos = Callable[[EventoPlanificador], None]
# >> Un "alias" de tipo: le da nombre a "funcion que recibe un evento".
#    En main.py se pasa eventos_paso.append: cada evento emitido se AGREGA
#    a la lista eventos_paso (la "libreta" de main).


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
        admision: Admision,
        memoria: GestorMemoria,
        observador: Optional[ObservadorEventos] = None,
    ) -> None:
        # >> Se crea en main.ejecutar_simulacion:
        #    planificador = PlanificadorSRTF(admision, memoria, eventos_paso.append)
        self.admision = admision
        self.memoria = memoria
        # >> Los MISMOS objetos que creo main (compartidos con presentacion).
        self.observador = observador
        # >> La funcion a la que le "avisa" cada evento (eventos_paso.append).
        self.reloj = 0
        # >> EL RELOJ DE LA SIMULACION. Arranca en t=0. Solo lo modifica
        #    ejecutar_unidad() (de a +1).
        self.proceso_en_ejecucion: Optional[Proceso] = None
        # >> Quien tiene la CPU ahora (None = CPU libre).
        self.cambios_contexto = 0
        # >> Contador: cuantas veces se cargo un proceso en la CPU
        #    (incluye la primera vez y las apropiaciones).
        self._cpu_ociosa_informada = False
        # >> Bandera para avisar "CPU ociosa" UNA sola vez y no repetirlo en
        #    cada instante que sigue ociosa.

    @staticmethod
    def seleccionar_srtf(procesos: Sequence[Proceso]) -> Optional[Proceso]:
        """Selecciona en forma determinista el proceso con menor tiempo restante."""
        # >> LA REGLA SRTF EN SI. Recibe la cola LISTO y devuelve el elegido.
        # >> @staticmethod: no usa self; es una funcion pura de "elegir".
        if not procesos:
            return None
            # >> Cola LISTO vacia -> nadie para elegir.

        for proceso in procesos:
            if proceso.tiempo_restante is None or proceso.tiempo_restante <= 0:
                raise ValueError(
                    f"El proceso '{proceso.id}' no tiene tiempo restante positivo."
                )
                # >> Control de seguridad: en LISTO nunca deberia haber uno
                #    con 0 restante (ya habria terminado).

        return min(
            procesos,
            key=lambda proceso: (
                proceso.tiempo_restante,
                proceso.tiempo_arribo,
                proceso.id,
            ),
        )
        # >> min(..., key=...) devuelve el proceso cuya "key" es la menor.
        #    La key es una tupla, y las tuplas se comparan de izquierda a
        #    derecha:  1) menor tiempo_restante  (ESTO ES SRTF)
        #              2) si empatan, menor tiempo_arribo (el que llego antes)
        #              3) si tambien empatan, menor id
        # >> "Determinista" = con la misma entrada, SIEMPRE elige lo mismo.

    # =========================================================================
    #  LAS 2 FUNCIONES QUE LLAMA main.py EN CADA VUELTA DEL CICLO
    # =========================================================================
    def procesar_instante(self) -> None:
        """Atiende los arribos del instante actual y reevalua la CPU (SRTF).

        No avanza el reloj: luego de llamarlo, el estado observable es el del
        instante ``self.reloj``.
        """
        # >> "Que pasa en este instante t?" (sin mover el reloj)
        arribados = self.admision.procesar_arribos(self.reloj)
        # >> 1) Llegadas de t: admision los pone en NUEVO / LISTO / SUSPENDIDO.
        self._informar_arribos(arribados, self.admision.extraer_transiciones())
        # >> 2) Lee la libreta de admision y emite los eventos de llegada.
        self._reevaluar_cpu()
        # >> 3) SRTF: con la cola LISTO actualizada, decide si hay que
        #       asignar la CPU o apropiarla.
        if self.proceso_en_ejecucion is None:
            self._informar_cpu_ociosa()
            # >> 4) Si despues de todo nadie tiene la CPU -> ociosa.

    def ejecutar_unidad(self) -> None:
        """Ejecuta una unidad de CPU y avanza el reloj de ``t`` a ``t + 1``.

        Si el proceso termina, se informa en ``t + 1`` junto con la liberacion
        de memoria, las nuevas admisiones y el siguiente proceso en CPU.
        """
        # >> "Pasa 1 unidad de tiempo".
        if self.proceso_en_ejecucion is None:
            self.reloj += 1
            return
            # >> CPU ociosa: solo avanza el reloj (esperando proximo arribo).

        self._cpu_ociosa_informada = False
        # >> Hay alguien en CPU: si despues vuelve a quedar ociosa, se avisara
        #    de nuevo.
        proceso = self.proceso_en_ejecucion
        if proceso.tiempo_inicio is None:
            proceso.tiempo_inicio = self.reloj
            # >> PRIMERA VEZ que este proceso usa la CPU -> se anota el
            #    instante (sirve para el tiempo de RESPUESTA).
            #    Si despues lo apropian y vuelve, no se pisa (ya no es None).

        proceso.tiempo_restante -= 1
        # >> Ejecuto 1 ut: le falta 1 menos.
        self.reloj += 1
        # >> El reloj pasa de t a t+1.

        if proceso.tiempo_restante == 0:
            self._finalizar(proceso)
            # >> Si llego a 0, TERMINA en t+1 (el reloj ya avanzado).

    # =========================================================================
    #  FUNCIONES INTERNAS
    # =========================================================================
    def _reevaluar_cpu(self) -> None:
        # >> EL CORAZON DE LA APROPIACION. Se llama en CADA instante desde
        #    procesar_instante().
        listos = list(self.admision.obtener_listos())
        elegido = self.seleccionar_srtf(listos)
        # >> El "mejor" de la cola LISTO segun SRTF (o None si esta vacia).
        actual = self.proceso_en_ejecucion
        # >> El que esta en la CPU ahora (o None).

        # --- CASO 1: la CPU esta OCUPADA -> hay que apropiar? ---------------
        if actual is not None:
            if elegido is None or actual.tiempo_restante <= elegido.tiempo_restante:
                return
                # >> NO se apropia si: no hay nadie en LISTO, o el actual
                #    tiene MENOR O IGUAL restante que el mejor de LISTO.
                # >> ESTE "<=" ES EL DESEMPATE: en empate, SIGUE el actual.
                #    Si fuera "<", en empate se haria un cambio de contexto
                #    que no gana nada.

            # >> Si llegamos aca: elegido tiene ESTRICTAMENTE menos restante.
            #    => APROPIACION.
            self.admision.devolver_a_listo(actual)
            # >> El actual: EJECUCION -> LISTO (conserva su memoria).
            self.admision.enviar_a_ejecucion(elegido)
            # >> El elegido: LISTO -> EJECUCION.
            # >> El ORDEN importa: primero se libera la CPU, despues se ocupa
            #    (enviar_a_ejecucion da error si la CPU ya esta ocupada).
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

        # --- CASO 2: la CPU esta LIBRE -> se la doy al mejor ------------------
        if elegido is not None:
            self._asignar_cpu(elegido)
            self._informar_inicio(elegido)

    def _asignar_cpu(self, proceso: Proceso) -> None:
        """Ocupa una CPU libre con un proceso LISTO en el mismo instante."""
        self.admision.enviar_a_ejecucion(proceso)
        self.proceso_en_ejecucion = proceso
        self.cambios_contexto += 1

    def _finalizar(self, proceso: Proceso) -> None:
        # >> LA LLAMA: ejecutar_unidad() cuando tiempo_restante llega a 0.
        # >> Es la funcion que CONECTA TODO: CPU + memoria + admision.
        # >> ORDEN: terminar -> liberar memoria ->
        #    reintentar suspendidos -> arribos de este t -> SRTF elige al
        #    siguiente. Todo en el MISMO instante, sin dejar la CPU ociosa.

        # 1) El proceso TERMINA.
        proceso.tiempo_finalizacion = self.reloj
        # >> Se anota el instante de fin (para el tiempo de RETORNO).
        self.admision.finalizar(proceso)
        # >> EJECUCION -> TERMINADO; libera un CUPO de multiprogramacion.
        self.proceso_en_ejecucion = None

        # 2) Se LIBERA su memoria.
        particion = self.memoria.obtener_asignacion(proceso)
        # >> Se guarda la particion ANTES de liberarla para el mensaje.
        memoria_liberada = self.memoria.liberar(proceso)
        # >> La particion pasa a hueco y se fusiona con huecos vecinos.
        libre_tras_liberar = self.memoria.memoria_libre_total()

        # 3) MEDIANO PLAZO: con la memoria nueva, reintentar suspendidos
        #    (y llenar cupos con los NUEVO que esperaban).
        self.admision.reintentar_suspendidos()
        transiciones_reintento = self.admision.extraer_transiciones()

        # 4) LARGO PLAZO: los que llegan justo en este instante.
        # Los arribos de este mismo instante participan de la eleccion SRTF.
        arribados = self.admision.procesar_arribos(self.reloj)
        transiciones_arribo = self.admision.extraer_transiciones()
        # >> Como se hace DESPUES de los reintentos, los suspendidos tienen
        #    prioridad sobre los que recien llegan.

        # 5) CORTO PLAZO: SRTF elige al siguiente en el mismo instante.
        siguiente = self.seleccionar_srtf(self.admision.obtener_listos())
        if siguiente is not None:
            self._asignar_cpu(siguiente)

        # 6) Recien ahora se EMITEN los eventos, en el orden en que pasaron.
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
            # >> "P4 pasa de LISTO_SUSPENDIDO a LISTO (...)" o
            #    "P5 permanece en LISTO_SUSPENDIDO (...)".

        self._informar_arribos(arribados, transiciones_arribo)

        if siguiente is not None:
            self._informar_inicio(siguiente)

    # --- Funciones que solo ARMAN MENSAJES (no cambian el estado) ------------

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
        transiciones: Sequence[Transicion],
    ) -> None:
        """Informa cada arribo junto con el estado al que pasa y el motivo."""
        # >> Junta cada proceso que LLEGO con lo que le paso en admision,
        #    para escribir UN solo renglon: "P3 llega y pasa a LISTO (...)".
        ids_arribados = {proceso.id for proceso in arribados}
        # >> {...} con "for" adentro = "set comprehension": conjunto de IDs.
        por_proceso: Dict[str, Transicion] = {}
        # >> id -> transicion de ese proceso que acaba de llegar.
        otras: List[Transicion] = []
        # >> Transiciones de procesos que NO llegaron ahora (ej. un NUEVO que
        #    esperaba cupo desde antes y recien ahora entra).
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
                # >> Llego pero NO tiene transicion = admision no lo intento
                #    cargar = NO HABIA CUPO (ya hay 5). Se queda en NUEVO.
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
                # >> destino = LISTO o LISTO_SUSPENDIDO; motivo = el texto
                #    de Best-Fit o de falta de memoria que armo admision.
            self._emitir(TIPO_ARRIBO, proceso, detalle)

        for transicion in otras:
            self._informar_transicion(transicion)

    def _informar_transicion(self, transicion: Transicion) -> None:
        proceso = transicion.proceso
        if transicion.origen == transicion.destino:
            # >> origen == destino: era suspendido y SIGUE suspendido.
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
            # >> Se avisa una vez; mientras siga ociosa no se repite.

    def _emitir(
        self,
        tipo: str,
        proceso: Optional[Proceso] = None,
        detalle: str = "",
    ) -> None:
        # >> PATRON OBSERVADOR: el planificador no sabe QUIEN escucha ni como
        #    se muestra. Solo arma el evento y se lo pasa al observador.
        #    En main, el observador es eventos_paso.append -> el evento se
        #    agrega a la lista y despues presentacion.mostrar_paso() la imprime.
        # >> Ventaja: la misma logica sirve para la consola simple, la
        #    interfaz con colores y los tests, sin tocar este archivo.
        if self.observador is not None:
            self.observador(
                EventoPlanificador(
                    tiempo=self.reloj,
                    tipo=tipo,
                    proceso_id=None if proceso is None else proceso.id,
                    detalle=detalle,
                )
            )
