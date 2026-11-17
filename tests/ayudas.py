"""Funciones auxiliares para las pruebas.

El simulador avanza siempre paso a paso (lo pide la consigna). Para probar
una simulacion completa sin esperar teclas, las pruebas repiten el mismo
ciclo que usa ``ejecutar_simulacion``: procesar el instante y ejecutar una
unidad de CPU.
"""


def avanzar_unidad(planificador) -> None:
    """Procesa los arribos del instante, reevalua SRTF y avanza una unidad."""
    planificador.procesar_instante()
    planificador.ejecutar_unidad()


def simular(planificador) -> None:
    """Ejecuta la simulacion hasta que no queden procesos pendientes."""
    while planificador.admision.hay_procesos_pendientes():
        avanzar_unidad(planificador)
