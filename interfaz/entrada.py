"""Entrada por teclado y eleccion del archivo CSV de la version completa."""

import os
import sys
from pathlib import Path
from typing import Optional

from core.main import DIRECTORIO_DATOS, limpiar_pantalla
from interfaz.panel import (
    ancho_terminal,
    centrar_linea,
    imprimir_bloque,
    imprimir_centrado,
)


def leer_tecla() -> str:
    """Lee una sola tecla sin esperar Enter, en Linux y en Windows.

    Las teclas especiales (flechas, F1, Inicio, etc.) envian varios
    caracteres seguidos; se leen todos y se devuelve ``""`` para que no
    se tomen como otra tecla ni queden escritos en la siguiente pregunta.
    """
    if os.name == "nt":
        import msvcrt

        tecla = msvcrt.getwch()
        if tecla in ("\x00", "\xe0"):  # flechas y teclas de funcion
            msvcrt.getwch()
            return ""
        return tecla

    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    configuracion_anterior = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        tecla = os.read(descriptor, 1).decode(errors="ignore")
        if tecla == "\x1b":  # comienzo de una secuencia de tecla especial
            while select.select([descriptor], [], [], 0.05)[0]:
                os.read(descriptor, 32)
            return ""
        return tecla
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, configuracion_anterior)


def seleccionar_archivo_csv(directorio_inicial: Path) -> Optional[Path]:
    """Abre un explorador de archivos para elegir un CSV de procesos."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print(
            "No se pudo abrir el explorador: "
            "falta tkinter en esta instalacion de Python."
        )
        return None

    ventana = None
    try:
        ventana = tk.Tk()
        ventana.withdraw()
        ruta = filedialog.askopenfilename(
            parent=ventana,
            title="Seleccionar archivo CSV de procesos",
            initialdir=str(directorio_inicial),
            filetypes=(("Archivos CSV", "*.csv"), ("Todos los archivos", "*")),
        )
        return Path(ruta) if ruta else None
    except (tk.TclError, OSError):
        print(
            "No se pudo abrir el explorador. "
            "Verifique que haya un entorno grafico disponible."
        )
        return None
    finally:
        if ventana is not None:
            ventana.destroy()


def contar_procesos(ruta: Path) -> str:
    """Cuenta las filas no vacias de un CSV para mostrarlas en la lista."""
    try:
        with ruta.open(encoding="utf-8-sig") as archivo:
            cantidad = sum(1 for linea in archivo if linea.strip())
    except (OSError, UnicodeDecodeError):
        return "no se puede leer"
    return f"{cantidad} proceso(s)"


def elegir_csv() -> Optional[Path]:
    """Muestra los CSV de data/ y permite elegir uno o escribir otra ruta.

    No depende de un entorno grafico; el explorador de archivos queda como
    opcion adicional para quien tenga tkinter disponible.
    """
    archivos = sorted(
        ruta for ruta in DIRECTORIO_DATOS.glob("*.csv") if ruta.is_file()
    )
    while True:
        limpiar_pantalla()
        ancho = ancho_terminal()
        print("=" * ancho)
        imprimir_centrado("SELECCIONAR ARCHIVO CSV")
        print("=" * ancho)
        lineas = []
        if archivos:
            ancho_nombre = max(len(ruta.name) for ruta in archivos)
            for numero, ruta in enumerate(archivos, start=1):
                lineas.append(
                    f"[{numero}] {ruta.name:<{ancho_nombre}}  "
                    f"({contar_procesos(ruta)})"
                )
        else:
            lineas.append(f"No hay archivos CSV en {DIRECTORIO_DATOS}.")
        lineas.extend((
            "",
            "[R] Escribir la ruta de otro archivo CSV",
            "[E] Buscarlo con el explorador de archivos (requiere entorno grafico)",
            "[0] Volver al menu",
        ))
        imprimir_bloque(lineas)
        print("-" * ancho)

        opcion = input(centrar_linea("Opcion: ")).strip().lower()
        if opcion == "0":
            return None
        if opcion.isdigit() and 1 <= int(opcion) <= len(archivos):
            return archivos[int(opcion) - 1]
        if opcion == "r":
            texto = input(centrar_linea("Ruta del archivo CSV: "))
            ruta = Path(texto.strip().strip('"').strip("'")).expanduser()
            if ruta.is_file():
                return ruta
            imprimir_centrado(f"No se encontro el archivo '{ruta}'.")
        elif opcion == "e":
            ruta = seleccionar_archivo_csv(DIRECTORIO_DATOS)
            if ruta is not None:
                return ruta
            imprimir_centrado("No se selecciono ningun archivo.")
        else:
            imprimir_centrado("Opcion no valida.")
        input(centrar_linea("Presione Enter para continuar..."))
