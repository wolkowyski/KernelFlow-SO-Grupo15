# =============================================================================
#  estados.py  -  EL DIAGRAMA DE ESTADOS (que cambios de estado estan permitidos)
# -----------------------------------------------------------------------------
#  QUE HACE:  Guarda el diagrama de estados como un diccionario y ofrece UNA
#             sola funcion, cambiar_estado(), que es la UNICA forma de cambiar
#             el estado de un proceso. Si el cambio no esta en el diagrama,
#             lanza error (asi un bug no puede "saltear" estados).
#  LO USA:    admision.py (en enviar_a_ejecucion, devolver_a_listo, finalizar
#             e _intentar_cargar). OJO: el planificador NUNCA cambia estados
#             directamente; le pide a admision que lo haga.
#  USA A:     proceso.py (los nombres de los estados y la clase Proceso).
#
#  EL DIAGRAMA (lo que esta escrito en TRANSICIONES_PERMITIDAS):
#
#        NUEVO ---------------> LISTO <----------> EJECUCION ----> TERMINADO
#          |                      ^      SRTF elige /
#          | hay cupo pero        |      apropiacion
#          | no hay memoria       | se libero memoria
#          v                      |
#        LISTO_SUSPENDIDO --------+
#
#    "Las transiciones estan en una tabla. Cualquier cambio de estado pasa
#     por cambiar_estado, que verifica contra la tabla; si alguien intenta un
#     cambio que no existe en el diagrama, el programa lo rechaza."
# =============================================================================
"""Estados y transiciones permitidas del ciclo de vida de un proceso."""

from core.proceso import (
    ESTADO_EJECUCION,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_NUEVO,
    ESTADO_TERMINADO,
    Proceso,
)
# >> "from core.proceso import X" = trae X del archivo core/proceso.py.
#    "core" es la carpeta (paquete) y "proceso" el archivo, sin el .py.


TRANSICIONES_PERMITIDAS = {
    # >> Diccionario:  estado_actual -> {conjunto de estados a los que puede ir}
    #    Las llaves { } de adentro son un "set" (conjunto, sin repetidos).
    ESTADO_NUEVO: {ESTADO_LISTO, ESTADO_LISTO_SUSPENDIDO},
    # >> NUEVO -> LISTO:             admitido y entro en memoria.
    # >> NUEVO -> LISTO_SUSPENDIDO:  admitido (habia cupo) pero sin hueco.
    ESTADO_LISTO: {ESTADO_EJECUCION},
    # >> LISTO -> EJECUCION: SRTF lo eligio.
    # >> PREGUNTA: "Por que LISTO no puede ir a LISTO_SUSPENDIDO?"
    #    RESPUESTA: no hacemos swap-out. Un proceso que ya esta en memoria no
    #    se saca; la consigna no lo pide.
    ESTADO_LISTO_SUSPENDIDO: {ESTADO_LISTO},
    # >> LISTO_SUSPENDIDO -> LISTO: termino otro proceso, se libero memoria y
    #    ahora si entra (admision.reintentar_suspendidos).
    ESTADO_EJECUCION: {ESTADO_LISTO, ESTADO_TERMINADO},
    # >> EJECUCION -> LISTO:      apropiacion (llego uno con menor restante).
    # >> EJECUCION -> TERMINADO:  completo su irrupcion.
    ESTADO_TERMINADO: set(),
    # >> TERMINADO es final: no va a ningun lado. set() = conjunto vacio.
}


def cambiar_estado(proceso: Proceso, estado_destino: str) -> None:
    """Cambia el estado si la transicion pertenece al ciclo de vida acordado."""
    # >> "-> None" indica que la funcion no devuelve nada; solo modifica.
    if estado_destino not in TRANSICIONES_PERMITIDAS.get(proceso.estado, set()):
        # >> .get(clave, set()) busca el estado actual en el diccionario; si
        #    no estuviera, devuelve un conjunto vacio (y entonces nada es valido).
        # >> Ej.: proceso en TERMINADO quiere ir a LISTO -> set() no contiene
        #    LISTO -> error.
        raise ValueError(
            f"No se puede pasar el proceso '{proceso.id}' "
            f"de {proceso.estado} a {estado_destino}."
        )
    proceso.estado = estado_destino
    # >> Si el cambio es valido, recien ahi se modifica el atributo.
