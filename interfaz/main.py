"""Punto de entrada de la version completa de KernelFlow.

Menu con logo y guia rapida, navegacion entre pasos con una tecla (B / F /
Q) y guardado de la simulacion (G). La simulacion la hacen los modulos de
``core/``; aca solo se elige como mostrarla.

Uso, desde la raiz del proyecto:

    python3 main.py                    (menu)
    python3 main.py data/lote.csv      (simula ese archivo)
    python3 main.py --sin-color        (sin colores)
    python3 main.py --pantalla-fija    (limpia la pantalla en cada paso)
    python3 main.py --exportar         (guarda TXT y HTML al terminar)
"""

import argparse
from contextlib import redirect_stdout
import io
import sys
import textwrap
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from core.admision import Admision, ErrorAdmision
from core.carga import ErrorCargaProcesos, cargar_lote, describir_avisos
from core.main import (
    DIRECTORIO_DATOS,
    DIRECTORIO_PROYECTO,
    RUTA_CSV_PREDETERMINADA,
    limpiar_pantalla,
)
from core.memoria import GestorMemoria
from interfaz.entrada import elegir_csv, leer_tecla
from interfaz.estilo import Estilo, a_ascii, preparar_terminal, quitar_colores
from interfaz.exportar import guardar_simulacion
from interfaz.panel import (
    PanelConsola,
    PlanificadorConGantt,
    ancho_terminal,
    centrar_linea,
    imprimir_bloque,
    imprimir_centrado,
)


DIRECTORIO_RESULTADOS = DIRECTORIO_PROYECTO / "resultados"
RUTA_LOGO_UTN = DIRECTORIO_DATOS / "logo_utn.txt"

# Se define en main() segun la terminal y la opcion --sin-color.
ESTILO = Estilo()
# El panel siempre se arma con colores y bordes Unicode para poder exportarlo
# a HTML; al mostrarlo se adapta a lo que soporta la terminal.
ESTILO_COMPLETO = Estilo(color=True, unicode=True)
# Pantalla fija: se limpia la terminal en cada paso (como un tablero).
PANTALLA_FIJA = False
# Guardar TXT y HTML automaticamente al terminar (opcion --exportar).
EXPORTAR_AL_TERMINAR = False


OPCIONES_MENU = (
    (
        "1",
        "Iniciar simulacion con el CSV de prueba",
        "Ejecuta data/procesos_demo.csv: 6 procesos que muestran apropiacion "
        "SRTF, un proceso en LISTO_SUSPENDIDO y la reutilizacion de memoria.",
    ),
    (
        "2",
        "Elegir otro archivo CSV",
        "Lista los lotes de prueba de la carpeta data/ y permite escribir la "
        "ruta de un archivo propio (hasta 10 procesos, formato: "
        "id,tamanio,arribo,irrupcion).",
    ),
    (
        "3",
        "Ver guia rapida",
        "Explica el formato del CSV, las reglas del simulador (MVT, Best-Fit, "
        "SRTF, multiprogramacion 5), los estados y los controles.",
    ),
    (
        "4",
        "Cambiar modo de pantalla",
        "Alterna entre HISTORIAL (los pasos quedan uno debajo del otro) y "
        "PANTALLA FIJA (se limpia en cada paso, como un tablero). Tambien se "
        "cambia con la tecla F durante la simulacion.",
    ),
    ("0", "Salir", "Cierra el simulador."),
)


def mostrar_menu() -> None:
    ancho = ancho_terminal()

    try:
        logo = RUTA_LOGO_UTN.read_text(encoding="utf-8").splitlines()
    except OSError:
        logo = []
    if logo:
        margen_logo = min(
            len(linea) - len(linea.lstrip()) for linea in logo if linea.strip()
        )
        imprimir_bloque(
            [ESTILO.c(linea[margen_logo:], "azul") for linea in logo]
        )

    e = ESTILO
    doble = e.c(e.linea(ancho, doble=True), "cian")
    simple = e.c(e.linea(ancho), "gris")
    print(doble)
    imprimir_centrado(e.c("K E R N E L F L O W", "negrita", "cian"))
    imprimir_centrado(
        "Simulador de planificacion SRTF y memoria MVT (Best-Fit)"
    )
    print(doble)
    imprimir_centrado(e.c("GRUPO 15", "negrita"))
    imprimir_bloque([e.c(nombre, "gris") for nombre in (
        "BADER SORAIRE Cain Abel",
        "GONZALEZ Carlos Alfredo",
        "LEIVA ROMERO Agustin Nazareno",
        "SEELAFF Mauricio Guillermo",
        "TORRES Alejandro Valentin",
        "WOLKOWYSKI Braian Leonel",
        "ZURANO LANG Lucas Maximiliano",
    )])
    print(simple)
    lineas = []
    ancho_texto = max(30, min(ancho - 10, 72))
    for clave, titulo, descripcion in OPCIONES_MENU:
        lineas.append(e.c(f"[{clave}]", "amarillo", "negrita") + " " + e.c(titulo, "negrita"))
        lineas.extend(
            e.c(linea, "gris") for linea in textwrap.wrap(
                descripcion,
                width=ancho_texto,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
        lineas.append("")
    imprimir_bloque(lineas[:-1])
    print(simple)
    imprimir_centrado(
        e.c("Modo de pantalla actual: ", "gris")
        + e.c("PANTALLA FIJA" if PANTALLA_FIJA else "HISTORIAL", "cian", "negrita")
    )


def mostrar_guia_rapida() -> None:
    """Explica la entrada, las reglas y la lectura de la simulacion."""
    guia = """
============================================================
  GUIA RAPIDA DE KERNELFLOW
============================================================
1. Preparar el archivo CSV
   Una fila representa un proceso. No escriba encabezados.
   Formato: id,tamanio,tiempo_arribo,tiempo_irrupcion
   Ejemplo: P1,120,0,8
   - id: nombre unico del proceso.
   - tamanio: memoria requerida en KB, entre 1 y 450.
   - tiempo_arribo: instante de llegada, desde 0.
   - tiempo_irrupcion: tiempo de irrupcion (rafaga), mayor que 0.
   Se admiten entre 1 y 10 procesos. Los numeros deben ser enteros.

2. Elegir como iniciar
   [1] Usa el CSV de prueba incluido en data/procesos_demo.csv.
   [2] Lista los CSV de la carpeta data/ para elegir uno por
       numero, o permite escribir la ruta de otro archivo.
   [3] Muestra esta guia.
   [0] Cierra el simulador.

3. Que hace el simulador
   - Reserva 100K para el sistema operativo y 450K para procesos.
   - MVT crea particiones variables. Best-Fit asigna el hueco libre
     mas pequeno donde entre cada proceso.
   - Pueden estar admitidos hasta 5 procesos al mismo tiempo
     (EJECUCION + LISTO + LISTO_SUSPENDIDO).
   - SRTF ejecuta el proceso LISTO con menor tiempo restante.
     Si llega otro mas corto, le quita la CPU (apropiacion).
   - Al terminar un proceso, libera su memoria y se vuelve a
     intentar el ingreso de los que esperan.

4. Como leer la pantalla
   Cada paso empieza con "COMIENZO DEL PASO" y termina con
   "FIN DEL PASO". Dentro de cada paso se listan todos los
   cambios de estado ocurridos (llegadas, admisiones,
   suspensiones, apropiaciones y finalizaciones) con su motivo.
   Luego se muestran en tablas: los procesos, la memoria
   principal (particiones), la CPU, la cola LISTO (en el orden
   en que SRTF los elegiria) y la cola LISTO_SUSPENDIDO, con el
   tiempo restante y la espera acumulada de cada proceso.
   Si los colores no se ven bien, use la opcion --sin-color.
   NUEVO espera su llegada o un cupo; LISTO espera la CPU;
   LISTO_SUSPENDIDO espera memoria; EJECUCION usa la CPU;
   TERMINADO ya completo su trabajo. La CPU puede estar OCIOSA.

5. Columnas de la tabla de procesos
   T.Irrup.: tiempo de irrupcion (CPU total que necesita).
   T.Ejec.: tiempo de CPU ya consumido.
   T.Rest.: tiempo de CPU que le falta (lo usa SRTF).
   Espera: tiempo en el sistema sin usar la CPU hasta ahora.
   NUEVO*: el proceso ya llego pero espera cupo (maximo 5).

6. Informe final
   Al terminar se muestran, por proceso, el tiempo de retorno
   (finalizacion - arribo), de espera (retorno - irrupcion) y de
   respuesta (primer uso de CPU - arribo), sus promedios y el
   rendimiento (trabajos terminados / tiempo total).

7. Controles durante la simulacion
   Espacio, Enter o N: ver el siguiente cambio relevante.
   B: volver al paso anterior para revisarlo (Espacio retoma).
   F: alternar entre historial y pantalla fija (tablero).
   Q: detener la simulacion y volver al menu.
   Al terminar (o al detenerla), G guarda la simulacion en la
   carpeta resultados/ como TXT y como HTML con colores.
   El reloj avanza internamente; no hace falta pulsar una tecla
   por cada unidad de tiempo.

8. Graficos
   Mapa de memoria: barra proporcional con el SO, cada particion
   (un color por proceso) y los huecos libres.
   [SRTF]: candidatos ordenados por tiempo restante y el elegido.
   Uso de la CPU: que proceso uso la CPU en cada instante.
   Al final: grafico de barras de retorno/espera y diagrama de
   Gantt con una fila por proceso.
============================================================"""
    imprimir_bloque(guia.strip("\n").splitlines())


def capturar(funcion: Callable, *argumentos) -> str:
    """Ejecuta una funcion que imprime y retorna lo que imprimio."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        funcion(*argumentos)
    return buffer.getvalue()


def para_pantalla(texto: str) -> str:
    """Adapta una pantalla a lo que soporta la terminal actual."""
    if not ESTILO.color:
        texto = quitar_colores(texto)
    if not ESTILO.unicode:
        texto = a_ascii(texto)
    return texto


def mostrar_pantalla(texto: str, aviso: str = "") -> None:
    if PANTALLA_FIJA:
        limpiar_pantalla()
    if aviso:
        print(para_pantalla(ESTILO_COMPLETO.c(
            f" {aviso} ".center(ancho_terminal(), "◄"), "negro", "fondo_amarillo")))
    print(para_pantalla(texto), end="")


def aviso_revision(indice: int, total: int) -> str:
    if indice >= total - 1:
        return ""
    actual = "los procesos cargados" if indice == 0 else f"el paso {indice}"
    return (f"REVISANDO {actual.upper()} - la simulacion va por el paso "
            f"{total - 1} - [Espacio] para volver a avanzar")


def navegar(pantallas: List[str], inicio: bool = False) -> bool:
    """Atiende las teclas entre pasos. ``True`` avanza; ``False`` sale.

    Espacio/Enter avanza, B vuelve al paso anterior (para revisar), F cambia
    entre historial y pantalla fija y Q vuelve al menu.
    """
    global PANTALLA_FIJA
    indice = len(pantallas) - 1
    while True:
        revisando = indice < len(pantallas) - 1
        if inicio and not revisando:
            avance = "comenzar la simulacion"
        else:
            avance = "paso siguiente" if revisando else "siguiente cambio"
        fija = "SI" if PANTALLA_FIJA else "NO"
        controles = (
            f"[Espacio/Enter] {avance}   [B] paso anterior   "
            f"[F] pantalla fija: {fija}   [Q] menu: "
        )
        print("\n" + centrar_linea(para_pantalla(
            ESTILO_COMPLETO.c(controles, "cian"))), end="", flush=True)
        tecla = leer_tecla()
        print()
        if tecla in (" ", "\r", "\n", "n", "N"):
            if not revisando:
                return True
            indice += 1
        elif tecla in ("b", "B"):
            if indice > 0:
                indice -= 1
        elif tecla in ("f", "F"):
            PANTALLA_FIJA = not PANTALLA_FIJA
        elif tecla in ("q", "Q"):
            return False
        else:
            continue
        mostrar_pantalla(pantallas[indice], aviso_revision(indice, len(pantallas)))


def exportar(pantallas: Sequence[str], ruta_csv: Path) -> None:
    try:
        ruta_txt, ruta_html = guardar_simulacion(
            pantallas, DIRECTORIO_RESULTADOS, ruta_csv.name
        )
    except OSError as error:
        imprimir_centrado(f"No se pudo guardar la simulacion: {error}")
        return
    imprimir_centrado("Simulacion guardada en:")
    imprimir_bloque((f"  {ruta_txt}", f"  {ruta_html}"))


def cierre(pantallas: Sequence[str], ruta_csv: Path, interactivo: bool) -> int:
    """Ofrece guardar la simulacion y espera para volver al menu."""
    if EXPORTAR_AL_TERMINAR:
        exportar(pantallas, ruta_csv)
    if not interactivo:
        return 0
    guardada = EXPORTAR_AL_TERMINAR
    while True:
        if guardada:
            opciones = "[Enter] volver al menu"
        else:
            opciones = ("[G] guardar la simulacion (TXT y HTML con colores)   "
                        "[Enter] volver al menu")
        print("\n" + centrar_linea(para_pantalla(
            ESTILO_COMPLETO.c(opciones + ": ", "cian"))), end="", flush=True)
        tecla = leer_tecla()
        print()
        if tecla in ("g", "G") and not guardada:
            exportar(pantallas, ruta_csv)
            guardada = True
        elif tecla in (" ", "\r", "\n", "q", "Q"):
            return 0


def menu_interactivo() -> int:
    """Permite elegir el archivo y volver al menu tras la simulacion."""
    global PANTALLA_FIJA
    while True:
        limpiar_pantalla()
        mostrar_menu()
        try:
            opcion = input(centrar_linea("Opcion: ")).strip()
        except EOFError:
            return 0

        if opcion == "0":
            return 0
        if opcion == "1":
            ruta = RUTA_CSV_PREDETERMINADA
            limpiar_pantalla()
        elif opcion == "2":
            ruta = elegir_csv()
            if ruta is None:
                continue
            limpiar_pantalla()
        elif opcion == "3":
            limpiar_pantalla()
            mostrar_guia_rapida()
            input("\n" + centrar_linea("Presione Enter para volver al menu..."))
            continue
        elif opcion == "4":
            PANTALLA_FIJA = not PANTALLA_FIJA
            continue
        else:
            imprimir_centrado("Opcion no valida.")
            input(centrar_linea("Presione Enter para continuar..."))
            continue

        if ejecutar_simulacion(ruta) != 0:
            input("\n" + centrar_linea("Presione Enter para volver al menu..."))


def crear_argumentos(argumentos: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Interpreta los argumentos de la aplicacion de consola."""
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
    analizador.add_argument(
        "--sin-color",
        action="store_true",
        help="Muestra la salida sin colores (util si la terminal no los soporta).",
    )
    analizador.add_argument(
        "--pantalla-fija",
        action="store_true",
        help="Limpia la pantalla en cada paso, como un tablero (tecla F).",
    )
    analizador.add_argument(
        "--exportar",
        action="store_true",
        help="Guarda la simulacion en resultados/ (TXT y HTML) al terminar.",
    )
    return analizador.parse_args(argumentos)


def ejecutar_simulacion(ruta_csv: Path) -> int:
    """Arma la simulacion con los componentes de ``core.py`` y la muestra.

    La carga, la memoria, la admision y el planificador son los del nucleo;
    aca solo se elige como presentar cada paso.
    """
    try:
        resultado = cargar_lote(ruta_csv)
    except ErrorCargaProcesos as error:
        imprimir_centrado(f"Error: {error}")
        return 1
    procesos = resultado.procesos
    if resultado.avisos:
        # Las filas con errores se descartan (nunca se corrigen ni se
        # inventan datos) y se informa cada una antes de simular.
        imprimir_centrado(para_pantalla(ESTILO_COMPLETO.c(
            describir_avisos(resultado), "amarillo", "negrita")))
        imprimir_bloque([para_pantalla(ESTILO_COMPLETO.c(f"- {aviso}", "amarillo"))
                         for aviso in resultado.avisos])
        if sys.stdin.isatty() and sys.stdout.isatty():
            respuesta = input("\n" + centrar_linea(
                f"[Enter] simular con los {len(procesos)} proceso(s) validos   "
                "[q + Enter] volver al menu: "))
            if respuesta.strip().lower() == "q":
                return 0

    memoria = GestorMemoria()
    try:
        admision = Admision(procesos, memoria)
    except ErrorAdmision as error:
        imprimir_centrado(f"Error: {error}")
        return 1
    panel = PanelConsola(procesos, admision, memoria, ESTILO_COMPLETO)
    eventos_paso: List = []
    planificador = PlanificadorConGantt(admision, memoria, eventos_paso.append)
    panel.linea_tiempo = planificador.linea_tiempo
    interactivo = sys.stdin.isatty() and sys.stdout.isatty()

    # Cada pantalla se guarda para poder volver atras (B) y exportarla.
    pantallas = [capturar(panel.mostrar_inicio, ruta_csv)]
    mostrar_pantalla(pantallas[0])
    if interactivo and not navegar(pantallas, inicio=True):
        return cierre(pantallas, ruta_csv, interactivo)

    numero_paso = 0
    while True:
        # Los eventos de una finalizacion en t (producidos al ejecutar la
        # unidad t-1) se muestran junto con los arribos del mismo t.
        if admision.hay_procesos_pendientes():
            planificador.procesar_instante()
        if eventos_paso:
            numero_paso += 1
            pantallas.append(capturar(
                panel.mostrar_paso, eventos_paso, planificador.reloj, numero_paso
            ))
            eventos_paso.clear()
            mostrar_pantalla(pantallas[-1])
            if interactivo and not navegar(pantallas):
                imprimir_centrado(
                    f"Simulacion detenida en t = {planificador.reloj}."
                )
                return cierre(pantallas, ruta_csv, interactivo)
        if not admision.hay_procesos_pendientes():
            break
        planificador.ejecutar_unidad()

    pantallas.append(capturar(panel.mostrar_fin, planificador.reloj))
    mostrar_pantalla(pantallas[-1])
    return cierre(pantallas, ruta_csv, interactivo)


def main(argumentos: Optional[Sequence[str]] = None) -> int:
    """Ejecuta KernelFlow y retorna un codigo apto para la consola de Linux."""
    global ESTILO, PANTALLA_FIJA, EXPORTAR_AL_TERMINAR
    opciones = crear_argumentos(argumentos)
    preparar_terminal()
    ESTILO = Estilo.detectar(sin_color=opciones.sin_color)
    PANTALLA_FIJA = opciones.pantalla_fija
    EXPORTAR_AL_TERMINAR = opciones.exportar
    try:
        if opciones.archivo is not None:
            return ejecutar_simulacion(opciones.archivo)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return menu_interactivo()
        return ejecutar_simulacion(RUTA_CSV_PREDETERMINADA)
    except (EOFError, KeyboardInterrupt):
        print()
        imprimir_centrado("Simulacion interrumpida.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
