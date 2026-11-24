# =============================================================================
#  estadisticas.py  -  EL INFORME FINAL (retorno, espera, respuesta, rendimiento)
# -----------------------------------------------------------------------------
#  QUE HACE:  Al terminar la simulacion, calcula los tiempos de cada proceso
#             y los promedios. SOLO CALCULA, no imprime.
#  LO USA:    presentacion.py -> lineas_informe() llama a
#             calcular_estadisticas() y despues formatear_informe() lo pasa
#             a texto.
#  USA A:     proceso.py (lee los tiempos guardados en cada Proceso).
#
#  DE DONDE SALE CADA DATO:
#    tiempo_arribo       -> del CSV
#    tiempo_irrupcion    -> del CSV
#    tiempo_inicio       -> lo anota planificador.ejecutar_unidad() la 1ra vez
#    tiempo_finalizacion -> lo anota planificador._finalizar()
#
#  FORMULAS (pregunta segura en el coloquio):
#    Retorno   = Finalizacion - Arribo     (todo el tiempo dentro del sistema)
#    Espera    = Retorno - Irrupcion       (el tiempo en que NO uso la CPU)
#    Respuesta = Inicio - Arribo           (cuanto tardo en tocar la CPU)
#    Rendimiento = procesos terminados / tiempo total
# =============================================================================
"""Calculo del informe estadistico final de la simulacion.

Convenciones (unidades de tiempo discretas, ut):
    - Tiempo de retorno = tiempo de finalizacion - tiempo de arribo.
    - Tiempo de espera  = tiempo de retorno - tiempo de irrupcion.
      Incluye todo el tiempo que el proceso estuvo en el sistema sin usar la
      CPU: en NUEVO esperando cupo, en LISTO_SUSPENDIDO y en LISTO.
    - Tiempo de respuesta = primer instante en CPU - tiempo de arribo.
    - Rendimiento = trabajos terminados / tiempo total de la simulacion.
      El tiempo total es el instante en que termina el ultimo proceso.
"""

from dataclasses import dataclass
from typing import List, Sequence

from core.proceso import ESTADO_TERMINADO, Proceso


@dataclass(frozen=True)
class EstadisticaProceso:
    """Tiempos calculados para un proceso terminado."""
    # >> Una FILA de la tabla final (un proceso). frozen = no se modifica.

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
    # >> El informe ENTERO: todas las filas + promedios + rendimiento.

    procesos: List[EstadisticaProceso]
    retorno_promedio: float
    espera_promedio: float
    respuesta_promedio: float
    # >> float = numero con decimales (ej. 2.33).
    tiempo_total: int
    trabajos_terminados: int
    rendimiento: float


def calcular_estadisticas(
    procesos: Sequence[Proceso], tiempo_total: int
) -> InformeEstadistico:
    """Calcula retorno, espera, promedios y rendimiento de los terminados."""
    # >> ENTRA: todos los procesos y el tiempo total (el reloj final, que
    #    es el instante en que termino el ultimo).
    # >> SALE:  un InformeEstadistico.
    filas: List[EstadisticaProceso] = []
    for proceso in procesos:
        if proceso.estado != ESTADO_TERMINADO or proceso.tiempo_finalizacion is None:
            continue
            # >> Solo se cuentan los TERMINADOS. (En una simulacion completa
            #    terminan todos; esto protege si se corta antes.)
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
                # >> ESPERA = retorno - irrupcion. Incluye el tiempo en NUEVO
                #    (sin cupo), en LISTO_SUSPENDIDO (sin memoria) y en LISTO
                #    (esperando CPU). Es decir: TODO el tiempo sin usar la CPU.
                # >> PREGUNTA: "Por que no cuentan solo el tiempo en LISTO?"
                #    RESPUESTA: la definicion es retorno - irrupcion; si el
                #    proceso estuvo suspendido, ese tiempo tambien es espera.
                tiempo_respuesta=proceso.tiempo_inicio - proceso.tiempo_arribo,
            )
        )

    cantidad = len(filas)
    retorno_promedio = (
        sum(fila.tiempo_retorno for fila in filas) / cantidad if cantidad else 0.0
    )
    # >> Promedio = suma / cantidad. El "if cantidad else 0.0" evita dividir
    #    por cero si no hay ninguno terminado.
    espera_promedio = (
        sum(fila.tiempo_espera for fila in filas) / cantidad if cantidad else 0.0
    )
    respuesta_promedio = (
        sum(fila.tiempo_respuesta for fila in filas) / cantidad if cantidad else 0.0
    )
    rendimiento = cantidad / tiempo_total if tiempo_total > 0 else 0.0
    # >> RENDIMIENTO (throughput) = trabajos terminados / tiempo total.
    #    Ej.: 3 procesos en 8 ut -> 3 / 8 = 0.375 trabajos por ut.

    return InformeEstadistico(
        procesos=filas,
        retorno_promedio=retorno_promedio,
        espera_promedio=espera_promedio,
        respuesta_promedio=respuesta_promedio,
        tiempo_total=tiempo_total,
        trabajos_terminados=cantidad,
        rendimiento=rendimiento,
    )
