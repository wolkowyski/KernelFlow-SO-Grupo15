# =============================================================================
#  main.py  -  EL PUNTO DE ENTRADA: MENU, ARMADO DE MODULOS Y CICLO PRINCIPAL
# -----------------------------------------------------------------------------
#  QUE HACE:  1) Muestra el menu y pide la opcion o la ruta del CSV.
#             2) ARMA la simulacion: crea memoria, admision, presentacion y
#                planificador y los conecta entre si (ejecutar_simulacion).
#             3) Corre el CICLO PRINCIPAL: en cada vuelta procesa el
#                instante, muestra el paso si hubo eventos, y avanza 1 ut.
#  LO USA:    __main__.py (cuando se ejecuta "python -m core") y el .exe.
#  USA A:     TODOS: carga, memoria, admision, planificador, presentacion.
#
# "COMO SE CONECTAN LOS MODULOS?"

#     cargar_lote(csv) ---> procesos
#                              |
#     GestorMemoria() -------> memoria ---------------+
#                              |                      |
#     Admision(procesos, memoria) -> admision --------+
#                                                     |
#     PresentacionConsola(procesos, admision, memoria)|  (solo mira)
#                                                     |
#     PlanificadorSRTF(admision, memoria, eventos_paso.append)
#                    |
#                    +--> cada evento se agrega a eventos_paso
#                         y presentacion.mostrar_paso() lo imprime
#
#  Los objetos memoria y admision son COMPARTIDOS: hay UNO de cada uno y
#  todos trabajan sobre el mismo. Por eso lo que cambia el planificador lo ve
#  la presentacion en el acto.
# =============================================================================
"""Punto de entrada del simulador KernelFlow (version base del TPI).

Arma los modulos de esta carpeta y ejecuta la simulacion paso a paso:

    proceso.py, estados.py   modelo de proceso y transiciones de estado
    carga.py                 lectura y validacion del CSV
    memoria.py               memoria MVT con Best-Fit
    admision.py              admision, colas y multiprogramacion 5
    planificador.py          planificacion SRTF apropiativa
    estadisticas.py          informe estadistico final
    presentacion.py          salida de texto por consola

Uso, desde la raiz del proyecto:

    python3 -m core                    (menu)
    python3 -m core data/lote.csv      (simula ese archivo)

La carpeta ``interfaz/`` tiene la version con colores, graficos y
exportacion; usa estos mismos modulos y no cambia la logica de la simulacion.
"""

import argparse
# >> Libreria estandar para leer argumentos de la linea de comandos
#    (ej.: python -m core data/lote.csv).
import os
# >> Funciones del sistema operativo (aca: borrar la pantalla).
from pathlib import Path
import sys
# >> Datos del interprete: sys.stdin/stdout (teclado/pantalla),
#    sys.executable (ruta del .exe), sys.frozen (si corre como .exe).
import textwrap
# >> Para cortar textos largos en varias lineas (descripcion del menu).
from typing import Optional, Sequence

from core.admision import Admision, ErrorAdmision
from core.carga import ErrorCargaProcesos, cargar_lote, describir_avisos
from core.memoria import GestorMemoria
from core.planificador import PlanificadorSRTF
from core.presentacion import ANCHO, PresentacionConsola


if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: data/ se distribuye junto al ejecutable.
    DIRECTORIO_PROYECTO = Path(sys.executable).resolve().parent
    # >> Si corre como .exe (PyInstaller pone sys.frozen = True), la carpeta
    #    del proyecto es la carpeta donde esta el .exe.
    # >> getattr(sys, "frozen", False): lee sys.frozen, o False si no existe.
else:
    DIRECTORIO_PROYECTO = Path(__file__).resolve().parent.parent
    # >> Si corre como Python normal: __file__ = este archivo (core/main.py);
    #    .parent = carpeta core; .parent.parent = raiz del proyecto.
DIRECTORIO_DATOS = DIRECTORIO_PROYECTO / "data"
# >> Con Path, "/" une rutas: raiz / "data" -> raiz\data
RUTA_CSV_PREDETERMINADA = DIRECTORIO_DATOS / "procesos_demo.csv"
# >> El CSV de la opcion 1 del menu.

OPCIONES_MENU = (
    (
        "1",
        "Iniciar simulacion con el CSV de prueba",
        "Ejecuta data/procesos_demo.csv: 6 procesos que muestran apropiacion "
        "SRTF, un proceso en LISTO_SUSPENDIDO y la reutilizacion de memoria.",
    ),
    (
        "2",
        "Cargar otro archivo CSV",
        "Pide la ruta de un archivo propio (hasta 10 procesos, una fila por "
        "proceso con el formato id,tamanio,arribo,irrupcion).",
    ),
    ("0", "Salir", "Cierra el simulador."),
)
# >> Cada opcion es una tupla (tecla, titulo, descripcion). Dos textos
#    seguidos entre comillas Python los une solo en uno.


def limpiar_pantalla() -> None:
    """Borra la pantalla al entrar en otra seccion del menu."""
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")
        # >> isatty() = "la salida es una consola de verdad?" (no un archivo
        #    ni un test). os.name == "nt" es Windows -> "cls"; si no, "clear".


def mostrar_menu() -> None:
    print("=" * ANCHO)
    print("KERNELFLOW - Simulador de planificacion SRTF y memoria MVT (Best-Fit)")
    print("Sistemas Operativos - UTN FRRe - Grupo 15")
    print("=" * ANCHO)
    for clave, titulo, descripcion in OPCIONES_MENU:
        # >> Desempaqueta cada tupla del menu en 3 variables.
        print(f"[{clave}] {titulo}")
        print(textwrap.fill(
            descripcion, width=ANCHO, initial_indent="    ", subsequent_indent="    "
        ))
        # >> Corta la descripcion a 80 columnas con sangria de 4 espacios.
        print()


def pedir_ruta_csv() -> Optional[Path]:
    """Pide la ruta de un CSV. Retorna ``None`` si se deja vacia."""
    texto = input("Ruta del archivo CSV (Enter para volver al menu): ")
    # >> input() espera que el usuario escriba algo y aprete Enter.
    texto = texto.strip().strip('"').strip("'")
    # >> Saca espacios y comillas de los bordes. Windows agrega comillas al
    #    "Copiar como ruta de acceso"; asi se puede pegar directo.
    return Path(texto).expanduser() if texto else None
    # >> expanduser() convierte "~" en la carpeta del usuario.


def seguir(accion: str) -> bool:
    """Espera Enter para continuar. Retorna ``False`` si se escribe ``q``."""
    respuesta = input(f"\n[Enter] {accion}   [q + Enter] volver al menu: ")
    return respuesta.strip().lower() != "q"
    # >> .lower() pasa a minusculas, asi "Q" tambien sirve.


def ejecutar_simulacion(ruta_csv: Path) -> int:
    """Arma los modulos del simulador y ejecuta la simulacion paso a paso."""
    # >> LA FUNCION MAS IMPORTANTE DE ESTE ARCHIVO.
    # >> Devuelve un codigo: 0 = todo bien, 1 = error.

    # --- 1) CARGA DEL CSV --------------------------------------------------
    try:
        resultado = cargar_lote(ruta_csv)
    except ErrorCargaProcesos as error:
        print(f"Error: {error}")
        return 1
        # >> Error grave (no existe, no es texto, ningun valido...): se
        #    muestra el mensaje y se vuelve al menu. El programa NO se cae.
    procesos = resultado.procesos
    interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    # >> True si hay una persona usando la consola (pide Enter entre pasos).
    #    False en los tests: muestra todo de corrido.
    if resultado.avisos:
        # Las filas con errores se descartan (nunca se corrigen ni se
        # inventan datos) y se informa cada una antes de simular.
        print(describir_avisos(resultado))
        for aviso in resultado.avisos:
            print(f"  - {aviso}")
        if interactivo and not seguir(
            f"simular con los {len(procesos)} proceso(s) validos"
        ):
            return 0
            # >> El usuario puede elegir no simular (q) despues de ver los avisos.

    # --- 2) ARMADO DE LOS MODULOS -------------------------------------------
    memoria = GestorMemoria()
    # >> Memoria vacia: un hueco de 450K en [100K - 550K).
    try:
        admision = Admision(procesos, memoria)
    except ErrorAdmision as error:
        print(f"Error: {error}")
        return 1

    presentacion = PresentacionConsola(procesos, admision, memoria)
    eventos_paso = []
    # >> LA "LIBRETA" DE MAIN: lista donde se juntan los eventos de un paso.
    planificador = PlanificadorSRTF(admision, memoria, eventos_paso.append)
    # >> Se le pasa eventos_paso.append (SIN parentesis = la funcion en si,
    #    no se ejecuta ahora). Cada vez que el planificador "emite" un
    #    evento, se ejecuta eventos_paso.append(evento). PATRON OBSERVADOR.
    # Si la entrada no es una terminal (por ejemplo, en las pruebas), la
    # simulacion se muestra completa sin esperar teclas.

    presentacion.mostrar_inicio(ruta_csv)
    if interactivo and not seguir("comenzar la simulacion"):
        return 0

    # --- 3) CICLO PRINCIPAL (una vuelta = un instante t) -------------------
    numero_paso = 0
    while True:
        # Los eventos de una finalizacion en t (producidos al ejecutar la
        # unidad t-1) se muestran junto con los arribos del mismo t.

        # (a) Que pasa en el instante t: arribos + SRTF.
        if admision.hay_procesos_pendientes():
            planificador.procesar_instante()

        # (b) Si en este t paso algo, se muestra el paso.
        if eventos_paso:
            # >> Una lista con elementos cuenta como True; vacia, False.
            # >> Por eso los instantes "sin novedades" NO se muestran (el
            #    proceso sigue ejecutando y nada cambia).
            numero_paso += 1
            presentacion.mostrar_paso(eventos_paso, planificador.reloj, numero_paso)
            eventos_paso.clear()
            # >> Se vacia la libreta para el proximo paso.
            if (
                interactivo
                and admision.hay_procesos_pendientes()
                and not seguir("siguiente cambio")
            ):
                print(f"Simulacion detenida en t = {planificador.reloj}.")
                return 0

        # (c) Si ya terminaron todos, se sale del ciclo.
        if not admision.hay_procesos_pendientes():
            break

        # (d) Pasa 1 ut: el proceso en CPU ejecuta y el reloj va de t a t+1.
        #     Si alguno termina, sus eventos quedan en eventos_paso y se
        #     muestran en la proxima vuelta, junto con los arribos de t+1.
        planificador.ejecutar_unidad()

    # --- 4) FIN: informe estadistico -----------------------------------------
    presentacion.mostrar_fin(planificador.reloj)
    # >> planificador.reloj = instante en que termino el ultimo proceso
    #    = tiempo total para el rendimiento.
    return 0


def menu_interactivo() -> int:
    """Muestra el menu hasta que se elige salir."""
    while True:
        # >> Bucle infinito: solo se sale con "return" (opcion 0).
        limpiar_pantalla()
        mostrar_menu()
        opcion = input("Opcion: ").strip()

        if opcion == "0":
            return 0
        if opcion == "1":
            ruta = RUTA_CSV_PREDETERMINADA
        elif opcion == "2":
            ruta = pedir_ruta_csv()
            if ruta is None:
                continue
                # >> Enter vacio -> "continue" vuelve al principio del while (menu).
        else:
            input("Opcion no valida. Presione Enter para continuar...")
            continue

        limpiar_pantalla()
        ejecutar_simulacion(ruta)
        input("\nPresione Enter para volver al menu...")


def crear_argumentos(argumentos: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Interpreta los argumentos de la linea de comandos."""
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
    # >> nargs="?" = el argumento es OPCIONAL (0 o 1). Si no se pone,
    #    archivo = None y se muestra el menu.
    return analizador.parse_args(argumentos)


def main(argumentos: Optional[Sequence[str]] = None) -> int:
    """Ejecuta KernelFlow y retorna un codigo de salida para la consola."""
    # >> LO PRIMERO QUE SE EJECUTA (lo llama __main__.py).
    opciones = crear_argumentos(argumentos)
    try:
        if opciones.archivo is not None:
            return ejecutar_simulacion(opciones.archivo)
            # >> "python -m core archivo.csv" -> simula directo, sin menu.
        if sys.stdin.isatty() and sys.stdout.isatty():
            return menu_interactivo()
            # >> Hay una persona en la consola -> menu.
        return ejecutar_simulacion(RUTA_CSV_PREDETERMINADA)
        # >> Sin consola (ej. salida redirigida a un archivo) -> corre la demo.
    except (EOFError, KeyboardInterrupt):
        print("\nSimulacion interrumpida.")
        return 130
        # >> Ctrl+C (KeyboardInterrupt) o fin de entrada (EOFError): se sale
        #    prolijo con un mensaje. 130 es el codigo convencional de Ctrl+C.


if __name__ == "__main__":
    raise SystemExit(main())
    # >> Solo se ejecuta si se corre este archivo directamente. SystemExit
    #    termina el programa devolviendo el codigo (0, 1 o 130) al sistema.
