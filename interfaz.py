"""KernelFlow - interfaz de consola con colores, tablas y graficos.

Este archivo NO contiene logica de simulacion. Importa ``core.py`` (donde
estan la carga del CSV, la memoria MVT/Best-Fit, la admision, el planificador
SRTF y las estadisticas) y solo cambia la forma de mostrar los resultados:

    1. Estilo: colores ANSI y tablas con bordes, sin librerias externas
    2. Exportacion de la simulacion a TXT y HTML con colores
    3. Linea de tiempo de la CPU (para el diagrama de Gantt)
    4. Panel de la terminal: tablas, mapa de memoria, decision SRTF,
       barras de progreso, uso de la CPU, grafico de barras y Gantt
    5. Menu con navegacion entre pasos (B / F / Q) y guardado (G)

Uso:

    python3 interfaz.py                    (menu)
    python3 interfaz.py data/lote.csv      (simula ese archivo)
    python3 interfaz.py --sin-color        (sin colores)
    python3 interfaz.py --pantalla-fija    (limpia la pantalla en cada paso)
    python3 interfaz.py --exportar         (guarda TXT y HTML al terminar)

La version base, sin nada de esto, se ejecuta con ``python3 core.py``.
"""

import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime
import html
import io
import math
import os
from pathlib import Path
import re
import shutil
import sys
import textwrap
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from core import (
    DIRECTORIO_PROYECTO,
    ESTADO_EJECUCION,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_NUEVO,
    ESTADO_TERMINADO,
    GRADO_MAXIMO_MULTIPROGRAMACION,
    RUTA_CSV_PREDETERMINADA,
    RUTA_LOGO_UTN,
    TIPO_APROPIACION,
    TIPO_ARRIBO,
    TIPO_CPU_OCIOSA,
    TIPO_FINALIZACION,
    TIPO_INICIO,
    TIPO_MEMORIA_LIBERADA,
    TIPO_NUEVA_ADMISION,
    TIPO_SIGUE_SUSPENDIDO,
    AdministradorAdmision,
    Admision,
    ErrorAdmision,
    ErrorCargaProcesos,
    EventoPlanificador,
    GestorMemoria,
    PlanificadorSRTF,
    PresentacionConsola,
    Proceso,
    calcular_estadisticas,
    cargar_procesos,
    elegir_csv,
    leer_tecla,
    limpiar_pantalla,
)


# ============================================================================
# 1. ESTILO: COLORES ANSI Y TABLAS CON BORDES
# Los colores se activan solo si la salida es una terminal y no se pidio
#   desactivarlos (--sin-color o NO_COLOR). Si la terminal no muestra los
#   bordes Unicode, las tablas se dibujan con +, - y |.
# ============================================================================

_PATRON_ANSI = re.compile(r"\x1b\[[0-9;]*m")

CODIGOS = {
    "negrita": "1",
    "tenue": "2",
    "rojo": "91",
    "verde": "92",
    "amarillo": "93",
    "azul": "94",
    "magenta": "95",
    "cian": "96",
    "blanco": "97",
    "gris": "90",
    "negro": "30",
    "fondo_rojo": "41",
    "fondo_verde": "42",
    "fondo_amarillo": "43",
    "fondo_azul": "44",
    "fondo_magenta": "45",
    "fondo_cian": "46",
    "fondo_blanco": "47",
    "fondo_gris": "100",
}

# Colores asignados a cada proceso (en orden de carga) para que se reconozca
# igual en el mapa de memoria, el diagrama de Gantt y las tablas.
PALETA_PROCESOS = ("cian", "amarillo", "verde", "azul", "rojo", "blanco")

# Equivalentes ASCII de los caracteres especiales (mismo ancho: 1 a 1).
_A_ASCII = str.maketrans({
    "┌": "+", "┬": "+", "┐": "+", "├": "+", "┼": "+", "┤": "+",
    "└": "+", "┴": "+", "┘": "+", "─": "-", "│": "|", "═": "=",
    "█": "#", "░": ".", "▒": ":", "►": ">", "◄": "<", "·": ".",
    "→": ">", "≤": "<",
})


def quitar_colores(texto: str) -> str:
    """Elimina los codigos de color ANSI."""
    return _PATRON_ANSI.sub("", texto)


def a_ascii(texto: str) -> str:
    """Reemplaza bordes y simbolos Unicode por equivalentes ASCII."""
    return texto.translate(_A_ASCII)

_BORDES_UNICODE = {
    "sup": ("┌", "┬", "┐"),
    "med": ("├", "┼", "┤"),
    "inf": ("└", "┴", "┘"),
    "h": "─",
    "v": "│",
}
_BORDES_ASCII = {
    "sup": ("+", "+", "+"),
    "med": ("+", "+", "+"),
    "inf": ("+", "+", "+"),
    "h": "-",
    "v": "|",
}


def largo_visible(texto: str) -> int:
    """Largo del texto en pantalla, sin contar los codigos de color."""
    return len(_PATRON_ANSI.sub("", texto))


def rellenar(texto: str, ancho: int, alineacion: str = "<") -> str:
    """Completa con espacios hasta ``ancho`` columnas visibles."""
    falta = max(0, ancho - largo_visible(texto))
    if alineacion == ">":
        return " " * falta + texto
    if alineacion == "^":
        izquierda = falta // 2
        return " " * izquierda + texto + " " * (falta - izquierda)
    return texto + " " * falta


@dataclass(frozen=True)
class Celda:
    """Valor de una tabla con estilos de color opcionales."""

    texto: object
    estilos: Tuple[str, ...] = ()
    alineacion: Optional[str] = None


ValorCelda = Union[Celda, object]


class Estilo:
    """Decide si se usan colores y bordes Unicode, y aplica el formato."""

    def __init__(self, color: bool = False, unicode: bool = False) -> None:
        self.color = color
        self.unicode = unicode
        self.bordes = _BORDES_UNICODE if unicode else _BORDES_ASCII

    @classmethod
    def detectar(cls, flujo=None, sin_color: bool = False) -> "Estilo":
        flujo = flujo if flujo is not None else sys.stdout
        es_terminal = hasattr(flujo, "isatty") and flujo.isatty()
        color = (
            es_terminal
            and not sin_color
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )
        codificacion = getattr(flujo, "encoding", None) or "ascii"
        try:
            "┌─┐│└┘├┼┤┬┴═".encode(codificacion)
            unicode = es_terminal
        except (LookupError, UnicodeEncodeError):
            unicode = False
        return cls(color=color, unicode=unicode)

    def c(self, texto: object, *estilos: str) -> str:
        """Aplica estilos de color a un texto (si los colores estan activos)."""
        texto = str(texto)
        if not self.color or not estilos:
            return texto
        codigos = ";".join(CODIGOS[nombre] for nombre in estilos if nombre)
        return f"\x1b[{codigos}m{texto}\x1b[0m" if codigos else texto

    def linea(self, ancho: int, doble: bool = False) -> str:
        """Linea horizontal de separacion."""
        if self.unicode:
            return ("═" if doble else "─") * ancho
        return ("=" if doble else "-") * ancho

    def tabla(
        self,
        encabezados: Sequence[str],
        filas: Sequence[Sequence[ValorCelda]],
        titulo: str = "",
        color_titulo: Sequence[str] = ("negrita", "cian"),
        vacia: str = "(vacia)",
    ) -> List[str]:
        """Dibuja una tabla con bordes y la retorna como lista de lineas.

        Los numeros se alinean a la derecha y el texto a la izquierda. Si no
        hay filas, se muestra una fila con el texto ``vacia``.
        """
        celdas: List[List[Celda]] = []
        for fila in filas:
            celdas.append([
                valor if isinstance(valor, Celda) else Celda(valor)
                for valor in fila
            ])

        anchos = [len(str(nombre)) for nombre in encabezados]
        for fila in celdas:
            for indice, celda in enumerate(fila):
                anchos[indice] = max(anchos[indice], largo_visible(str(celda.texto)))
        ancho_interior = sum(anchos) + 3 * len(anchos) - 1
        if not celdas:
            ancho_extra = len(vacia) + 2 - ancho_interior
            if ancho_extra > 0:
                anchos[-1] += ancho_extra
                ancho_interior += ancho_extra

        b = self.bordes
        gris = ("gris",)

        def borde(tipo: str) -> str:
            izquierda, medio, derecha = b[tipo]
            tramo = medio.join(b["h"] * (ancho + 2) for ancho in anchos)
            return self.c(izquierda + tramo + derecha, *gris)

        separador = self.c(b["v"], *gris)

        def formar(valores: Sequence[Celda], negrita: bool = False) -> str:
            partes = []
            for celda, ancho in zip(valores, anchos):
                alineacion = celda.alineacion or (
                    ">" if _es_numero(celda.texto) else "<"
                )
                texto = rellenar(str(celda.texto), ancho, alineacion)
                estilos = celda.estilos + (("negrita",) if negrita else ())
                partes.append(" " + self.c(texto, *estilos) + " ")
            return separador + separador.join(partes) + separador

        lineas = []
        if titulo:
            ancho_total = ancho_interior + 2
            lineas.append(rellenar(self.c(titulo, *color_titulo), ancho_total, "^")
                          if len(titulo) <= ancho_total
                          else self.c(titulo, *color_titulo))
        lineas.append(borde("sup"))
        lineas.append(formar([Celda(e, ("cian",)) for e in encabezados], negrita=True))
        lineas.append(borde("med"))
        if celdas:
            lineas.extend(formar(fila) for fila in celdas)
        else:
            texto = rellenar(self.c(vacia, "gris"), ancho_interior, "^")
            lineas.append(separador + texto + separador)
        lineas.append(borde("inf"))
        return lineas


def _es_numero(valor: object) -> bool:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return True
    texto = str(valor).strip()
    return bool(texto) and texto.replace(".", "", 1).isdigit()


def acomodar_en_filas(
    bloques: Sequence[List[str]], ancho_maximo: int, separacion: int = 3
) -> List[str]:
    """Ubica bloques de lineas uno al lado del otro mientras entren.

    Los que no entran en el ancho disponible pasan a la fila siguiente.
    """
    lineas: List[str] = []
    fila_actual: List[List[str]] = []
    ancho_actual = 0

    def volcar() -> None:
        if not fila_actual:
            return
        anchos = [max(largo_visible(l) for l in bloque) for bloque in fila_actual]
        alto = max(len(bloque) for bloque in fila_actual)
        if lineas:
            lineas.append("")
        for indice in range(alto):
            partes = []
            for bloque, ancho in zip(fila_actual, anchos):
                texto = bloque[indice] if indice < len(bloque) else ""
                partes.append(rellenar(texto, ancho))
            lineas.append((" " * separacion).join(partes).rstrip())

    for bloque in bloques:
        if not bloque:
            continue
        ancho = max(largo_visible(linea) for linea in bloque)
        necesario = ancho if not fila_actual else ancho_actual + separacion + ancho
        if fila_actual and necesario > ancho_maximo:
            volcar()
            fila_actual, ancho_actual = [], 0
            necesario = ancho
        fila_actual.append(bloque)
        ancho_actual = necesario
    volcar()
    return lineas


def preparar_terminal() -> None:
    """Habilita colores ANSI y UTF-8 en la consola de Windows."""
    if os.name != "nt":
        return
    os.system("")  # activa el procesamiento de secuencias ANSI en conhost
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None and flujo.isatty():
            try:
                reconfigurar(encoding="utf-8")
            except (ValueError, OSError):
                pass


# ============================================================================
# 2. EXPORTACION A TXT Y HTML
# El HTML conserva los colores de la terminal, para el informe o adjuntarlo.
# ============================================================================

_PATRON_SGR = re.compile(r"\x1b\[([0-9;]*)m")

_COLOR_TEXTO: Dict[str, str] = {
    "30": "#1e1e1e", "90": "#8b8b8b", "91": "#ff6b6b", "92": "#5fd068",
    "93": "#ffd75f", "94": "#6ca8ff", "95": "#e47cff", "96": "#4fd6e6",
    "97": "#ffffff",
}
_COLOR_FONDO: Dict[str, str] = {
    "41": "#e05555", "42": "#4cbf5a", "43": "#e6c34a", "44": "#4f86e0",
    "45": "#c45fe0", "46": "#3cc3d4", "47": "#e6e6e6", "100": "#6b6b6b",
}


def ansi_a_html(texto: str) -> str:
    """Convierte texto con codigos de color ANSI en HTML con estilos."""
    partes: List[str] = []
    estado: Dict[str, str] = {}
    abierto = False
    posicion = 0
    for coincidencia in _PATRON_SGR.finditer(texto):
        partes.append(html.escape(texto[posicion:coincidencia.start()]))
        posicion = coincidencia.end()
        if abierto:
            partes.append("</span>")
            abierto = False
        for codigo in (coincidencia.group(1) or "0").split(";"):
            if codigo in ("", "0"):
                estado.clear()
            elif codigo == "1":
                estado["font-weight"] = "bold"
            elif codigo == "2":
                estado["opacity"] = "0.7"
            elif codigo in _COLOR_TEXTO:
                estado["color"] = _COLOR_TEXTO[codigo]
            elif codigo in _COLOR_FONDO:
                estado["background"] = _COLOR_FONDO[codigo]
        if estado:
            estilo = ";".join(f"{clave}:{valor}" for clave, valor in estado.items())
            partes.append(f'<span style="{estilo}">')
            abierto = True
    partes.append(html.escape(texto[posicion:]))
    if abierto:
        partes.append("</span>")
    return "".join(partes)


def guardar_simulacion(
    pantallas: Sequence[str], carpeta: Path, nombre_lote: str
) -> Tuple[Path, Path]:
    """Guarda todas las pantallas en ``.txt`` y ``.html``; retorna sus rutas."""
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = carpeta / f"simulacion_{Path(nombre_lote).stem}_{marca}"
    contenido = "\n".join(pantallas)

    ruta_txt = base.with_suffix(".txt")
    ruta_txt.write_text(quitar_colores(contenido), encoding="utf-8")

    titulo = html.escape(f"KernelFlow - {nombre_lote}")
    documento = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{titulo}</title>
<style>
  body {{ background:#141414; color:#d4d4d4; margin:0; padding:24px; }}
  h1 {{ font-family:system-ui,sans-serif; font-size:18px; color:#4fd6e6; }}
  pre {{ font-family:Consolas,"DejaVu Sans Mono",monospace; font-size:13px;
        line-height:1.25; white-space:pre; }}
</style>
</head>
<body>
<h1>{titulo}</h1>
<pre>{ansi_a_html(contenido)}</pre>
</body>
</html>
"""
    ruta_html = base.with_suffix(".html")
    ruta_html.write_text(documento, encoding="utf-8")
    return ruta_txt, ruta_html


# ============================================================================
# 3. LINEA DE TIEMPO DE LA CPU
# Registro de que proceso uso la CPU en cada ut, para el diagrama de Gantt.
# ============================================================================

class PlanificadorConGantt(PlanificadorSRTF):
    """El mismo SRTF de ``core.py`` que ademas anota el uso de la CPU.

    ``linea_tiempo[t]`` es el ID del proceso que uso la CPU en [t, t+1), o
    ``None`` si estuvo ociosa. Solo se usa para dibujar el Gantt; no cambia
    ninguna decision del planificador.
    """

    def __init__(self, *argumentos, **opciones) -> None:
        super().__init__(*argumentos, **opciones)
        self.linea_tiempo: List[Optional[str]] = []

    def ejecutar_unidad(self) -> None:
        en_cpu = self.proceso_en_ejecucion
        self.linea_tiempo.append(None if en_cpu is None else en_cpu.id)
        super().ejecutar_unidad()


# ============================================================================
# 4. PANEL DE LA TERMINAL: TABLAS, MAPA DE MEMORIA Y GANTT
# Solo consulta procesos, admision, memoria y la linea de tiempo; no decide
#   transiciones ni selecciona la CPU.
# ============================================================================

COLOR_ESTADO = {
    ESTADO_NUEVO: ("gris",),
    ESTADO_LISTO: ("cian",),
    ESTADO_LISTO_SUSPENDIDO: ("amarillo",),
    ESTADO_EJECUCION: ("verde", "negrita"),
    ESTADO_TERMINADO: ("azul",),
}
NOMBRE_ESTADO = {ESTADO_LISTO_SUSPENDIDO: "LISTO/SUSP."}

# (etiqueta, colores) de cada tipo de evento.
ETIQUETA_EVENTO = {
    TIPO_ARRIBO: ("LLEGADA", ("cian",)),
    TIPO_NUEVA_ADMISION: ("ADMISION", ("verde",)),
    TIPO_SIGUE_SUSPENDIDO: ("SIN MEMORIA", ("amarillo",)),
    TIPO_APROPIACION: ("APROPIACION", ("magenta", "negrita")),
    TIPO_INICIO: ("CPU", ("verde", "negrita")),
    TIPO_FINALIZACION: ("FIN", ("azul", "negrita")),
    TIPO_MEMORIA_LIBERADA: ("MEMORIA", ("azul",)),
    TIPO_CPU_OCIOSA: ("CPU OCIOSA", ("gris",)),
}
ETIQUETA_SUSPENSION = ("SUSPENSION", ("amarillo", "negrita"))
ANCHO_ETIQUETA = max(len(e) for e, _ in ETIQUETA_EVENTO.values()) + 2
CELDAS_PROGRESO = 8


def ancho_terminal() -> int:
    return shutil.get_terminal_size(fallback=(120, 30)).columns


def centrar_linea(texto: str) -> str:
    return " " * max(0, (ancho_terminal() - largo_visible(texto)) // 2) + texto


def imprimir_centrado(texto: str) -> None:
    print(centrar_linea(texto))


def imprimir_bloque(lineas: Sequence[str]) -> None:
    """Centra un bloque respetando la alineacion interna de sus lineas."""
    if not lineas:
        return
    ancho_bloque = max(largo_visible(linea) for linea in lineas)
    margen = " " * max(0, (ancho_terminal() - ancho_bloque) // 2)
    for linea in lineas:
        print(margen + linea if linea else "")


class PanelConsola(PresentacionConsola):
    """Vista de la simulacion para la terminal, con tablas y graficos."""

    def __init__(
        self,
        procesos: Sequence[Proceso],
        admision: AdministradorAdmision,
        memoria: GestorMemoria,
        estilo: Optional[Estilo] = None,
    ) -> None:
        super().__init__(procesos, admision, memoria)
        self.estilo = estilo if estilo is not None else Estilo.detectar()
        # El planificador comparte su lista; se completa a medida que avanza.
        self.linea_tiempo: List[Optional[str]] = []
        self._color_proceso: Dict[str, str] = {
            proceso.id: PALETA_PROCESOS[indice % len(PALETA_PROCESOS)]
            for indice, proceso in enumerate(procesos)
        }
        self._estados_previos: Dict[str, str] = {
            proceso.id: proceso.estado for proceso in procesos
        }
        ids = sorted((re.escape(p.id) for p in procesos), key=len, reverse=True)
        self._patron_ids = (
            re.compile(r"(?<![\w])(" + "|".join(ids) + r")(?![\w])") if ids else None
        )

    # ------------------------------------------------------------------
    # Pantallas
    # ------------------------------------------------------------------

    def mostrar_inicio(self, ruta_csv: Path) -> None:
        e = self.estilo
        self._encabezado("PROCESOS CARGADOS", f"Archivo: {ruta_csv.name}")
        imprimir_centrado(
            f"{len(self.procesos)} proceso(s) leido(s) correctamente. Todos "
            "comienzan en " + e.c("NUEVO", "gris") + " y esperan su arribo."
        )
        print()
        imprimir_bloque(self._tabla_procesos(tiempo=None, cambiados=set(),
                                             titulo="Procesos del lote"))
        print()
        imprimir_bloque(self._mapa_memoria())
        print()
        imprimir_bloque((
            e.c("Memoria:", "negrita") + " 100K para el SO + 450K para usuario"
            " (particiones variables MVT, Best-Fit)",
            e.c("CPU:", "negrita") + " SRTF apropiativo   "
            + e.c("Multiprogramacion maxima:", "negrita") + " 5",
        ))

    def mostrar_paso(
        self, eventos: Sequence[EventoPlanificador], tiempo: int, numero: int
    ) -> None:
        e = self.estilo
        cambiados = {
            proceso.id for proceso in self.procesos
            if proceso.estado != self._estados_previos.get(proceso.id)
        }
        print()
        self._encabezado(f"PASO {numero}", f"Reloj: t = {tiempo} ut")
        imprimir_centrado(e.c("EVENTOS DE ESTE PASO", "negrita"))
        imprimir_bloque(self._lineas_eventos(eventos) + [""] + self._decision_srtf())
        print()
        imprimir_bloque(self._mapa_memoria())
        print()
        imprimir_bloque(acomodar_en_filas(
            [self._tabla_procesos(tiempo, cambiados), self._tabla_particiones()],
            ancho_terminal() - 2,
        ))
        print()
        imprimir_bloque(acomodar_en_filas(
            [
                self._tabla_cpu(tiempo),
                self._tabla_listos(tiempo),
                self._tabla_suspendidos(tiempo),
            ],
            ancho_terminal() - 2,
        ))
        print()
        imprimir_bloque(self._linea_cpu(tiempo))
        print()
        imprimir_centrado(self._barra_estado(tiempo))
        print(e.c(f" FIN DEL PASO {numero} ".center(ancho_terminal(), "─"
                                                     if e.unicode else "-"),
                  "gris"))
        self._estados_previos = {p.id: p.estado for p in self.procesos}

    def mostrar_fin(self, tiempo: int) -> None:
        e = self.estilo
        print()
        self._encabezado(
            "SIMULACION FINALIZADA",
            f"t = {tiempo} ut   Memoria de usuario libre: "
            f"{self.memoria.memoria_libre_total()}K",
        )
        informe = calcular_estadisticas(self.procesos, tiempo)
        filas = [
            (
                self._id(fila.id),
                fila.tiempo_arribo,
                fila.tiempo_irrupcion,
                fila.tiempo_inicio,
                fila.tiempo_finalizacion,
                Celda(fila.tiempo_retorno, ("verde",)),
                Celda(fila.tiempo_espera, ("amarillo",)),
                Celda(fila.tiempo_respuesta, ("cian",)),
            )
            for fila in informe.procesos
        ]
        filas.append((
            Celda("PROMEDIO", ("negrita",)), "", "", "", "",
            Celda(f"{informe.retorno_promedio:.2f}", ("verde", "negrita"), ">"),
            Celda(f"{informe.espera_promedio:.2f}", ("amarillo", "negrita"), ">"),
            Celda(f"{informe.respuesta_promedio:.2f}", ("cian", "negrita"), ">"),
        ))
        imprimir_bloque(e.tabla(
            ("ID", "T.Arribo", "T.Irrup.", "T.Inicio", "T.Final.",
             "T.Retorno", "T.Espera", "T.Resp."),
            filas,
            titulo="Informe estadistico por proceso",
        ))
        print()
        imprimir_bloque(e.tabla(
            ("Metrica", "Valor", "Formula"),
            [
                ("Tiempo de retorno promedio",
                 Celda(f"{informe.retorno_promedio:.2f} ut", ("verde", "negrita")),
                 "T. Finalizacion - T. Arribo"),
                ("Tiempo de espera promedio",
                 Celda(f"{informe.espera_promedio:.2f} ut", ("amarillo", "negrita")),
                 "T. Retorno - T. Irrupcion"),
                ("Tiempo de respuesta promedio",
                 Celda(f"{informe.respuesta_promedio:.2f} ut", ("cian", "negrita")),
                 "Primer uso de CPU - T. Arribo"),
                ("Rendimiento del sistema",
                 Celda(f"{informe.rendimiento:.4f} trab./ut", ("magenta", "negrita")),
                 f"{informe.trabajos_terminados} trabajos / "
                 f"{informe.tiempo_total} ut"),
            ],
            titulo="Resumen",
        ))
        print()
        imprimir_bloque(self._grafico_barras(informe))
        print()
        imprimir_bloque(self._gantt(tiempo))

    # ------------------------------------------------------------------
    # Bloques de cada paso
    # ------------------------------------------------------------------

    def _encabezado(self, titulo: str, subtitulo: str = "") -> None:
        e = self.estilo
        ancho = ancho_terminal()
        print(e.c(e.linea(ancho, doble=True), "cian"))
        imprimir_centrado(e.c(titulo, "negrita", "blanco"))
        if subtitulo:
            imprimir_centrado(e.c(subtitulo, "cian"))
        print(e.c(e.linea(ancho, doble=True), "cian"))

    def _lineas_eventos(self, eventos: Sequence[EventoPlanificador]) -> List[str]:
        e = self.estilo
        ancho = max(40, min(ancho_terminal() - 6, 118))
        lineas: List[str] = []
        for evento in eventos:
            etiqueta, colores = ETIQUETA_EVENTO.get(evento.tipo, ("EVENTO", ()))
            if "a LISTO_SUSPENDIDO" in evento.detalle and evento.tipo in (
                TIPO_ARRIBO, TIPO_NUEVA_ADMISION
            ):
                etiqueta, colores = ETIQUETA_SUSPENSION
            ancho_prefijo = 6 + ANCHO_ETIQUETA + 1
            envueltas = textwrap.wrap(evento.detalle, width=ancho - ancho_prefijo) or [""]
            for indice, texto in enumerate(envueltas):
                texto = self._resaltar_ids(texto)
                if indice == 0:
                    lineas.append(
                        e.c(f"t={evento.tiempo:<3} ", "gris")
                        + e.c(f"[{etiqueta}]".ljust(ANCHO_ETIQUETA), *colores)
                        + " " + texto
                    )
                else:
                    lineas.append(" " * ancho_prefijo + texto)
        return lineas

    def _decision_srtf(self) -> List[str]:
        """Explica por que el proceso en CPU es el elegido por SRTF."""
        e = self.estilo
        etiqueta = e.c("[SRTF]".ljust(ANCHO_ETIQUETA), "magenta", "negrita")
        prefijo = " " * 6 + etiqueta + " "
        en_cpu = self.proceso_en_cpu()
        candidatos = list(self.admision.obtener_listos())
        if en_cpu is not None:
            candidatos.append(en_cpu)
        if not candidatos:
            return [prefijo + "No hay procesos en LISTO: la CPU queda "
                    + e.c("OCIOSA", "gris") + "."]

        def clave(proceso: Proceso):
            # El proceso en CPU va primero entre los empatados (conserva la CPU).
            return (proceso.tiempo_restante, proceso is not en_cpu,
                    proceso.tiempo_arribo, proceso.id)

        ordenados = sorted(candidatos, key=clave)
        partes = []
        for indice, proceso in enumerate(ordenados):
            if indice > 0:
                igual = proceso.tiempo_restante == ordenados[indice - 1].tiempo_restante
                partes.append(" = " if igual else " < ")
            texto = f"{proceso.id}({proceso.tiempo_restante})"
            partes.append(e.c(texto, "verde", "negrita") if proceso is en_cpu
                          else self._resaltar_ids(texto))
        explicacion = "Menor tiempo restante: " + "".join(partes)
        empatados = []
        if en_cpu is not None:
            explicacion += e.c(" → ", "gris") + "usa la CPU " + e.c(en_cpu.id, "verde", "negrita")
            empatados = [p for p in ordenados
                         if p is not en_cpu and p.tiempo_restante == en_cpu.tiempo_restante]
        lineas = [prefijo + explicacion]
        if en_cpu is not None and empatados:
            lineas.append(" " * (6 + ANCHO_ETIQUETA + 1) + e.c(
                "Empate de tiempo restante: el proceso que ya esta en CPU la conserva.",
                "gris"))
        return lineas

    def _mapa_memoria(self) -> List[str]:
        """Barra proporcional de la memoria: SO, particiones y huecos libres."""
        e = self.estilo
        resumen = self.memoria.obtener_resumen_memoria()
        particiones = [resumen["particion_so"], *resumen["particiones_usuario"]]
        total = self.memoria.memoria_total_kb
        ancho = max(40, min(ancho_terminal() - 12, 110)) - len(particiones) - 1
        anchos = _repartir(
            [particion.tamanio for particion in particiones], total, ancho, minimo=3
        )
        separador = e.c("│", "gris")
        segmentos = []
        for particion, columnas in zip(particiones, anchos):
            if particion.libre:
                etiqueta = _etiqueta_que_entra(
                    (f"libre {particion.tamanio}K", "libre", ""), columnas)
                sobra = columnas - len(etiqueta)
                izquierda = sobra // 2
                texto = "░" * izquierda + etiqueta + "░" * (sobra - izquierda)
                segmentos.append(e.c(texto, "verde"))
            elif particion.proceso_id == "SO":
                etiqueta = _etiqueta_que_entra((f"SO {particion.tamanio}K", "SO"), columnas)
                segmentos.append(e.c(rellenar(etiqueta, columnas, "^"),
                                     "negro", "fondo_magenta"))
            else:
                pid = particion.proceso_id
                etiqueta = _etiqueta_que_entra(
                    (f"{pid} {particion.tamanio}K", pid, pid[:columnas]), columnas)
                color = self._color_proceso.get(pid, "blanco")
                segmentos.append(e.c(rellenar(etiqueta, columnas, "^"),
                                     "negro", f"fondo_{color}"))
        barra = separador + separador.join(segmentos) + separador

        # Escala de direcciones: el inicio de cada particion y el final.
        escala = [" "] * (sum(anchos) + len(anchos) + 1)
        columna = 0
        ocupado_hasta = -1
        for particion, columnas in zip(particiones, anchos):
            texto = str(particion.direccion_inicio)
            if columna > ocupado_hasta:
                escala[columna:columna + len(texto)] = texto
                ocupado_hasta = columna + len(texto)
            columna += columnas + 1
        final = str(total)
        inicio_final = len(escala) - len(final)
        if inicio_final > ocupado_hasta:
            escala[inicio_final:] = final

        huecos = self.memoria.obtener_huecos()
        lineas = [
            e.c("Mapa de memoria", "negrita", "cian")
            + e.c(f"  (aprox. a escala, {total}K; direcciones en K)", "gris"),
            barra,
            e.c("".join(escala)[:len(escala)], "gris"),
        ]
        if len(huecos) > 1:
            lineas.append(e.c(
                f"Fragmentacion externa: {self.memoria.memoria_libre_total()}K "
                f"libres repartidos en {len(huecos)} huecos (el mayor: "
                f"{self.memoria.mayor_hueco_libre()}K)", "amarillo"))
        return lineas

    def _tabla_procesos(
        self, tiempo: Optional[int], cambiados=frozenset(), titulo: str = "Procesos"
    ) -> List[str]:
        e = self.estilo
        filas = []
        hay_sin_cupo = False
        for proceso in self.procesos:
            estado = NOMBRE_ESTADO.get(proceso.estado, proceso.estado)
            if (
                tiempo is not None
                and proceso.estado == ESTADO_NUEVO
                and proceso.tiempo_arribo <= tiempo
            ):
                estado += "*"
                hay_sin_cupo = True
            cambio = proceso.id in cambiados
            estilos_estado = COLOR_ESTADO.get(proceso.estado, ())
            if cambio:
                estilos_estado = estilos_estado + ("negrita",)
            filas.append((
                Celda("►" if cambio else " ", ("magenta", "negrita")),
                self._id(proceso.id),
                proceso.tamanio,
                proceso.tiempo_arribo,
                proceso.tiempo_irrupcion,
                Celda(self._progreso(proceso), ()),
                Celda(proceso.tiempo_restante,
                      ("negrita",) if proceso.estado == ESTADO_EJECUCION else (), ">"),
                Celda(estado, estilos_estado),
            ))
        lineas = e.tabla(
            (" ", "ID", "KB", "Arribo", "T.Irrup.", "Progreso (ejecutado)",
             "T.Rest.", "Estado"),
            filas,
            titulo=titulo,
        )
        if cambiados:
            lineas.append(e.c("► cambio de estado en este paso", "magenta"))
        if hay_sin_cupo:
            lineas.append(e.c("* llego y espera cupo de multiprogramacion", "gris"))
        return lineas

    def _progreso(self, proceso: Proceso) -> str:
        """Barra de progreso de CPU, por ejemplo ``████░░░░ 4/8``."""
        e = self.estilo
        ejecutado = proceso.tiempo_irrupcion - proceso.tiempo_restante
        llenas = round(CELDAS_PROGRESO * ejecutado / proceso.tiempo_irrupcion)
        if ejecutado and not llenas:
            llenas = 1
        color = "azul" if proceso.estado == ESTADO_TERMINADO else (
            "verde" if proceso.estado == ESTADO_EJECUCION else "cian")
        barra = e.c("█" * llenas, color) + e.c("░" * (CELDAS_PROGRESO - llenas), "gris")
        ancho = len(str(proceso.tiempo_irrupcion))
        return f"{barra} {ejecutado:>{ancho}}/{proceso.tiempo_irrupcion}"

    def _tabla_particiones(self) -> List[str]:
        resumen = self.memoria.obtener_resumen_memoria()
        filas = []
        for particion in [resumen["particion_so"], *resumen["particiones_usuario"]]:
            if particion.libre:
                proceso, estado, frag = Celda("-", ("gris",)), Celda("Libre", ("verde",)), "-"
            elif particion.proceso_id == "SO":
                proceso, estado, frag = (
                    Celda("SO", ("magenta",)), Celda("Sistema", ("magenta",)), "-"
                )
            else:
                proceso = self._id(particion.proceso_id)
                estado, frag = Celda("Ocupada", ("rojo",)), "0"
            filas.append((
                Celda("-", ("gris",), ">") if particion.numero is None
                else particion.numero,
                particion.direccion_inicio,
                particion.tamanio,
                proceso,
                frag,
                estado,
            ))
        lineas = self.estilo.tabla(
            ("Part.", "Inicio", "Tamanio", "Proceso", "Frag.Int.", "Estado"),
            filas,
            titulo="Memoria principal (KB)",
        )
        huecos = self.memoria.obtener_huecos()
        lineas.append(self.estilo.c(
            f"Libre: {self.memoria.memoria_libre_total()}K en {len(huecos)} "
            f"hueco(s); mayor hueco: {self.memoria.mayor_hueco_libre()}K",
            "gris",
        ))
        return lineas

    def _tabla_cpu(self, tiempo: int) -> List[str]:
        en_cpu = self.proceso_en_cpu()
        filas = [] if en_cpu is None else [(
            self._id(en_cpu.id),
            en_cpu.tamanio,
            self._numero_particion(en_cpu),
            en_cpu.tiempo_irrupcion - en_cpu.tiempo_restante,
            Celda(en_cpu.tiempo_restante, ("verde", "negrita")),
        )]
        return self.estilo.tabla(
            ("ID", "KB", "Part.", "T.Ejec.", "T.Rest."),
            filas,
            titulo="CPU - EJECUCION",
            color_titulo=("negrita", "verde"),
            vacia="CPU OCIOSA",
        )

    def _tabla_listos(self, tiempo: int) -> List[str]:
        filas = [
            (
                orden,
                self._id(proceso.id),
                proceso.tamanio,
                self._numero_particion(proceso),
                proceso.tiempo_arribo,
                Celda(proceso.tiempo_restante, ("cian",)),
                self._espera_acumulada(proceso, tiempo),
            )
            for orden, proceso in enumerate(self._ordenar_srtf(
                self.admision.obtener_listos()), start=1)
        ]
        return self.estilo.tabla(
            ("Orden", "ID", "KB", "Part.", "Arribo", "T.Rest.", "Espera"),
            filas,
            titulo="Cola LISTO (en memoria)",
            color_titulo=("negrita", "cian"),
            vacia="sin procesos",
        )

    def _tabla_suspendidos(self, tiempo: int) -> List[str]:
        filas = [
            (
                orden,
                self._id(proceso.id),
                proceso.tamanio,
                proceso.tiempo_arribo,
                Celda(proceso.tiempo_restante, ("amarillo",)),
                self._espera_acumulada(proceso, tiempo),
            )
            for orden, proceso in enumerate(
                self.admision.obtener_listos_suspendidos(), start=1)
        ]
        return self.estilo.tabla(
            ("Orden", "ID", "KB", "Arribo", "T.Rest.", "Espera"),
            filas,
            titulo="Cola LISTO_SUSPENDIDO (sin memoria)",
            color_titulo=("negrita", "amarillo"),
            vacia="sin procesos",
        )

    def _linea_cpu(self, tiempo: int) -> List[str]:
        """Gantt compacto de la CPU desde t = 0 hasta el instante actual."""
        e = self.estilo
        if not self.linea_tiempo:
            return []
        unidades, columnas = _escala_gantt(len(self.linea_tiempo), ancho_terminal() - 20)
        barra, escala = self._barra_gantt(self.linea_tiempo, unidades, columnas)
        return [
            e.c("Uso de la CPU hasta ahora", "negrita", "cian")
            + e.c("  (· = CPU ociosa)", "gris"),
            barra,
            e.c(escala, "gris"),
        ]

    def _barra_estado(self, tiempo: int) -> str:
        e = self.estilo
        en_cpu = self.proceso_en_cpu()
        terminados = sum(p.estado == ESTADO_TERMINADO for p in self.procesos)
        sep = e.c(" | ", "gris")
        partes = [
            e.c("t = ", "gris") + e.c(f"{tiempo} ut", "negrita"),
            e.c("CPU: ", "gris") + (
                e.c(en_cpu.id, "verde", "negrita") if en_cpu else e.c("OCIOSA", "gris")
            ),
            e.c("Multiprogramacion: ", "gris") + e.c(
                f"{self.admision.grado_multiprogramacion()}/"
                f"{GRADO_MAXIMO_MULTIPROGRAMACION}", "negrita"),
            e.c("Memoria libre: ", "gris") + e.c(
                f"{self.memoria.memoria_libre_total()}K/"
                f"{self.memoria.memoria_usuario_kb}K", "negrita"),
            e.c("Terminados: ", "gris") + e.c(
                f"{terminados}/{len(self.procesos)}", "negrita"),
        ]
        return sep.join(partes)

    # ------------------------------------------------------------------
    # Graficos del informe final
    # ------------------------------------------------------------------

    def _grafico_barras(self, informe) -> List[str]:
        """Barras horizontales de retorno y espera por proceso."""
        e = self.estilo
        if not informe.procesos:
            return []
        maximo = max(fila.tiempo_retorno for fila in informe.procesos) or 1
        largo = 40
        ancho_id = max(len(fila.id) for fila in informe.procesos)
        lineas = [e.c("Retorno y espera por proceso", "negrita", "cian")
                  + e.c("  (" + e.c("█", "verde") + e.c(" retorno  ", "gris")
                        + e.c("█", "amarillo") + e.c(" espera)", "gris"), "gris")]
        for fila in informe.procesos:
            for nombre, valor, color in (
                ("retorno", fila.tiempo_retorno, "verde"),
                ("espera", fila.tiempo_espera, "amarillo"),
            ):
                celdas = round(largo * valor / maximo)
                if valor and not celdas:
                    celdas = 1
                etiqueta = fila.id if nombre == "retorno" else ""
                lineas.append(
                    self._resaltar_ids(etiqueta.ljust(ancho_id)) + " "
                    + e.c(nombre.ljust(7), "gris") + " "
                    + e.c("█" * celdas, color) + " " + str(valor)
                )
        return lineas

    def _gantt(self, tiempo: int) -> List[str]:
        """Diagrama de Gantt: una fila por proceso y la fila de la CPU."""
        e = self.estilo
        linea = self.linea_tiempo[:tiempo]
        if not linea:
            return []
        ancho_id = max(4, max(len(p.id) for p in self.procesos))
        unidades, ancho_columna = _escala_gantt(len(linea), ancho_terminal() - ancho_id - 12)
        columnas = math.ceil(len(linea) / unidades)
        detalle_escala = (f"cada {ancho_columna} columnas = 1 ut" if unidades == 1
                          else f"cada columna = {unidades} ut")

        lineas = [
            e.c("Diagrama de Gantt", "negrita", "cian")
            + e.c(f"  ({detalle_escala};  █ usa la CPU  ░ espera en el sistema)", "gris"),
        ]
        for proceso in self.procesos:
            fin = proceso.tiempo_finalizacion if proceso.tiempo_finalizacion is not None else tiempo
            celdas = []
            for columna in range(columnas):
                desde = columna * unidades
                tramo = linea[desde:desde + unidades]
                if proceso.id in tramo:
                    celdas.append(e.c("█" * ancho_columna,
                                      self._color_proceso.get(proceso.id, "blanco")))
                elif proceso.tiempo_arribo <= desde < fin:
                    celdas.append(e.c("░" * ancho_columna, "gris"))
                else:
                    celdas.append(" " * ancho_columna)
            lineas.append(self._resaltar_ids(proceso.id.ljust(ancho_id)) + " "
                          + e.c("│", "gris") + "".join(celdas) + e.c("│", "gris"))
        barra, escala = self._barra_gantt(linea, unidades, ancho_columna)
        lineas.append(e.c("CPU".ljust(ancho_id), "negrita") + " " + barra)
        lineas.append(" " * (ancho_id + 1) + e.c(escala, "gris"))
        return lineas

    def _barra_gantt(
        self, linea: Sequence[Optional[str]], unidades: int, ancho_columna: int
    ):
        """Barra de CPU con un tramo coloreado por cada rafaga y su escala.

        Cada columna logica abarca ``unidades`` ut y ocupa ``ancho_columna``
        caracteres.
        """
        e = self.estilo
        columnas = [linea[i] for i in range(0, len(linea), unidades)]
        tramos = []
        for pid in columnas:
            if tramos and tramos[-1][0] == pid:
                tramos[-1][1] += 1
            else:
                tramos.append([pid, 1])
        partes = []
        for pid, cantidad in tramos:
            largo = cantidad * ancho_columna
            if pid is None:
                partes.append(e.c("·" * largo, "gris"))
            else:
                etiqueta = pid if len(pid) <= largo else pid[:largo]
                color = self._color_proceso.get(pid, "blanco")
                partes.append(e.c(rellenar(etiqueta, largo, "^"),
                                  "negro", f"fondo_{color}"))
        barra = e.c("│", "gris") + "".join(partes) + e.c("│", "gris")

        escala = [" "] * (len(columnas) * ancho_columna + 6)
        paso = 5 if ancho_columna > 1 or len(columnas) <= 60 else 10
        for columna in range(0, len(columnas) + 1, paso):
            texto = str(columna * unidades)
            posicion = columna * ancho_columna
            if posicion + len(texto) <= len(escala):
                escala[posicion:posicion + len(texto)] = texto
        return barra, " " + "".join(escala).rstrip()

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

    def _id(self, proceso_id: str) -> Celda:
        return Celda(proceso_id, ("amarillo",))

    def _resaltar_ids(self, texto: str) -> str:
        if not self.estilo.color or self._patron_ids is None:
            return texto
        return self._patron_ids.sub(
            lambda m: self.estilo.c(m.group(1), "amarillo"), texto
        )

    def _numero_particion(self, proceso: Proceso) -> object:
        particion = self.memoria.obtener_asignacion(proceso)
        if particion is None or particion.numero is None:
            return "-"
        return particion.numero

    @staticmethod
    def _espera_acumulada(proceso: Proceso, tiempo: int) -> int:
        """Tiempo en el sistema sin usar la CPU hasta el instante actual."""
        ejecutado = proceso.tiempo_irrupcion - proceso.tiempo_restante
        return max(0, tiempo - proceso.tiempo_arribo - ejecutado)

    @staticmethod
    def _ordenar_srtf(procesos: Sequence[Proceso]) -> List[Proceso]:
        """Orden en que SRTF los elegiria: menor restante, arribo e ID."""
        return sorted(
            procesos,
            key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.id),
        )


def _escala_gantt(unidades_totales: int, ancho_disponible: int):
    """Elige cuantas ut entran por columna y cuantos caracteres ocupa cada una.

    Si hay lugar, cada ut ocupa hasta 3 caracteres para que entren los IDs;
    si no, se agrupan varias ut por columna.
    """
    ancho_disponible = max(20, ancho_disponible)
    if unidades_totales <= ancho_disponible:
        return 1, max(1, min(3, ancho_disponible // max(1, unidades_totales)))
    return math.ceil(unidades_totales / ancho_disponible), 1


def _etiqueta_que_entra(opciones: Sequence[str], columnas: int) -> str:
    """Devuelve la primera etiqueta que entra en ``columnas`` con margen."""
    for opcion in opciones:
        if len(opcion) + 2 <= columnas or (len(opcion) <= columnas and opcion):
            return opcion
    return ""


def _repartir(tamanios: Sequence[int], total: int, ancho: int, minimo: int) -> List[int]:
    """Reparte ``ancho`` columnas en proporcion a los tamanios (con minimo)."""
    exactos = [tamanio * ancho / total for tamanio in tamanios]
    anchos = [max(minimo, int(valor)) for valor in exactos]
    diferencia = ancho - sum(anchos)
    if diferencia > 0:
        orden = sorted(range(len(anchos)),
                       key=lambda i: exactos[i] - int(exactos[i]), reverse=True)
    else:
        orden = sorted(range(len(anchos)), key=lambda i: anchos[i], reverse=True)
    intentos = 0
    while diferencia != 0 and orden and intentos < 10 * ancho:
        indice = orden[intentos % len(orden)]
        if diferencia > 0:
            anchos[indice] += 1
            diferencia -= 1
        elif anchos[indice] > minimo:
            anchos[indice] -= 1
            diferencia += 1
        intentos += 1
    return anchos


# ============================================================================
# 5. MENU, NAVEGACION Y EJECUCION
# Menu con colores, navegacion entre pasos (B/F/Q) y guardado (G).
# ============================================================================

DIRECTORIO_RESULTADOS = DIRECTORIO_PROYECTO / "resultados"

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
            # La lista de archivos de data/ es la misma de core.py.
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
        procesos = cargar_procesos(ruta_csv)
    except ErrorCargaProcesos as error:
        imprimir_centrado(f"Error: {error}")
        return 1

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
