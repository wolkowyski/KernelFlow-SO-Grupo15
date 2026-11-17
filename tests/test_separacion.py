"""Pruebas de la separacion entre la version base y la interfaz."""

import ast
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import core
import interfaz
from admision import Admision
from ayudas import simular
from carga import cargar_procesos
from memoria import GestorMemoria
from planificador import PlanificadorSRTF

RAIZ = Path(__file__).resolve().parent.parent
LOTES = sorted((RAIZ / "data").glob("*.csv"))
ARCHIVOS_BASE = (
    "core.py",
    "proceso.py",
    "estados.py",
    "carga.py",
    "memoria.py",
    "admision.py",
    "planificador.py",
    "estadisticas.py",
    "presentacion.py",
)


def _modulos_importados(ruta: Path) -> set:
    modulos = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulos.add(nodo.module)
    return modulos


def _resultado(clase_planificador, ruta):
    """Simula un lote y retorna (tiempos por proceso, eventos, reloj final)."""
    procesos = cargar_procesos(ruta)
    memoria = GestorMemoria()
    admision = Admision(procesos, memoria)
    eventos = []
    planificador = clase_planificador(admision, memoria, eventos.append)
    simular(planificador)
    tiempos = [
        (p.id, p.tiempo_inicio, p.tiempo_finalizacion, p.estado) for p in procesos
    ]
    return tiempos, eventos, planificador.reloj


class TestSeparacion(unittest.TestCase):
    def test_la_version_base_no_depende_de_la_interfaz(self):
        for nombre in ARCHIVOS_BASE:
            with self.subTest(archivo=nombre):
                self.assertNotIn("interfaz", _modulos_importados(RAIZ / nombre))

    def test_core_muestra_texto_sin_colores(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = core.ejecutar_simulacion(RAIZ / "data" / "procesos_demo.csv")
        self.assertEqual(codigo, 0)
        self.assertNotIn("\x1b[", salida.getvalue())
        self.assertIn("INFORME ESTADISTICO FINAL", salida.getvalue())

    def test_la_interfaz_usa_los_mismos_modulos(self):
        self.assertIs(interfaz.Admision, Admision)
        self.assertIs(interfaz.GestorMemoria, GestorMemoria)
        self.assertTrue(issubclass(interfaz.PlanificadorConGantt, PlanificadorSRTF))

    def test_planificador_con_gantt_no_cambia_la_simulacion(self):
        self.assertTrue(LOTES)
        for ruta in LOTES:
            with self.subTest(lote=ruta.name):
                self.assertEqual(
                    _resultado(PlanificadorSRTF, ruta),
                    _resultado(interfaz.PlanificadorConGantt, ruta),
                )


if __name__ == "__main__":
    unittest.main()
