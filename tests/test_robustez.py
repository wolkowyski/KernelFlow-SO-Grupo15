"""Pruebas de robustez del nucleo del simulador.

1. Un simulador de referencia ("oraculo"), escrito aparte y sin reutilizar
   codigo de ``core/``, aplica las mismas reglas de la consigna. Se compara
   instante por instante con el simulador real en cientos de lotes al azar.
2. En cada instante se verifican invariantes que nunca deben romperse:
   memoria contigua y sin solapamientos, multiprogramacion <= 5, una sola
   CPU, SRTF, ningun proceso salteado ni adelantado, etc.

Reglas de referencia (documentadas en el README y el HOWTO):
- Memoria de usuario [100K, 550K), particiones variables, Best-Fit (hueco mas
  chico; ante empate, menor direccion). Al liberar se unen huecos contiguos.
- Multiprogramacion: EJECUCION + LISTO + LISTO_SUSPENDIDO <= 5.
- Arribos por tiempo y, ante empate, orden del CSV. Con cupo: si hay hueco
  pasa a LISTO; si no, a LISTO_SUSPENDIDO.
- Al terminar un proceso se libera su memoria y se reintentan primero los
  suspendidos (FIFO) y luego los NUEVO que esperan cupo.
- SRTF apropiativo: menor tiempo restante; si empata con el que esta en CPU,
  este la conserva; con la CPU libre: menor restante, arribo e ID.
"""

import random
import unittest
from pathlib import Path

from core.admision import GRADO_MAXIMO_MULTIPROGRAMACION, Admision
from core.carga import cargar_lote
from core.estadisticas import calcular_estadisticas
from core.memoria import GestorMemoria
from core.planificador import PlanificadorSRTF
from core.proceso import (
    ESTADO_EJECUCION,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_NUEVO,
    ESTADO_TERMINADO,
    Proceso,
)

INICIO_USUARIO = 100
FIN_USUARIO = 550
DATA = Path(__file__).resolve().parent.parent / "data"


def oraculo(lote):
    """Simulador de referencia. ``lote``: lista de (id, tamanio, arribo, irrupcion).

    Retorna (linea_de_tiempo, inicio, fin): que proceso uso la CPU en cada
    unidad y los instantes de inicio y fin de cada proceso.
    """
    tam = {p: t for p, t, _, _ in lote}
    arr = {p: a for p, _, a, _ in lote}
    rest = {p: i for p, _, _, i in lote}
    memoria = [[INICIO_USUARIO, FIN_USUARIO - INICIO_USUARIO, None]]

    def asignar(pid):
        candidatos = [(m[1], m[0], k) for k, m in enumerate(memoria)
                      if m[2] is None and m[1] >= tam[pid]]
        if not candidatos:
            return False
        _, _, k = min(candidatos)
        inicio, tamanio, _ = memoria[k]
        nuevo = [[inicio, tam[pid], pid]]
        if tamanio > tam[pid]:
            nuevo.append([inicio + tam[pid], tamanio - tam[pid], None])
        memoria[k:k + 1] = nuevo
        return True

    def liberar(pid):
        for m in memoria:
            if m[2] == pid:
                m[2] = None
        unida = []
        for m in memoria:
            if unida and unida[-1][2] is None and m[2] is None:
                unida[-1][1] += m[1]
            else:
                unida.append(list(m))
        memoria[:] = unida

    sin_arribar = [p for p, _, _, _ in sorted(
        lote, key=lambda x: (x[2], [q[0] for q in lote].index(x[0])))]
    nuevos, listos, suspendidos = [], [], []
    cpu = None
    inicio, fin, linea = {}, {}, []
    t = 0
    libero = False
    limite = max(arr.values()) + sum(rest.values()) + 5
    while len(fin) < len(lote):
        if libero:
            for pid in list(suspendidos):
                if asignar(pid):
                    suspendidos.remove(pid)
                    listos.append(pid)
            libero = False
        while sin_arribar and arr[sin_arribar[0]] <= t:
            nuevos.append(sin_arribar.pop(0))
        while nuevos and len(listos) + len(suspendidos) + (cpu is not None) < 5:
            pid = nuevos.pop(0)
            (listos if asignar(pid) else suspendidos).append(pid)
        if listos:
            mejor = min(listos, key=lambda p: (rest[p], arr[p], p))
            if cpu is None:
                cpu = mejor
                listos.remove(mejor)
            elif rest[mejor] < rest[cpu]:
                listos.remove(mejor)
                listos.append(cpu)
                cpu = mejor
        linea.append(cpu)
        if cpu is not None:
            inicio.setdefault(cpu, t)
            rest[cpu] -= 1
        t += 1
        if cpu is not None and rest[cpu] == 0:
            fin[cpu] = t
            liberar(cpu)
            cpu = None
            libero = True
        if t > limite:
            raise AssertionError("el oraculo no termina")
    return linea, inicio, fin


class ErrorInvariante(AssertionError):
    pass


def verificar_invariantes(procesos, admision, memoria, planificador):
    """Comprueba el estado completo del sistema en el instante actual."""
    t = planificador.reloj
    por_id = {p.id: p for p in procesos}

    def falla(mensaje):
        raise ErrorInvariante(f"t={t}: {mensaje}")

    # Memoria: contigua, sin solapamientos, huecos unidos, sin frag. interna.
    particiones = memoria.obtener_particiones()
    direccion = INICIO_USUARIO
    for indice, particion in enumerate(particiones):
        if particion.direccion_inicio != direccion:
            falla(f"memoria no contigua en {direccion}K: {particiones}")
        direccion = particion.direccion_fin
        if particion.libre:
            if indice and particiones[indice - 1].libre:
                falla("dos huecos libres contiguos sin unir")
        else:
            dueno = por_id.get(particion.proceso_id)
            if dueno is None:
                falla(f"particion de un proceso inexistente: {particion}")
            if dueno.estado not in (ESTADO_LISTO, ESTADO_EJECUCION):
                falla(f"{dueno.id} tiene memoria estando en {dueno.estado}")
            if particion.tamanio != dueno.tamanio:
                falla(f"particion de {dueno.id} con tamanio distinto al proceso")
    if direccion != FIN_USUARIO:
        falla(f"la memoria termina en {direccion}K y no en {FIN_USUARIO}K")

    en_cpu = [p for p in procesos if p.estado == ESTADO_EJECUCION]
    if len(en_cpu) > 1:
        falla(f"mas de un proceso en CPU: {[p.id for p in en_cpu]}")
    if planificador.proceso_en_ejecucion not in (en_cpu[0] if en_cpu else None,):
        falla("el planificador y los estados no coinciden en el proceso en CPU")

    ids_con_memoria = {p.proceso_id for p in memoria.obtener_particiones_ocupadas()}
    for proceso in procesos:
        tiene = proceso.id in ids_con_memoria
        if proceso.estado in (ESTADO_LISTO, ESTADO_EJECUCION) and not tiene:
            falla(f"{proceso.id} esta en {proceso.estado} sin memoria")
        if proceso.estado in (ESTADO_NUEVO, ESTADO_LISTO_SUSPENDIDO, ESTADO_TERMINADO) and tiene:
            falla(f"{proceso.id} tiene memoria estando en {proceso.estado}")
        if proceso.tiempo_arribo > t and proceso.estado != ESTADO_NUEVO:
            falla(f"{proceso.id} fue atendido antes de su arribo")
        if not 0 <= proceso.tiempo_restante <= proceso.tiempo_irrupcion:
            falla(f"tiempo restante invalido en {proceso.id}")
        if (proceso.estado == ESTADO_TERMINADO) != (proceso.tiempo_restante == 0):
            falla(f"{proceso.id}: TERMINADO no coincide con tiempo restante 0")

    grado = admision.grado_multiprogramacion()
    activos = sum(p.estado in (ESTADO_LISTO, ESTADO_LISTO_SUSPENDIDO, ESTADO_EJECUCION)
                  for p in procesos)
    if grado != activos or grado > GRADO_MAXIMO_MULTIPROGRAMACION:
        falla(f"multiprogramacion invalida: {grado} (activos {activos})")

    # Ningun proceso que ya llego queda olvidado en NUEVO si hay cupo.
    esperando_cupo = [p for p in procesos
                      if p.estado == ESTADO_NUEVO and p.tiempo_arribo <= t]
    if esperando_cupo and grado < GRADO_MAXIMO_MULTIPROGRAMACION:
        falla(f"{esperando_cupo[0].id} espera cupo pero hay cupo libre")

    # Un suspendido solo espera si realmente no entra en ningun hueco.
    for proceso in admision.obtener_listos_suspendidos():
        if proceso.tamanio <= memoria.mayor_hueco_libre():
            falla(f"{proceso.id} sigue suspendido pero entra en un hueco")

    # SRTF: si hay listos la CPU no esta ociosa y ejecuta el de menor restante.
    listos = admision.obtener_listos()
    if listos and not en_cpu:
        falla("hay procesos LISTO y la CPU esta ociosa")
    if listos and en_cpu:
        minimo = min(p.tiempo_restante for p in listos)
        if en_cpu[0].tiempo_restante > minimo:
            falla(f"SRTF: {en_cpu[0].id} usa la CPU con mas tiempo restante "
                  f"que otro proceso LISTO ({minimo})")


def simular_verificando(lote):
    """Corre el simulador real verificando invariantes en cada instante."""
    procesos = [Proceso(pid, tam, arr, irr) for pid, tam, arr, irr in lote]
    memoria = GestorMemoria()
    admision = Admision(procesos, memoria)
    planificador = PlanificadorSRTF(admision, memoria)
    limite = max(p.tiempo_arribo for p in procesos) + sum(
        p.tiempo_irrupcion for p in procesos) + 5
    linea = []
    while admision.hay_procesos_pendientes():
        planificador.procesar_instante()
        verificar_invariantes(procesos, admision, memoria, planificador)
        en_cpu = planificador.proceso_en_ejecucion
        linea.append(None if en_cpu is None else en_cpu.id)
        planificador.ejecutar_unidad()
        if planificador.reloj > limite:
            raise ErrorInvariante("la simulacion no termina (posible bucle)")
    verificar_invariantes(procesos, admision, memoria, planificador)
    if memoria.memoria_libre_total() != FIN_USUARIO - INICIO_USUARIO:
        raise ErrorInvariante("al terminar queda memoria sin liberar")
    return procesos, linea, planificador.reloj


def lote_al_azar(generador):
    cantidad = generador.randint(1, 10)
    lote = []
    for indice in range(1, cantidad + 1):
        tamanio = generador.choice([
            generador.randint(1, 60),
            generador.randint(60, 200),
            generador.randint(200, 450),
            450,
        ])
        lote.append((f"P{indice}", tamanio, generador.randint(0, 25),
                     generador.randint(1, 15)))
    generador.shuffle(lote)  # el orden del CSV no tiene por que seguir el arribo
    return lote


class TestContraOraculo(unittest.TestCase):
    def comparar(self, lote):
        procesos, linea, reloj = simular_verificando(lote)
        linea_ref, inicio_ref, fin_ref = oraculo(lote)
        self.assertEqual(linea, linea_ref, f"uso de CPU distinto en {lote}")
        for proceso in procesos:
            self.assertEqual(proceso.tiempo_inicio, inicio_ref[proceso.id], lote)
            self.assertEqual(proceso.tiempo_finalizacion, fin_ref[proceso.id], lote)
        # El informe usa las formulas de la consigna.
        informe = calcular_estadisticas(procesos, reloj)
        for fila in informe.procesos:
            arribo = next(x[2] for x in lote if x[0] == fila.id)
            irrup = next(x[3] for x in lote if x[0] == fila.id)
            self.assertEqual(fila.tiempo_retorno, fin_ref[fila.id] - arribo)
            self.assertEqual(fila.tiempo_espera, fin_ref[fila.id] - arribo - irrup)
        self.assertEqual(informe.trabajos_terminados, len(lote))
        self.assertEqual(sum(x is not None for x in linea), sum(x[3] for x in lote))

    def test_lotes_al_azar(self):
        generador = random.Random(2026)
        for _ in range(800):
            self.comparar(lote_al_azar(generador))

    def test_lotes_de_la_catedra_y_del_grupo(self):
        for ruta in sorted(DATA.glob("*.csv")):
            try:
                procesos = cargar_lote(ruta).procesos
            except ValueError:
                continue  # lotes con errores a proposito (se prueban aparte)
            with self.subTest(lote=ruta.name):
                self.comparar([(p.id, p.tamanio, p.tiempo_arribo, p.tiempo_irrupcion)
                               for p in procesos])

    def test_casos_limite(self):
        casos = [
            [("P1", 450, 0, 1)],                                   # memoria exacta
            [("P1", 1, 0, 1)],                                     # proceso minimo
            [(f"P{i}", 45, 0, 1) for i in range(1, 11)],           # 10 juntos
            [(f"P{i}", 450, 0, 2) for i in range(1, 11)],          # 10 que no entran juntos
            [("P1", 450, 100, 3), ("P2", 10, 0, 1)],               # mucha CPU ociosa
            [("P1", 200, 0, 5), ("P2", 200, 0, 5), ("P3", 100, 0, 5)],  # empates totales
            [("P10", 50, 0, 3), ("P2", 50, 0, 3)],                 # desempate por ID
            [("A", 300, 0, 9), ("B", 200, 1, 1), ("C", 150, 2, 1)],  # suspension y vuelta
            [("P1", 100, 0, 20), ("P2", 100, 1, 1), ("P3", 100, 2, 1),
             ("P4", 100, 3, 1), ("P5", 100, 4, 1), ("P6", 100, 5, 1)],
        ]
        for lote in casos:
            with self.subTest(lote=lote):
                self.comparar(lote)


if __name__ == "__main__":
    unittest.main()
