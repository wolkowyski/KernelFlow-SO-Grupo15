# =============================================================================
#  memoria.py  -  LA MEMORIA: PARTICIONES VARIABLES (MVT) CON BEST-FIT
# -----------------------------------------------------------------------------
#  QUE HACE:  Administra los 550K de memoria:
#               [0K   - 100K)  -> Sistema Operativo (fijo, nunca se toca)
#               [100K - 550K)  -> 450K para procesos de usuario
#             Guarda la memoria de usuario como una LISTA ORDENADA POR
#             DIRECCION donde se mezclan particiones ocupadas y huecos libres,
#             que juntos SIEMPRE suman 450K. Ejemplo:
#               [ P1 100-200 | LIBRE 200-260 | P3 260-410 | LIBRE 410-550 ]
#  LO USAN:   admision.py   -> asignar() al admitir, y consultas de huecos
#                              para armar el mensaje de fragmentacion.
#             planificador.py -> liberar() cuando un proceso termina.
#             presentacion.py -> obtener_resumen_memoria() para la tabla.
#  USA A:     proceso.py (la clase Proceso).
#
#  LAS 3 IDEAS CLAVE:
#   1) asignar(): Best-Fit = el hueco MAS CHICO donde entra. La particion se
#      crea del tamanio EXACTO del proceso, al principio del hueco; lo que
#      sobra queda como un hueco nuevo. => fragmentacion INTERNA siempre 0.
#   2) liberar(): la particion vuelve a ser hueco y se FUSIONA con los huecos
#      vecinos (si hay). Esto NO es compactacion (no movemos procesos).
#   3) La fragmentacion EXTERNA si puede pasar: hay KB libres en total pero
#      repartidos en huecos chicos donde no entra nadie.
# =============================================================================
"""Administracion de memoria MVT con estrategia de asignacion Best-Fit."""

from dataclasses import dataclass, field
# >> field() permite configurar un atributo de un dataclass (ver "numero").
from typing import Dict, List, Optional, Tuple, Union
# >> Anotaciones de tipo: List[X] lista de X, Dict diccionario, Tuple tupla,
#    Union[A, B] "A o B", Optional[X] "X o None". Solo documentan.

from core.proceso import Proceso

MEMORIA_SO_KB = 100
MEMORIA_USUARIO_KB = 450
MEMORIA_TOTAL_KB = MEMORIA_SO_KB + MEMORIA_USUARIO_KB      # 550K
DIRECCION_INICIO_SO = 0
DIRECCION_INICIO_USUARIO = MEMORIA_SO_KB                   # el usuario empieza en 100K
# >> Valores de la consigna. Estan como constantes para no repetir numeros
#    "magicos" por todo el codigo.


def _es_entero_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0
    # >> Misma idea que proceso._es_entero: excluye True/False.


def _es_entero_no_negativo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


@dataclass(frozen=True)
class ParticionMemoria:
    """Representa una particion ocupada o un hueco libre en la memoria.

    ``numero`` es el ID de particion: se asigna al crear la particion para un
    proceso y no cambia aunque otras particiones se liberen o fusionen. El SO
    usa el 0 y los huecos libres no tienen numero.
    """
    # >> frozen=True: el objeto es INMUTABLE (no se puede modificar despues de
    #    creado). Por eso, cuando algo cambia, en vez de editar la particion
    #    se crea una NUEVA y se reemplaza en la lista. Evita bugs de
    #    "alguien modifico la particion sin querer".
    # >> La MISMA clase sirve para particion ocupada y para hueco libre:
    #    la diferencia es si proceso_id tiene un ID o es None.

    direccion_inicio: int
    # >> Donde empieza, en KB. Ej. 100.
    tamanio: int
    # >> Cuantos KB ocupa. Ej. 60.
    proceso_id: Optional[str] = None
    # >> ID del proceso dueno, o None si es un HUECO LIBRE.
    numero: Optional[int] = field(default=None, compare=False)
    # >> Numero de particion para la tabla (1, 2, 3...). El SO es 0; los
    #    huecos no tienen. compare=False: al comparar dos particiones con ==
    #    no se tiene en cuenta el numero (solo direccion, tamanio y dueno).

    def __post_init__(self) -> None:
        # >> Validaciones al crear (igual que en Proceso).
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
            # >> Como la clase es frozen, "self.proceso_id = ..." daria error.
            #    object.__setattr__ es la forma "oficial" de asignar igual
            #    DURANTE la creacion. Solo se usa aca para limpiar espacios.

    @property
    def direccion_fin(self) -> int:
        """Direccion limite exclusiva donde termina la particion."""
        return self.direccion_inicio + self.tamanio
        # >> @property: se usa como atributo, sin parentesis:
        #    particion.direccion_fin  (no particion.direccion_fin()).
        # >> "Exclusiva": una particion [100K - 160K) ocupa 100..159.
        #    Asi la siguiente arranca justo en 160 sin superponerse.

    @property
    def libre(self) -> bool:
        """Indica si la particion es un hueco libre."""
        return self.proceso_id is None
        # >> particion.libre -> True si es hueco. Se usa en TODO el archivo.


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
        # >> Se crea UNA sola vez, en main.ejecutar_simulacion:
        #    memoria = GestorMemoria()   (usa 100K y 450K por defecto).
        if not _es_entero_no_negativo(memoria_so_kb):
            raise ValueError("La memoria reservada al SO debe ser un entero no negativo.")
        if not _es_entero_positivo(memoria_usuario_kb):
            raise ValueError("La memoria de usuario debe ser un entero positivo.")

        self._memoria_so_kb = memoria_so_kb
        self._memoria_usuario_kb = memoria_usuario_kb
        self._direccion_inicio_usuario = memoria_so_kb
        # >> El "_" adelante = atributo interno. Desde afuera se lee con las
        #    @property de abajo, pero no se deberia modificar.
        self._siguiente_numero_particion = 1
        # >> Contador para numerar particiones: 1, 2, 3... Nunca se reutiliza
        #    un numero, aunque la particion se libere.
        self._particiones: List[ParticionMemoria] = [
            ParticionMemoria(
                direccion_inicio=self._direccion_inicio_usuario,
                tamanio=self._memoria_usuario_kb,
                proceso_id=None,
            )
        ]
        # >> ESTADO INICIAL: la lista tiene UN solo elemento: un hueco libre
        #    de 450K que va de 100K a 550K. Todo lo demas sale de partir y
        #    volver a unir este hueco.

    # --- Consultas (solo leen, no modifican nada) -----------------------------

    @property
    def memoria_so_kb(self) -> int:
        """Tamanio en KB reservado para el sistema operativo."""
        return self._memoria_so_kb

    @property
    def memoria_usuario_kb(self) -> int:
        """Tamanio total en KB de la memoria de usuario."""
        return self._memoria_usuario_kb
        # >> La usa admision.__init__ para rechazar procesos de mas de 450K.

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
        # >> El SO NO esta en la lista _particiones (nunca se asigna ni libera).
        #    Se fabrica aca solo para mostrarlo como primera fila de la tabla.

    def obtener_particiones(self) -> List[ParticionMemoria]:
        """Retorna una copia ordenada de todas las particiones del area de usuario."""
        return list(self._particiones)
        # >> list(...) devuelve una COPIA: quien la reciba no puede romper la
        #    lista original agregando o sacando elementos.

    def obtener_huecos(self) -> List[ParticionMemoria]:
        """Retorna la lista de huecos libres actuales en el area de usuario."""
        return [particion for particion in self._particiones if particion.libre]
        # >> "List comprehension": arma una lista nueva con los elementos que
        #    cumplen la condicion. Se lee: "particion, por cada particion de
        #    la lista, si particion es libre".

    def obtener_particiones_ocupadas(self) -> List[ParticionMemoria]:
        """Retorna la lista de particiones asignadas a procesos de usuario."""
        return [particion for particion in self._particiones if not particion.libre]

    def obtener_asignacion(
        self, proceso_o_id: Union[Proceso, str]
    ) -> Optional[ParticionMemoria]:
        """Retorna la particion asignada a un proceso especifico o ``None`` si no reside en memoria."""
        # >> Acepta un Proceso o directamente su ID en texto (Union).
        # >> La usa planificador._finalizar para saber QUE particion se libera
        #    (y asi poder mostrar el mensaje "Se libera la memoria de P1...").
        id_buscado = self._extraer_id_proceso(proceso_o_id)
        for particion in self._particiones:
            if particion.proceso_id == id_buscado:
                return particion
        return None

    def memoria_libre_total(self) -> int:
        """Suma total en KB de los huecos libres en el area de usuario."""
        return sum(hueco.tamanio for hueco in self.obtener_huecos())
        # >> Suma de TODOS los huecos. Si es >= que lo que pide un proceso
        #    pero igual no entra => FRAGMENTACION EXTERNA (ver admision).

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
        # >> El hueco mas grande. Si el proceso no entra ni ahi, no entra en
        #    ninguno. Lo usa admision para el mensaje de fragmentacion.

    def puede_asignar(self, tamanio: int) -> bool:
        """Indica si existe un hueco libre capaz de alojar ``tamanio`` KB."""
        # >> Consulta auxiliar (la usan los tests). El simulador directamente
        #    llama a asignar() y mira si devolvio None.
        if not _es_entero_positivo(tamanio):
            raise ValueError("El tamanio a consultar debe ser un entero positivo.")
        if tamanio > self._memoria_usuario_kb:
            return False
        return any(
            particion.libre and particion.tamanio >= tamanio
            for particion in self._particiones
        )
        # >> any(...) = True si AL MENOS UNO cumple la condicion.

    # --- Operaciones que MODIFICAN la memoria ---------------------------------

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
        # >> LA LLAMA: admision._intentar_cargar(), con un Proceso.
        # >> DEVUELVE: la particion creada (exito) o None (no entra).

        # PASO 1: sacar el ID y el tamanio del proceso.
        id_proceso, tamanio_requerido = self._extraer_datos_asignacion(
            proceso_o_id, tamanio
        )
        # >> La funcion devuelve una tupla de 2 y se "desempaqueta" en 2
        #    variables de una vez: a, b = (x, y).

        # PASO 2: un proceso no puede tener dos particiones.
        if self.obtener_asignacion(id_proceso) is not None:
            raise ValueError(
                f"El proceso '{id_proceso}' ya tiene una particion de memoria asignada."
            )

        # PASO 3: si pide mas que toda la memoria de usuario, imposible.
        if tamanio_requerido > self._memoria_usuario_kb:
            return None

        # PASO 4: BEST-FIT. Buscar la POSICION (indice) del mejor hueco.
        indice_mejor_hueco = self._buscar_indice_best_fit(tamanio_requerido)
        if indice_mejor_hueco is None:
            return None
            # >> Ningun hueco alcanza -> None -> admision lo manda a
            #    LISTO_SUSPENDIDO (o lo deja ahi si ya estaba).

        # PASO 5: crear la particion AL PRINCIPIO del hueco elegido, del
        #         tamanio EXACTO que pidio el proceso (eso es MVT).
        hueco_seleccionado = self._particiones[indice_mejor_hueco]
        particion_asignada = ParticionMemoria(
            direccion_inicio=hueco_seleccionado.direccion_inicio,
            tamanio=tamanio_requerido,
            proceso_id=id_proceso,
            numero=self._siguiente_numero_particion,
        )
        self._siguiente_numero_particion += 1

        # PASO 6: lo que sobra del hueco queda como hueco nuevo, a continuacion.
        tamanio_remanente = hueco_seleccionado.tamanio - tamanio_requerido
        if tamanio_remanente == 0:
            self._particiones[indice_mejor_hueco] = particion_asignada
            # >> Entro JUSTO: el hueco se reemplaza por la particion y listo.
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
            # >> "Asignacion por rebanada" (slice): reemplaza 1 elemento de la
            #    lista (el hueco) por 2 (particion + hueco sobrante), en el
            #    MISMO lugar. Asi la lista sigue ordenada por direccion.
            # >> Ejemplo: hueco [100-550) de 450K, llega P1 de 60K:
            #    antes:   [ LIBRE 100-550 ]
            #    despues: [ P1 100-160 | LIBRE 160-550 ]

        return particion_asignada

    def liberar(self, proceso_o_id: Union[Proceso, str]) -> bool:
        """Libera la particion ocupada por el proceso y fusiona huecos libres contiguos.

        Argumentos:
            proceso_o_id: Instancia de ``Proceso`` o identificador ``str`` del proceso.

        Retorna:
            ``True`` si el proceso tenia memoria asignada y fue liberada;
            ``False`` si el proceso no se encontraba en memoria.
        """
        # >> LA LLAMA: planificador._finalizar(), cuando un proceso TERMINA.
        #    Es el UNICO momento en que se libera memoria en todo el simulador.
        id_proceso = self._extraer_id_proceso(proceso_o_id)

        for indice, particion in enumerate(self._particiones):
            # >> enumerate da (posicion, elemento): (0, p0), (1, p1), ...
            if particion.proceso_id == id_proceso:
                self._particiones[indice] = ParticionMemoria(
                    direccion_inicio=particion.direccion_inicio,
                    tamanio=particion.tamanio,
                    proceso_id=None,
                )
                # >> Se reemplaza por un HUECO en el mismo lugar y tamanio
                #    (proceso_id=None, sin numero).
                self._compactar_huecos_adyacentes()
                # >> Y se unen los huecos que hayan quedado pegados.
                return True

        return False

    def obtener_resumen_memoria(self) -> Dict[str, object]:
        """Retorna una instantanea observable del estado de memoria para presentacion."""
        # >> Una "foto" de la memoria en un diccionario. La usa
        #    presentacion.tabla_memoria() (y el panel de la interfaz).
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

    # --- Funciones internas -------------------------------------------------

    def _buscar_indice_best_fit(self, tamanio_requerido: int) -> Optional[int]:
        # >> EL CORAZON DE BEST-FIT. Devuelve la posicion en la lista del
        #    hueco elegido, o None si no entra en ninguno.
        candidatos: List[Tuple[int, int, int]] = []
        for indice, particion in enumerate(self._particiones):
            if particion.libre and particion.tamanio >= tamanio_requerido:
                # >> Candidato = hueco libre donde ENTRA el proceso.
                candidatos.append(
                    (particion.tamanio, particion.direccion_inicio, indice)
                )
                # >> Se guarda una tupla (tamanio, direccion, indice).

        if not candidatos:
            return None

        _, _, indice_elegido = min(candidatos)
        return indice_elegido
        # >> min() sobre tuplas compara el 1er elemento; si empatan, el 2do...
        #    => gana el hueco de MENOR TAMANIO (eso es Best-Fit) y, si hay dos
        #       del mismo tamanio, el de MENOR DIRECCION.
        # >> "_, _, indice_elegido = ..." desempaqueta la tupla y descarta
        #    (con "_") el tamanio y la direccion: solo nos importa el indice.
        # >> PREGUNTA POSIBLE: "Como lo cambiarian a First-Fit o Worst-Fit?"
        #    First-Fit: quedarse con el PRIMER candidato (menor direccion).
        #    Worst-Fit: usar max() por tamanio (el hueco MAS GRANDE).
        #    Es cambiar solo esta funcion; el resto del simulador no se entera.

    def _compactar_huecos_adyacentes(self) -> None:
        # >> OJO CON EL NOMBRE: NO es "compactacion" de la teoria (mover
        #    procesos para juntar todo el espacio libre). Solo FUSIONA huecos
        #    que quedaron PEGADOS uno al lado del otro. Los procesos no se mueven.
        if not self._particiones:
            return

        compactadas: List[ParticionMemoria] = [self._particiones[0]]
        # >> Lista nueva que arranca con el primer elemento.
        for actual in self._particiones[1:]:
            # >> [1:] = desde el segundo elemento hasta el final.
            anterior = compactadas[-1]
            # >> [-1] = el ultimo elemento agregado a la lista nueva.
            if anterior.libre and actual.libre:
                compactadas[-1] = ParticionMemoria(
                    direccion_inicio=anterior.direccion_inicio,
                    tamanio=anterior.tamanio + actual.tamanio,
                    proceso_id=None,
                )
                # >> Dos huecos seguidos -> se reemplazan por UNO que empieza
                #    donde el primero y mide la suma de los dos.
            else:
                compactadas.append(actual)

        self._particiones = compactadas
        # >> Ejemplo: termina P2 en  [ P1 | P2 | LIBRE ]
        #    1) liberar:  [ P1 | LIBRE | LIBRE ]
        #    2) fusionar: [ P1 | LIBRE (suma de los dos) ]

    @staticmethod
    def _extraer_id_proceso(proceso_o_id: Union[Proceso, str]) -> str:
        # >> @staticmethod: funcion que vive dentro de la clase pero no usa
        #    "self" (no necesita datos del objeto). Solo saca el ID.
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
        # >> @classmethod: recibe la CLASE ("cls") en vez del objeto. Aca se
        #    usa solo para poder llamar a cls._extraer_id_proceso.
        # >> Devuelve (id, tamanio) listos para que asignar() trabaje.
        if isinstance(proceso_o_id, Proceso):
            tamanio_final = (
                proceso_o_id.tamanio if tamanio is None else tamanio
            )
            # >> "A if condicion else B": si no pasaron tamanio, usa el del
            #    proceso. En el simulador siempre se usa el del proceso.
            if not _es_entero_positivo(tamanio_final):
                raise ValueError("El tamanio del proceso debe ser un entero positivo.")
            return proceso_o_id.id, tamanio_final

        id_proceso = cls._extraer_id_proceso(proceso_o_id)
        if not _es_entero_positivo(tamanio):
            raise ValueError(
                "Debe indicar un tamanio entero positivo al asignar por ID de proceso."
            )
        return id_proceso, int(tamanio)
