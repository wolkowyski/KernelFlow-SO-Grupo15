# =============================================================================
#  proceso.py  -  LA "FICHA" DE CADA PROCESO (lo que en teoria llamamos PCB)
# -----------------------------------------------------------------------------
#  QUE HACE:  Define la clase Proceso (una fila del CSV convertida en objeto)
#             y los 5 nombres de estado que usa todo el simulador.
#  LO USAN:   TODOS los modulos.
#               - carga.py        crea los objetos Proceso a partir del CSV.
#               - estados.py      les cambia el atributo "estado".
#               - memoria.py      lee "id" y "tamanio" para darles particion.
#               - admision.py     los mueve entre las colas.
#               - planificador.py les descuenta "tiempo_restante".
#               - estadisticas.py lee sus tiempos para el informe.
#               - presentacion.py los muestra en las tablas.
#  USA A:     nadie del proyecto. Es la base: no importa ningun otro modulo.
#
#    "Proceso es nuestro PCB simplificado: guarda id, tamanio, arribo,
#     irrupcion, cuanto le falta de CPU, su estado, y los instantes en que
#     arranco y termino para despues calcular las estadisticas."
# =============================================================================
"""Modelo de dominio para los procesos del simulador KernelFlow."""

from dataclasses import dataclass
# >> dataclass es un "decorador" de la libreria estandar de Python.
#    Puesto arriba de una clase, ARMA SOLO el constructor __init__ con los
#    atributos que declaramos (id, tamanio, ...). Sin el, tendriamos que
#    escribir a mano:  def __init__(self, id, tamanio, tiempo_arribo, ...):
#                           self.id = id ...
from typing import Optional
# >> Optional[int] significa "un int o None (vacio)". Es solo una ANOTACION
#    de tipo: documenta que se espera, pero Python no la controla al correr.

# --- Los 5 estados posibles de un proceso ------------------------------------
# >> Se guardan como constantes de texto para escribir cada nombre UNA sola vez.
#    Si alguien escribe ESTADO_LISTOO, Python da error al instante; si
#    escribiera el texto "LISTOO" a mano, el error pasaria desapercibido.
ESTADO_NUEVO = "NUEVO"                          # llego (o todavia no) y no fue admitido
ESTADO_LISTO = "LISTO"                          # admitido y CON memoria: espera CPU
ESTADO_LISTO_SUSPENDIDO = "LISTO_SUSPENDIDO"    # admitido pero SIN memoria (no entro)
ESTADO_EJECUCION = "EJECUCION"                  # esta usando la CPU (hay 1 sola CPU)
ESTADO_TERMINADO = "TERMINADO"                  # completo su irrupcion

# >> PREGUNTA POSIBLE: "Por que no tienen BLOQUEADO?"
#    RESPUESTA: la consigna no tiene E/S. Cada proceso es una sola rafaga de
#    CPU, asi que ningun proceso se bloquea esperando un dispositivo.

ESTADOS_VALIDOS = (
    ESTADO_NUEVO,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_EJECUCION,
    ESTADO_TERMINADO,
)
# >> Tupla (lista que no se puede modificar) con los 5 estados. Se usa abajo,
#    en __post_init__, para rechazar un estado inventado.


def _es_entero(valor: object) -> bool:
    """Verifica que el valor sea un entero puro (excluyendo booleanos)."""
    # >> El "_" al inicio del nombre es una convencion: "funcion interna de
    #    este archivo, no la uses desde afuera".
    # >> Truco de Python: True y False SON enteros (True == 1). Sin el
    #    "not isinstance(valor, bool)", un tamanio=True pasaria como valido.
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

    # >> Los 4 primeros vienen del CSV (son las 4 columnas). Son obligatorios.
    id: str
    # >> Ej. "P1". Lo usa memoria para saber de quien es cada particion.
    tamanio: int
    # >> KB que pide. Lo usa memoria.asignar() para buscar hueco Best-Fit.
    tiempo_arribo: int
    # >> Cuando llega. Lo usa admision para saber CUANDO entra al sistema
    #    (procesar_arribos) y planificador como 2do criterio de desempate.
    tiempo_irrupcion: int
    # >> Cuanta CPU necesita en total. No cambia nunca.

    # >> Los siguientes tienen valor por defecto ("= ..."), asi que NO hace
    #    falta pasarlos al crear el Proceso.
    tiempo_restante: Optional[int] = None
    # >> Cuanta CPU le FALTA. Arranca igual a la irrupcion (ver __post_init__)
    #    y planificador.ejecutar_unidad() le resta 1 por cada ut en CPU.
    #    ES LA CLAVE DE SRTF: gana la CPU el de menor tiempo_restante.
    estado: str = ESTADO_NUEVO
    # >> Todos nacen en NUEVO. Solo se cambia con estados.cambiar_estado().
    tiempo_inicio: Optional[int] = None
    # >> Primera vez que toco la CPU. Lo pone planificador.ejecutar_unidad().
    #    Sirve para el tiempo de RESPUESTA (inicio - arribo).
    tiempo_finalizacion: Optional[int] = None
    # >> Cuando termino. Lo pone planificador._finalizar().
    #    Sirve para el tiempo de RETORNO (finalizacion - arribo).

    def __post_init__(self) -> None:
        # >> __post_init__ lo llama dataclass AUTOMATICAMENTE justo despues de
        #    crear el objeto. Aca validamos que los datos tengan sentido.
        # >> Es una segunda red de seguridad: carga.py ya valida el CSV, pero
        #    si alguien crea un Proceso a mano (por ejemplo en los tests),
        #    tambien queda protegido. ValueError = "valor invalido".
        if self.id is None:
            raise ValueError("El ID del proceso no puede ser nulo.")
        self.id = str(self.id).strip()
        # >> .strip() saca espacios al principio y al final: " P1 " -> "P1".
        if not self.id:
            raise ValueError("El ID del proceso no puede estar vacio.")

        if not _es_entero(self.tamanio) or self.tamanio <= 0:
            raise ValueError(
                f"El tamanio del proceso '{self.id}' debe ser un entero positivo."
            )
            # >> f"...{self.id}..." es un f-string: mete el valor de la
            #    variable dentro del texto. Se usa en todo el proyecto.

        if not _es_entero(self.tiempo_arribo) or self.tiempo_arribo < 0:
            raise ValueError(
                f"El tiempo de arribo del proceso '{self.id}' debe ser un entero mayor o igual a 0."
            )
            # >> El arribo puede ser 0 (llega al inicio); por eso es "< 0".

        if not _es_entero(self.tiempo_irrupcion) or self.tiempo_irrupcion <= 0:
            raise ValueError(
                f"El tiempo de irrupcion del proceso '{self.id}' debe ser un entero positivo."
            )
            # >> La irrupcion NO puede ser 0: un proceso sin CPU no tiene sentido.

        if self.tiempo_restante is None:
            self.tiempo_restante = self.tiempo_irrupcion
            # >> CASO NORMAL: al crearse, le falta toda su irrupcion.
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
            # >> ', '.join(lista) une los textos con ", " entre medio:
            #    "NUEVO, LISTO, LISTO_SUSPENDIDO, EJECUCION, TERMINADO".
