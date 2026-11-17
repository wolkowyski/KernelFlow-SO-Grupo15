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
import os
from pathlib import Path
import sys
import textwrap
from typing import Optional, Sequence

from core.admision import Admision, ErrorAdmision
from core.carga import ErrorCargaProcesos, cargar_lote, describir_avisos
from core.memoria import GestorMemoria
from core.planificador import PlanificadorSRTF
from core.presentacion import ANCHO, PresentacionConsola


if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: data/ se distribuye junto al ejecutable.
    DIRECTORIO_PROYECTO = Path(sys.executable).resolve().parent
else:
    DIRECTORIO_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_DATOS = DIRECTORIO_PROYECTO / "data"
RUTA_CSV_PREDETERMINADA = DIRECTORIO_DATOS / "procesos_demo.csv"

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


def limpiar_pantalla() -> None:
    """Borra la pantalla al entrar en otra seccion del menu."""
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def mostrar_menu() -> None:
    print("=" * ANCHO)
    print("KERNELFLOW - Simulador de planificacion SRTF y memoria MVT (Best-Fit)")
    print("Sistemas Operativos - UTN FRRe - Grupo 15")
    print("=" * ANCHO)
    for clave, titulo, descripcion in OPCIONES_MENU:
        print(f"[{clave}] {titulo}")
        print(textwrap.fill(
            descripcion, width=ANCHO, initial_indent="    ", subsequent_indent="    "
        ))
        print()


def pedir_ruta_csv() -> Optional[Path]:
    """Pide la ruta de un CSV. Retorna ``None`` si se deja vacia."""
    texto = input("Ruta del archivo CSV (Enter para volver al menu): ")
    texto = texto.strip().strip('"').strip("'")
    return Path(texto).expanduser() if texto else None


def seguir(accion: str) -> bool:
    """Espera Enter para continuar. Retorna ``False`` si se escribe ``q``."""
    respuesta = input(f"\n[Enter] {accion}   [q + Enter] volver al menu: ")
    return respuesta.strip().lower() != "q"


def ejecutar_simulacion(ruta_csv: Path) -> int:
    """Arma los modulos del simulador y ejecuta la simulacion paso a paso."""
    try:
        resultado = cargar_lote(ruta_csv)
    except ErrorCargaProcesos as error:
        print(f"Error: {error}")
        return 1
    procesos = resultado.procesos
    interactivo = sys.stdin.isatty() and sys.stdout.isatty()
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

    memoria = GestorMemoria()
    try:
        admision = Admision(procesos, memoria)
    except ErrorAdmision as error:
        print(f"Error: {error}")
        return 1

    presentacion = PresentacionConsola(procesos, admision, memoria)
    eventos_paso = []
    planificador = PlanificadorSRTF(admision, memoria, eventos_paso.append)
    # Si la entrada no es una terminal (por ejemplo, en las pruebas), la
    # simulacion se muestra completa sin esperar teclas.

    presentacion.mostrar_inicio(ruta_csv)
    if interactivo and not seguir("comenzar la simulacion"):
        return 0

    numero_paso = 0
    while True:
        # Los eventos de una finalizacion en t (producidos al ejecutar la
        # unidad t-1) se muestran junto con los arribos del mismo t.
        if admision.hay_procesos_pendientes():
            planificador.procesar_instante()
        if eventos_paso:
            numero_paso += 1
            presentacion.mostrar_paso(eventos_paso, planificador.reloj, numero_paso)
            eventos_paso.clear()
            if (
                interactivo
                and admision.hay_procesos_pendientes()
                and not seguir("siguiente cambio")
            ):
                print(f"Simulacion detenida en t = {planificador.reloj}.")
                return 0
        if not admision.hay_procesos_pendientes():
            break
        planificador.ejecutar_unidad()

    presentacion.mostrar_fin(planificador.reloj)
    return 0


def menu_interactivo() -> int:
    """Muestra el menu hasta que se elige salir."""
    while True:
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
    return analizador.parse_args(argumentos)


def main(argumentos: Optional[Sequence[str]] = None) -> int:
    """Ejecuta KernelFlow y retorna un codigo de salida para la consola."""
    opciones = crear_argumentos(argumentos)
    try:
        if opciones.archivo is not None:
            return ejecutar_simulacion(opciones.archivo)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return menu_interactivo()
        return ejecutar_simulacion(RUTA_CSV_PREDETERMINADA)
    except (EOFError, KeyboardInterrupt):
        print("\nSimulacion interrumpida.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
