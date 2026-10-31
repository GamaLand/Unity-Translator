# Guía de uso de UnityTranslator

## Área de trabajo

La barra lateral agrupa preparación, traducción/revisión y entrega. Arrastre los separadores para ajustar la lista y los editores de origen/traducción etiquetados. Abajo, cambie entre **Comparación de textos** y **Referencias y comprobaciones**; los avisos siguen visibles. **Herramientas del registro** contiene historial, nuevos candidatos, plurales y eliminación del borrador. **Acciones masivas** contiene operaciones de página/filtro/proyecto con sus vistas previas y confirmaciones. Guardar y aprobar siguen siendo pasos distintos. Los formularios se desplazan en ventanas pequeñas (mínimo 900 × 740).

## Contexto de diálogo verificado

La preparación del piloto muestra la fase de registros o contexto antes de enviar solicitudes al modelo. Un proyecto grande puede necesitar una primera revisión del contexto. Cancelar detiene la preparación de forma segura; el cierre espera la limpieza. Reanuda el piloto guardado con Continuar sin recrear el proyecto.

En los ajustes avanzados del modelo, **Usar diálogos vecinos verificados** es opcional y está desactivado de forma predeterminada. Los segmentos Ren’Py compatibles muestran el orden de origen y aportan hasta dos réplicas anteriores y posteriores. Opciones, condiciones, saltos, llamadas, sintaxis desconocida y límites de archivos cortan la ventana; las plantillas solo enlazan réplicas de un mismo bloque. Las tablas de términos Unity y las fuentes sin orden demostrado siguen aisladas. La revisión muestra referencias que pueden reducirse según el presupuesto. Cambiar de modo exige un piloto revisado coincidente. Se conservan tareas, traducciones, borradores y aprobaciones existentes; no se garantiza mayor naturalidad.

## Instalación e idioma

En Windows x64, extrae **todo** el ZIP de la aplicación en una carpeta independiente y
abre `UnityTranslator.exe`. El paquete preparado no necesita Python. Desde el código fuente:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

El idioma inicial es inglés. **Language**, junto a **Help**, permite elegir entre ocho
idiomas. La elección se aplica al volver a abrir la aplicación y no cambia los idiomas
de origen y destino del proyecto.

## Traducir

1. **Proyecto:** elige la carpeta del juego, otra carpeta para el proyecto y los códigos
   de idioma. Abre un proyecto existente para continuar el trabajo.
2. **Textos:** analiza la compatibilidad, selecciona una fuente admitida y extrae los textos.
   La extracción y la instalación se comprueban por separado.
3. **Modelo:** inicia LM Studio o llama-server y carga tú mismo el modelo. Introduce la
   dirección local y el identificador del modelo, y prueba la conexión.
4. **Glosario:** añade opcionalmente nombres protegidos, términos preferidos y reglas de estilo.
5. **Traducir:** realiza y revisa primero una prueba representativa; después inicia el
   trabajo completo. Selecciona de 1 a 36 solicitudes paralelas según la capacidad del
   servidor. Minimizar no detiene la traducción. La pausa espera las solicitudes activas;
   cancelar interrumpe las tareas del cliente.
6. **Revisión:** compara, corrige, guarda y aprueba. Guardar un borrador no lo aprueba.
   La aprobación por página afecta solo a los registros aptos seleccionados. Para aprobar
   todas las traducciones, acepta primero el alcance y las advertencias; después escribe
   exactamente la frase indicada y pulsa el botón final. Puedes cancelar en ambos pasos.
   Se excluyen borradores y errores de formato; si cambia la lista, no hay aprobación parcial.

## Copias, instalación y distribución

Exporta JSON o una copia de seguridad del proyecto. Cierra el juego antes de preparar
el plan de instalación. Revisa los archivos nuevos y confirma la instalación por separado.
Abre tú mismo el juego y comprueba caracteres, diseño y significado. La aplicación al
juego sigue siendo experimental.

Desinstala los añadidos desde el proyecto original. No sobrescribas ni borres a ciegas
`winhttp.dll`/`doorstop_config.ini` y no reinicies el inventario original.
Consulta la [guía para desarrolladores](../docs/installation.md).

Quien recibe un ZIP compartible usa `Kur.cmd` para elegir la carpeta de la misma versión
del juego y `Kaldir.cmd` para retirar únicamente los añadidos propios sin modificar.
No necesita modelo ni UnityTranslator. Conserva las licencias y fuentes incluidas.
No se admiten todos los juegos Unity y las comprobaciones no garantizan la calidad.
Algunos diagnósticos técnicos conservan el idioma original.


Los idiomas de origen y destino del juego son independientes del idioma de la interfaz. Usa ja para japonés, it para italiano o pt-BR para portugués brasileño; también puedes introducir otros códigos. El idioma de origen debe existir en el juego. Se rechazan las columnas ausentes o ambiguas. El modelo debe admitir el par. Se conservan los idiomas, las aprobaciones y las reglas de estilo de proyectos existentes; revisa las reglas antiguas específicas de un idioma. Comprueba fuentes, diseño RTL y plurales con un parche pequeño antes de compartirlo. El inglés también puede ser el idioma de destino.

## Krypta FM

Para la versión compatible de Krypta FM, elija origen `en` y destino `tr`. El perfil 2 cubre 449 campos de 34 TextAssets y una tabla del diario; quedan excluidas dos fuentes y otros textos de interfaz o imágenes. Se conservan las identidades y aprobaciones.

Tras revisar y aprobar las traducciones, cierre el juego y revise en «Aplicar al juego» el plan de los dos archivos nuevos: `winhttp.dll` y `doorstop_config.ini`. El runtime experimental permanece en el proyecto separado; no se sustituyen archivos originales. Retire los añadidos desde el mismo proyecto. La exportación de textos no es un instalador; los ZIP de instalación también admiten la versión Krypta en→tr verificada. El destinatario ejecuta Install.cmd, revisa el plan y escribe INSTALL; Uninstall.cmd elimina solo los añadidos propios sin cambios. La combinación portátil tiene pruebas sintéticas; su prueba específica dentro del juego queda pendiente. Se observaron inicio/menú, opciones, entrada al juego, pausa y subtítulos. Otras pantallas, cambios de idioma y disposición del texto requieren revisión manual; una etiqueta larga puede superponerse a su explicación.

En los ajustes avanzados puedes desactivar opcionalmente el razonamiento para las solicitudes de LM Studio. Esto puede dejar más presupuesto de salida para la traducción. La compatibilidad depende del modelo y servidor; una opción no admitida puede detener el trabajo. Se conservan los valores predeterminados y los ajustes globales del servidor.

## Traducción Ren'Py

En Textos, selecciona el motor y analiza el juego. Un archivo
`game/tl/<idioma>/*.rpy` lee toda la carpeta de idioma. Los `.rpy` originales,
`_ren.py` verificados y archivos RPA-3.0 con fuentes se comprueban mediante contratos
de comportamiento comparados con Ren'Py 8.1.2 y 8.3.6; la versión por sí sola no
concede soporte. Se admiten conjuntos grandes y contenedores sin solapamientos;
se rechazan rutas o nombres base de fuentes coincidentes. Se cubren diálogos de una
línea con atributos de personaje y temporales `@`, `nointeract`, claves explícitas
`_()` y textos de menú. El diálogo del menú debe preceder a las opciones y no puede
mezclarse con títulos. Quedan excluidos los grupos voice/nvl, diálogos multilínea,
texto dinámico, scripts solo compilados y textos en imágenes. Revisa las exclusiones.
No se ejecuta código del juego. Los grandes resultados pueden dividirse en archivos
numerados; conserva junto todo el árbol exportado.

El ZIP de instalación sigue limitado a Ren'Py `8.1.2.23090503`; los metadatos privados de repositorios, herramientas de IA o credenciales bloquean el empaquetado de la copia.

Usa el modelo, piloto, borradores y revisión humana existentes. Las traducciones
anteriores de las plantillas quedan en el historial para lectura. Tras aprobar,
introduce un identificador Ren'Py de destino, como `turkish`; no se convierte
automáticamente el código de idioma. Termina o descarta los borradores.
El exportador nativo prepara los archivos en el proyecto; las traducciones aprobadas
contradictorias de una clave global bloquean la exportación.

**Crear ZIP de instalación Ren'Py** empaqueta traducciones aprobadas para la versión coincidente con un EXE en la raíz. Extraiga el ZIP fuera del juego y ejecute `Install.cmd`. Elija una vez la carpeta original, revise el plan y escriba `INSTALL`. No se copia el juego ni se reemplazan archivos existentes; los conflictos detienen la instalación. Solo se añaden traducciones, `Play-Translated.cmd` y pequeños recibos. No hace falta una copia de seguridad de los originales.

`Play-Translated.cmd` en el juego selecciona el idioma traducido. Se usan las partidas normales. Jugar puede cambiar partidas, cachés, registros y bytecode; desinstalar no restaura progreso anterior.

Conserve el ZIP para `Remove.cmd`. Cierre el juego y elija la misma carpeta. Solo se eliminan añadidos propios sin cambios; se conservan archivos modificados/enlazados/desconocidos y recibos. Si se generaron `.rpyc` de traducción, la eliminación se detiene antes de borrar nada: revise/elimine manualmente solo los indicados y reintente. No borre otros `.rpyc` del juego. Los ZIP antiguos mantienen la copia completa.

CLI: `export-renpy-zip --game ... --project ... --language turkish`. Revise fuentes, diseño y otras escenas.

Si el informe del piloto muestra un trabajo en curso, actualízalo cuando se detenga. Un piloto cancelado puede evaluarse si se intentó toda la muestra necesaria y existen resultados completos. La evaluación habilita el trabajo completo con los mismos ajustes y fuentes; no aprueba traducciones.

Tras revisar la prueba, los cambios guardados de glosario/estilo se aplican a nuevas solicitudes sin repetirla. Las solicitudes en curso conservan sus reglas originales; las traducciones existentes no cambian. Revisa los registros afectados y vuelve a traducirlos explícitamente si hace falta. Usar los ajustes del piloto revisado restaura el modelo y la generación, conservando el glosario/estilo actual.

En Revisión, Volver a traducir los registros de esta página envía hasta 200 registros de la página filtrada visible a la cola común con el modelo actual y el glosario/estilo guardado. Se requiere una prueba revisada con los mismos ajustes. Se excluyen borradores y registros en curso. El texto aprobado sigue seleccionado; los nuevos candidatos aparecen en el historial. La pestaña Traducir muestra el progreso.

En Revisión, **Acciones en lote** permite aprobar traducciones no vacías exactamente idénticas al original o devolver las vacías a Pendiente. Abarca todas las páginas de los filtros actuales, con recuento y ejemplos antes de confirmar. Borre los filtros para abarcar todo el proyecto. Se excluyen borradores, registros en cola/en proceso y aprobaciones existentes. Una copia puede ser una frase sin traducir: aprobarla es su decisión explícita. Devolver vacíos conserva el historial y no envía solicitudes al modelo; después inicie un trabajo en Traducir con el piloto revisado habitual.

Al devolver traducciones vacías a Pendiente, se permiten entradas de trabajos pausados. La vista previa las cuenta; al reanudar se omitirán las entradas antiguas porque cambia la versión del registro. Se conserva el historial. Otras entradas en cola/en proceso siguen bloqueando la acción; los registros excluidos se distinguen de la ausencia de coincidencias.
