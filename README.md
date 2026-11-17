# KernelFlow

Simulador de asignación de memoria y planificación de procesos por consola,
desarrollado en Python 3 para el TPI de **Sistemas Operativos** (UTN Facultad
Regional Resistencia, 2026, Comisión K 2.1 Turno Tarde, **Grupo 15**).

Carga hasta 10 procesos desde un CSV, administra 450K de memoria de usuario
con particiones variables (MVT) y Best-Fit, y planifica la CPU con SRTF
apropiativo. Los primeros 100K quedan reservados para el sistema operativo.
La simulación avanza paso a paso: se detiene cada vez que llega o termina un
proceso.

**Integrantes:** Bader Soraire, Cain Abel · Gonzalez, Carlos Alfredo · Leiva
Romero, Agustin Nazareno · Seelaff, Mauricio Guillermo · Torres, Alejandro
Valentin · Wolkowyski, Braian Leonel · Zurano Lang, Lucas Maximiliano.

## Estructura

```text
kernel-flow/
├── main.py              # Arranca la versión completa (la del ejecutable)
├── core/                # Lógica del simulador: la versión base del TPI
│   ├── main.py          #   menú simple y ciclo de la simulación paso a paso
│   ├── proceso.py       #   modelo de proceso
│   ├── estados.py       #   estados y transiciones permitidas
│   ├── carga.py         #   lectura y validación del CSV
│   ├── memoria.py       #   memoria MVT con Best-Fit
│   ├── admision.py      #   admisión, colas y multiprogramación 5
│   ├── planificador.py  #   reloj y planificación SRTF
│   ├── estadisticas.py  #   retorno, espera, promedios y rendimiento
│   └── presentacion.py  #   salida de texto
├── interfaz/            # Presentación extra (no forma parte de la consigna)
│   ├── main.py          #   menú completo, navegación entre pasos y guardado
│   ├── panel.py         #   tablas, mapa de memoria, gráficos y Gantt
│   ├── estilo.py        #   colores ANSI y tablas con bordes
│   ├── entrada.py       #   lectura de teclas y elección del CSV
│   └── exportar.py      #   guardado en TXT y HTML
├── data/                # Lotes de prueba
├── tests/               # Pruebas automáticas
├── docs/                # HOWTO e informe con capturas (Word)
├── empaquetar.py        # Genera el ejecutable y el ZIP de entrega
└── kernelflow.spec      # Configuración de PyInstaller
```

La carpeta `core/` no depende de `interfaz/`. La interfaz usa los mismos
módulos y solo cambia la forma de mostrar el estado.

## Ejecución

Con el ejecutable del paquete de entrega:

```bash
./KernelFlow            # Linux (carpeta "ejecutable")
KernelFlow.exe          # Windows (doble clic)
```

Desde el código fuente (Python 3.8 o superior, sin librerías externas):

```bash
python3 main.py                        # versión completa
python3 main.py data/lote_1_best_fit.csv
python3 -m core                        # versión base, solo texto
python3 -m core data/lote_1_best_fit.csv
```

En Windows se usa `py` en lugar de `python3`.

Opciones de la versión completa: `--sin-color` (sin colores),
`--pantalla-fija` (limpia la pantalla en cada paso) y `--exportar` (guarda la
simulación en `resultados/` al terminar).

### Controles

| Versión completa | Versión base | Acción |
|---|---|---|
| Espacio / Enter | Enter | Avanza al siguiente cambio |
| B | — | Vuelve al paso anterior |
| F | — | Alterna historial y pantalla fija |
| Q | `q` + Enter | Vuelve al menú |
| G (al terminar) | — | Guarda la simulación en TXT y HTML |

## Formato del CSV

Una fila por proceso, sin encabezado, con el orden
`id_proceso,tamanio,t_arribo,t_irrupcion`. Se admiten entre 1 y 10 procesos;
el tamaño va en KB (1 a 450) y los tiempos son enteros (arribo ≥ 0,
irrupción > 0).

```csv
P1,120,0,8
P2,150,1,4
P3,100,2,9
```

## Comportamiento

- **Estados:** `NUEVO`, `LISTO`, `LISTO_SUSPENDIDO`, `EJECUCION` y
  `TERMINADO` (sin E/S ni `BLOQUEADO`).
- **Multiprogramación:** como máximo 5 procesos entre `EJECUCION`, `LISTO` y
  `LISTO_SUSPENDIDO`. Un proceso sin cupo permanece en `NUEVO`; uno con cupo
  pero sin hueco de memoria pasa a `LISTO_SUSPENDIDO`.
- **Memoria:** Best-Fit elige el hueco libre más chico donde entra el
  proceso. Al liberar una partición se fusionan los huecos contiguos y se
  reintentan primero los suspendidos (en orden de llegada) y luego los nuevos
  que esperan cupo.
- **SRTF:** se ejecuta el proceso con menor tiempo restante; una llegada con
  menor tiempo restante apropia la CPU. Ante un empate, el proceso que ya está
  en CPU la conserva. Con la CPU libre se elige por menor tiempo restante,
  luego menor arribo y luego menor ID.
- **Salida:** en cada paso se muestran los eventos con su motivo, el proceso
  en CPU, las colas `LISTO` y `LISTO_SUSPENDIDO`, la tabla de procesos y la
  tabla de particiones (ID, dirección de comienzo, tamaño, proceso y
  fragmentación interna, que en MVT es siempre 0K).
- **Informe final:** tiempo de retorno (finalización − arribo) y de espera
  (retorno − irrupción) de cada proceso, sus promedios, tiempo de respuesta y
  rendimiento (trabajos terminados / tiempo total).

## Lotes de prueba

| Archivo | Qué muestra |
|---|---|
| `procesos_demo.csv` | Apropiación SRTF, suspensión por memoria y fragmentación externa |
| `lote_1_best_fit.csv` | Best-Fit elige el hueco más chico aunque haya uno más grande antes |
| `lote_2_cupo_10_procesos.csv` | 10 procesos: cupo de multiprogramación y memoria llenos |
| `lote_3_cpu_ociosa_memoria_exacta.csv` | CPU ociosa entre arribos y un proceso de 450K exactos |
| `lote_4_empate_srtf.csv` | Empate de tiempo restante: el proceso en CPU la conserva |

El lote de demostración termina en t = 31 con retorno promedio 14.00 ut,
espera promedio 8.83 ut y rendimiento 0.1935 trabajos por unidad de tiempo.

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```

## Paquete de entrega

```bash
python3 -m pip install pyinstaller
python3 empaquetar.py
```

Corre las pruebas, genera el ejecutable y deja
`entrega/KernelFlow-<sistema>.zip` con el ejecutable y la carpeta `data/`,
el código fuente, `HOWTO.txt` y la guía con capturas. PyInstaller no genera
ejecutables para otro sistema: el de Linux se arma en Linux y el de Windows
en Windows.

## Documentación

- `docs/HOWTO_KernelFlow_Grupo15.docx`: guía de ejecución con capturas.
- `docs/Informe_Simulaciones_Grupo15.docx`: capturas de cada paso de los
  cinco lotes, validaciones y versión base.
- [Tablero de Trello](https://trello.com/invite/b/660d6768671c589f7fe1ad3c/ATTIfcc43a38988bc5a0fdae81020ef1ac0f450A99A4/so-2026)
  · [Diagrama de flujo (draw.io)](https://drive.google.com/file/d/1SHgLzj9BOfEBwsSJKS4dxIwl1VEnXMCb/view?usp=sharing)
  · [Video Sprint 1](https://youtu.be/IwoRyFjnta0)
