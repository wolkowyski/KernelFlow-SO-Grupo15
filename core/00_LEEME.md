# core comentado: cómo leerlo

Esta carpeta es una **copia para estudiar** de `KernelFlow-SO-Grupo15/core`.

**El código es idéntico al entregado.** Solo se agregaron líneas que empiezan con `#`, que Python ignora. Está verificado: la estructura del código de los 11 archivos coincide con la del original, y la copia produce exactamente la misma salida con la demo y con los CSV de prueba. El repo entregado no se tocó.

## Cómo leer los comentarios

| Marca | Qué es |
|---|---|
| Bloque `# ====` arriba de cada archivo | Qué hace el archivo, quién lo usa, a quién usa y una frase para el coloquio |
| `# >>` | La explicación de la línea de arriba (qué hace y por qué) |
| `# PASO 1:`, `# PASO 2:`… | Los pasos de una función larga, en orden |
| `PREGUNTA POSIBLE:` / `RESPUESTA:` | Algo que el profe puede preguntar, con la respuesta |
| `LA LLAMA:` / `ENTRA:` / `SALE:` | Desde dónde se usa la función, qué recibe y qué devuelve |

## Orden de lectura recomendado

1. **`proceso.py`**: la "ficha" de cada proceso y los 5 estados. Es corto y es la base de todo.
2. **`estados.py`**: el diagrama de estados como tabla. Muy corto.
3. **`memoria.py`**: MVT y Best-Fit (`asignar`, `liberar`, `_buscar_indice_best_fit`).
4. **`admision.py`**: el cupo de 5, NUEVO / LISTO / LISTO_SUSPENDIDO y los reintentos. **El de Braian.**
5. **`planificador.py`**: SRTF, la apropiación, el reloj y `_finalizar`.
6. **`main.py`**: solo `ejecutar_simulacion`, que conecta todo lo anterior.
7. **`carga.py`**: cómo se lee y valida el CSV (los avisos de los CSV de prueba).
8. **`estadisticas.py`**: las 4 fórmulas.
9. **`presentacion.py`**: solo imprime. Es lo menos importante para el coloquio.

`__init__.py` y `__main__.py` son de dos líneas: solo hacen que `python -m core` funcione.

## Quién llama a quién

```
main.ejecutar_simulacion
 ├─ carga.cargar_lote(csv)                       -> lista de Proceso
 ├─ GestorMemoria()                               -> memoria (1 hueco de 450K)
 ├─ Admision(procesos, memoria)                   -> colas vacías
 ├─ PresentacionConsola(procesos, admision, memoria)
 ├─ PlanificadorSRTF(admision, memoria, eventos_paso.append)
 └─ CICLO (una vuelta = un instante t)
     ├─ planificador.procesar_instante()
     │    ├─ admision.procesar_arribos(t)         <- LARGO plazo
     │    │    └─ _admitir_nuevos -> _intentar_cargar -> memoria.asignar (Best-Fit)
     │    └─ _reevaluar_cpu()                      <- CORTO plazo (SRTF)
     │         ├─ seleccionar_srtf(listos)
     │         └─ si hay apropiación: devolver_a_listo + enviar_a_ejecucion
     ├─ si hubo eventos -> presentacion.mostrar_paso(...)
     └─ planificador.ejecutar_unidad()             restante -1, reloj +1
          └─ si restante == 0 -> _finalizar()
               ├─ admision.finalizar               EJECUCION -> TERMINADO
               ├─ memoria.liberar                  hueco + fusión de vecinos
               ├─ admision.reintentar_suspendidos  <- MEDIANO plazo
               ├─ admision.procesar_arribos(t)
               └─ seleccionar_srtf -> _asignar_cpu (el siguiente, sin dejar la CPU ociosa)
```

## Las 10 funciones que hay que saber sí o sí

| # | Función | Archivo | En una frase |
|---|---|---|---|
| 1 | `ejecutar_simulacion` | main.py | Arma los módulos y corre el ciclo |
| 2 | `procesar_arribos` | admision.py | Llegadas de t: pasan a NUEVO y se intenta admitirlas |
| 3 | `_admitir_nuevos` | admision.py | Mientras haya cupo (< 5), saca de NUEVO y busca memoria |
| 4 | `_intentar_cargar` | admision.py | Pide hueco: LISTO, o LISTO_SUSPENDIDO con el motivo |
| 5 | `reintentar_suspendidos` | admision.py | Al liberarse memoria: suspendidos (FIFO) y después nuevos |
| 6 | `grado_multiprogramacion` | admision.py | EJECUCION + LISTO + LISTO_SUSPENDIDO |
| 7 | `asignar` + `_buscar_indice_best_fit` | memoria.py | El hueco más chico donde entra; el sobrante queda como hueco |
| 8 | `liberar` + `_compactar_huecos_adyacentes` | memoria.py | La partición vuelve a ser hueco y se une con los vecinos |
| 9 | `_reevaluar_cpu` + `seleccionar_srtf` | planificador.py | Menor restante; con `<=`, en un empate sigue el actual |
| 10 | `_finalizar` | planificador.py | Termina, libera, reintenta, arribos y asigna el siguiente |

## Para practicar

Abrí al lado el CSV de prueba que corresponde (en `coloquio\csv_pruebas`) y seguí en el código lo que muestra la pantalla:

- **B_multiprog_llena**: `_admitir_nuevos` corta el `while` cuando el grado llega a 5.
- **C_memoria_llena** y **D_frag_externa**: los dos `motivo` de `_intentar_cargar`.
- **E_errores**: cada `raise ValueError` de `_validar_fila` en `carga.py`.
- **J_empates**: el `<=` de `_reevaluar_cpu`.
