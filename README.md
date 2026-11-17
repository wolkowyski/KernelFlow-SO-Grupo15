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

## Descargas (entrega final)

| Archivo | Qué es |
|---|---|
| [`descargas/KernelFlow-linux.zip`](descargas/KernelFlow-linux.zip) | Ejecutable para **Linux** + lotes de prueba + código fuente + HOWTO |
| [`descargas/KernelFlow-windows.zip`](descargas/KernelFlow-windows.zip) | Ejecutable para **Windows 10/11** + lo mismo |
| [`docs/Informe_Simulaciones_Grupo15.docx`](docs/Informe_Simulaciones_Grupo15.docx) | Informe con capturas de todos los lotes |
| [`docs/HOWTO_KernelFlow_Grupo15.docx`](docs/HOWTO_KernelFlow_Grupo15.docx) | Guía de ejecución con capturas |
| [`HOWTO.md`](HOWTO.md) | Guía rápida de ejecución (texto) |

**Para probarlo rápido:** descargar el ZIP de tu sistema, descomprimirlo y
abrir `ejecutable/KernelFlow` (Linux: `./KernelFlow` en una terminal) o
`ejecutable\KernelFlow.exe` (Windows: doble clic). No hace falta instalar
Python. Para correrlo desde el código: `python3 main.py`.

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
├── kernelflow.spec      # Configuración de PyInstaller
└── descargas/           # Paquetes de entrega listos (Linux y Windows)
```

### Por qué está dividido en `core/` e `interfaz/`

Lo pidieron los docentes en la revisión de la segunda entrega: separar la
**versión base del TPI** de la **presentación extra**.

- `core/` es el simulador que pide la consigna. Cada módulo tiene una sola
  responsabilidad (carga, memoria, admisión, planificador, estadísticas,
  salida), así se puede leer, probar y defender por partes, en vez de un único
  archivo `.py` gigante.
- `interfaz/` solo cambia **cómo se muestra** el estado: colores, mapa de
  memoria, Gantt, navegación entre pasos y exportación. No tiene reglas de
  negocio: usa la misma carga, memoria, admisión y planificador de `core/`.
- La regla se verifica con una prueba (`tests/test_separacion.py`): ningún
  módulo de `core/` importa nada de `interfaz/`, y las dos versiones producen
  exactamente la misma simulación en todos los lotes.

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

Una fila por proceso con el orden `id_proceso,tamanio,t_arribo,t_irrupcion`:

```csv
P1,120,0,8
P2,150,1,4
P3,100,2,9
```

| Campo | Valores válidos |
|---|---|
| `id_proceso` | Único, hasta 10 caracteres: letras, números, `_`, `-` o `.` |
| `tamanio` | Entero en KB, de 1 a 450 (memoria de usuario) |
| `t_arribo` | Entero de 0 a 999 |
| `t_irrupcion` | Entero de 1 a 999 |

También se aceptan `;` o tabulación como separador (Excel en español guarda
con `;`), una fila de encabezado, líneas vacías, comentarios que empiezan con
`#` y archivos guardados con la codificación de Windows.

### Validación y filas con errores

El simulador **nunca corrige ni inventa datos**. Cada fila con un problema se
**descarta con un aviso** que indica la línea y el motivo, y se simulan los
procesos válidos (antes de empezar se pide confirmación):

- campos vacíos, letras, decimales, negativos o fuera de rango;
- cantidad de columnas incorrecta, ID vacío, inválido o repetido;
- un proceso de más de 450K, que nunca podría cargarse en memoria;
- a partir del proceso 11, porque la consigna permite como máximo 10.

Si el archivo no existe, no es de texto o no tiene ningún proceso válido, se
informa el motivo y no se simula. Los tiempos tienen un tope de 999 para que
un valor exagerado no deje al simulador avanzando el reloj sin fin.

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

### Lotes de la cátedra

Los seis lotes enviados por los docentes están en `data/catedra_lote_*.csv`:

| Archivo | Procesos | Avisos | Fin | Retorno prom. | Espera prom. | Rendimiento |
|---|---|---|---|---|---|---|
| `catedra_lote_1.csv` | 5 | 0 | 22 | 2.60 | 0.40 | 0.2273 |
| `catedra_lote_2.csv` | 5 | 0 | 56 | 26.20 | 15.00 | 0.0893 |
| `catedra_lote_3.csv` | 8 | 0 | 55 | 20.00 | 13.12 | 0.1455 |
| `catedra_lote_4.csv` | 10 | 0 | 56 | 15.90 | 10.30 | 0.1786 |
| `catedra_lote_5.csv` | 2 | 1 | 9 | 6.00 | 1.50 | 0.2222 |
| `catedra_lote_6.csv` | 10 | 2 | 45 | 19.40 | 14.90 | 0.2222 |

En el lote 5 se descarta P2 (451K: nunca entra en los 450K de usuario) y en
el lote 6, P11 y P12 (la consigna permite como máximo 10 procesos).

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```

Además de las pruebas de cada módulo:

- **Simulador de referencia** (`tests/test_robustez.py`): un segundo
  simulador, escrito aparte con las mismas reglas, se compara instante por
  instante con el real en 800 lotes al azar, en los lotes de `data/` y en
  casos límite (memoria exacta, 10 procesos, empates, CPU ociosa).
- **Invariantes en cada instante:** memoria contigua de 100K a 550K sin
  solapamientos, huecos unidos y sin fragmentación interna; como máximo 5
  procesos entre `EJECUCION`, `LISTO` y `LISTO_SUSPENDIDO`; una sola CPU; el
  proceso en CPU siempre tiene el menor tiempo restante; ningún proceso se
  atiende antes de su arribo ni queda olvidado en `NUEVO` habiendo cupo, y
  ningún suspendido espera si entra en un hueco.
- **Carga tolerante** (`tests/test_carga_tolerante.py`): formatos de Excel,
  filas con errores, tiempos enormes, archivos binarios o vacíos.

## Compatibilidad

Funciona en **Linux** y en **Windows 10/11** con Python 3.8 o superior, sin
librerías externas. Las pruebas y la simulación se verificaron en los dos
sistemas, y se entrega un ejecutable para cada uno.

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
- [Repositorio en GitHub](https://github.com/wolkowyski/KernelFlow-SO-Grupo15)
- [Tablero de Trello](https://trello.com/invite/b/660d6768671c589f7fe1ad3c/ATTIfcc43a38988bc5a0fdae81020ef1ac0f450A99A4/so-2026)
  · [Diagrama de flujo (draw.io)](https://drive.google.com/file/d/1SHgLzj9BOfEBwsSJKS4dxIwl1VEnXMCb/view?usp=sharing)
  · [Video Sprint 1](https://youtu.be/IwoRyFjnta0)
