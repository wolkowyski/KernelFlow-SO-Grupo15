# =============================================================================
#  presentacion.py  -  LO QUE SE VE EN PANTALLA (tablas y pasos)
# -----------------------------------------------------------------------------
#  QUE HACE:  Imprime en la consola: los procesos cargados, cada paso de la
#             simulacion (eventos + colas + tabla de procesos + tabla de
#             particiones) y el informe final.
#             ES EL UNICO MODULO DEL NUCLEO QUE HACE print() (junto con main).
#             SOLO CONSULTA: nunca cambia estados, colas ni memoria.
#  LO USA:    main.py (mostrar_inicio, mostrar_paso, mostrar_fin).
#  USA A:     admision.py (colas y grado), memoria.py (particiones y huecos),
#             estadisticas.py (calculo del informe), planificador.py (solo
#             el tipo EventoPlanificador) y proceso.py.

#    "Separamos la logica de la pantalla: el planificador emite eventos y
#     presentacion los imprime. Por eso la misma simulacion se puede mostrar
#     en consola simple, en la interfaz con colores o verificar en los tests."
# =============================================================================
"""Salida de consola para los eventos y el estado observable del simulador."""

from pathlib import Path
from typing import List, Optional, Sequence

from core.admision import GRADO_MAXIMO_MULTIPROGRAMACION, Admision
from core.estadisticas import InformeEstadistico, calcular_estadisticas
from core.memoria import GestorMemoria
from core.planificador import EventoPlanificador
from core.proceso import (
    ESTADO_EJECUCION,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_TERMINADO,
    Proceso,
)

ANCHO = 80
# >> Ancho en caracteres de las lineas "=====". main.py tambien lo importa.


def tabla_ascii(encabezados: Sequence[str], filas: Sequence[Sequence[object]]) -> str:
    """Construye una tabla ASCII apta para cualquier consola."""
    # >> Arma una tabla con bordes usando solo + - |  (funciona en cualquier
    #    consola, sin caracteres raros). Ejemplo de salida:
    #      +----+-----+
    #      | ID | KB  |
    #      +----+-----+
    #      | P1 | 60  |
    #      +----+-----+
    celdas = [[str(valor) for valor in fila] for fila in filas]
    # >> Convierte todo a texto (los numeros tambien).
    anchos = [
        max([len(nombre)] + [len(fila[indice]) for fila in celdas])
        for indice, nombre in enumerate(encabezados)
    ]
    # >> Para cada columna: el ancho es el texto MAS LARGO entre el titulo
    #    y todos los valores de esa columna.
    borde = "+" + "+".join("-" * (ancho + 2) for ancho in anchos) + "+"
    # >> "-" * 5 = "-----" (repetir un texto). +2 por el espacio a cada lado.

    def formar_fila(valores: Sequence[str]) -> str:
        # >> Funcion definida DENTRO de otra: solo existe aca adentro y puede
        #    usar "anchos" de la funcion de afuera.
        return "| " + " | ".join(
            f"{valor:<{ancho}}" for valor, ancho in zip(valores, anchos)
        ) + " |"
        # >> f"{valor:<{ancho}}" = escribe el valor alineado a la IZQUIERDA y
        #    rellena con espacios hasta "ancho" caracteres.
        # >> zip(a, b) recorre las dos listas a la vez: (valor1, ancho1), ...

    lineas = [borde, formar_fila(encabezados), borde]
    lineas.extend(formar_fila(fila) for fila in celdas)
    lineas.append(borde)
    return "\n".join(lineas)
    # >> "\n" = salto de linea. Une todas las lineas en un solo texto.


class PresentacionConsola:
    """Muestra la simulacion paso a paso en la consola.

    Los estados pertenecen a los procesos, las colas a admision y las
    particiones al gestor de memoria. Esta clase solo consulta esos datos.
    """

    def __init__(
        self,
        procesos: Sequence[Proceso],
        admision: Admision,
        memoria: GestorMemoria,
    ) -> None:
        # >> Se crea en main.ejecutar_simulacion con los MISMOS objetos que
        #    usa el planificador. Asi, cada vez que imprime, ve el estado real.
        self.procesos = procesos
        self.admision = admision
        self.memoria = memoria

    def mostrar_inicio(self, ruta_csv: Path) -> None:
        """Muestra los procesos cargados antes de empezar la simulacion."""
        # >> Pantalla "PROCESOS CARGADOS" antes del primer Enter.
        print("=" * ANCHO)
        print("PROCESOS CARGADOS")
        print("=" * ANCHO)
        print(f"Archivo: {ruta_csv.name}")
        # >> .name = solo el nombre del archivo, sin la carpeta.
        print(
            f"{len(self.procesos)} proceso(s) leido(s) correctamente. Todos "
            "comienzan en NUEVO y esperan su tiempo de arribo."
        )
        print()
        print(self.tabla_procesos())
        print()
        print("Memoria: 100K para el SO + 450K para usuario (MVT, Best-Fit).")
        print("Planificacion: SRTF apropiativo. Multiprogramacion maxima: 5.")

    def mostrar_paso(
        self, eventos: Sequence[EventoPlanificador], tiempo: int, numero: int
    ) -> None:
        """Muestra todos los cambios de un instante y el estado del sistema."""
        # >> LA LLAMA main.py cada vez que en un instante hubo eventos.
        # >> ENTRA: la lista de eventos del paso, el reloj y el numero de paso.
        print("\n" + "=" * ANCHO)
        print(f"COMIENZO DEL PASO {numero} | RELOJ: t = {tiempo} ut")
        print("=" * ANCHO)
        print("EVENTOS DE ESTE PASO")
        for evento in eventos:
            print(f"- t = {evento.tiempo} | {evento.detalle}")
            # >> Un renglon por evento, con el texto que armo el planificador.
        print("-" * ANCHO)

        terminados = sum(
            proceso.estado == ESTADO_TERMINADO for proceso in self.procesos
        )
        # >> Truco: sumar True/False cuenta los True (True vale 1).
        resumen, listos, suspendidos = self.lineas_resumen(tiempo)
        # >> lineas_resumen devuelve una lista de 3 textos y se desempaquetan.
        print(resumen)
        print(
            f"TERMINADOS: {terminados}/{len(self.procesos)}   "
            f"MULTIPROGRAMACION: {self.admision.grado_multiprogramacion()}/"
            f"{GRADO_MAXIMO_MULTIPROGRAMACION}"
        )
        # >> Aca se ve el "3/5" del grado de multiprogramacion.
        print(f"COLA {listos}")
        print(f"COLA {suspendidos}")
        print("(entre parentesis: tiempo restante en ut)")
        print()
        print("ESTADO DE LOS PROCESOS")
        print(self.tabla_procesos())
        print()
        print("TABLA DE PARTICIONES (KB)")
        print(self.tabla_memoria())
        print(self.linea_memoria_libre())
        print(f" FIN DEL PASO {numero} ".center(ANCHO, "="))
        # >> .center(80, "=") centra el texto rellenando con "=" a los lados.

    def mostrar_fin(self, tiempo: int) -> None:
        """Cierra la simulacion y presenta el informe estadistico."""
        print("\n" + "=" * ANCHO)
        print(f"SIMULACION FINALIZADA EN t = {tiempo} ut")
        print("=" * ANCHO)
        print(f"Memoria de usuario libre: {self.memoria.memoria_libre_total()}K.")
        # >> Al final deberia dar 450K: todos terminaron y liberaron.
        print()
        for linea in self.lineas_informe(tiempo):
            print(linea)

    # ------------------------------------------------------------------
    # Construccion de contenido reutilizable por las distintas vistas.
    # ------------------------------------------------------------------
    # >> Estas funciones DEVUELVEN texto en vez de imprimirlo, para que
    #    tambien las pueda usar la interfaz con colores.

    def proceso_en_cpu(self) -> Optional[Proceso]:
        return next(
            (proceso for proceso in self.procesos if proceso.estado == ESTADO_EJECUCION),
            None,
        )
        # >> next(generador, None): devuelve el PRIMER proceso que este en
        #    EJECUCION, o None si no hay ninguno (CPU ociosa).

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
        # >> Ej.: ["TIEMPO: 4 ut   CPU: P3 (T. restante: 1 ut de 2 ut ...)",
        #          "LISTO: P1(2), P2(5)",
        #          "LISTO_SUSPENDIDO: P4(3)"]

    def tabla_procesos(self) -> str:
        filas = [
            (
                proceso.id,
                proceso.tamanio,
                proceso.tiempo_arribo,
                proceso.tiempo_irrupcion,
                proceso.tiempo_irrupcion - proceso.tiempo_restante,
                # >> T. Ejecutado = lo que ya uso de CPU = irrupcion - restante.
                proceso.tiempo_restante,
                "L/SUSP."
                if proceso.estado == ESTADO_LISTO_SUSPENDIDO
                else proceso.estado,
                # >> LISTO_SUSPENDIDO es largo: se abrevia "L/SUSP." en la tabla.
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
        # >> Lista = [SO] + todas las particiones/huecos de usuario.
        #    El "*" "desarma" la lista y pone sus elementos adentro.
        filas = []
        for particion in particiones:
            if particion.libre:
                asignado, fragmentacion = "LIBRE", "-"
            else:
                asignado = particion.proceso_id
                fragmentacion = "-" if particion.proceso_id == "SO" else "0"
                # >> FRAGMENTACION INTERNA = "0" para todo proceso: en MVT la
                #    particion mide EXACTAMENTE lo que pidio el proceso, no
                #    sobra nada adentro. (Al SO no aplica: "-".)
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
        # >> Ej.: "Libre usuario: 250K en 2 hueco(s); mayor hueco: 150K"
        #    Si libre > mayor hueco, la memoria esta fragmentada (externa).

    def lineas_informe(self, tiempo: int) -> List[str]:
        """Informe estadistico final: retorno, espera, promedios y rendimiento."""
        informe = calcular_estadisticas(self.procesos, tiempo)
        # >> estadisticas.py CALCULA...
        return formatear_informe(informe).splitlines()
        # >> ...y formatear_informe lo pasa a TEXTO.

    @staticmethod
    def _formatear_cola(procesos: Sequence[Proceso]) -> str:
        """Muestra cada proceso con su tiempo restante entre parentesis."""
        return ", ".join(
            f"{proceso.id}({proceso.tiempo_restante})" for proceso in procesos
        ) or "-"
        # >> "P1(2), P3(4)". Si la cola esta vacia, join da "" y el
        #    "or '-'" lo reemplaza por "-" (un texto vacio cuenta como falso).


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
    # >> Ultima fila con los promedios. ":.2f" = 2 decimales (2.33).
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
        # >> ":.4f" = 4 decimales (0.3750).
    ]
    return "\n".join(lineas)
