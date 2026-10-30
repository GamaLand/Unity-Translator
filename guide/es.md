# Guía de uso de UnityTranslator

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

**Crear ZIP de instalación Ren'Py** admite la versión correspondiente con un solo
EXE de juego en la raíz. El ZIP no contiene archivos originales del juego.
Extráelo fuera del original y ejecuta `Install.cmd`. Selecciona el juego coincidente
y una carpeta de salida independiente; revisa el plan exacto de archivos nuevos.
Se crea una copia traducida completa que requiere espacio adicional. No se sustituyen
originales ni se inicia el juego. `Play-Translated.cmd` en la copia inicia el idioma
del paquete. No se copian partidas, registros ni cachés originales; las partidas
de la copia son independientes. El destinatario no necesita Python, modelo ni UnityTranslator.

Conserva el ZIP para `Remove.cmd`. Solo se eliminan archivos propios sin cambios;
se conservan los modificados o creados durante la ejecución y los recibos.
La carpeta no se vacía por completo.
CLI: `export-renpy-zip --game ... --project ... --language turkish`.
No se admite instalar directamente en la carpeta original.

Si el informe del piloto muestra un trabajo en curso, actualízalo cuando se detenga. Un piloto cancelado puede evaluarse si se intentó toda la muestra necesaria y existen resultados completos. La evaluación habilita el trabajo completo con los mismos ajustes y fuentes; no aprueba traducciones.

Tras revisar la prueba, los cambios guardados de glosario/estilo se aplican a nuevas solicitudes sin repetirla. Las solicitudes en curso conservan sus reglas originales; las traducciones existentes no cambian. Revisa los registros afectados y vuelve a traducirlos explícitamente si hace falta. Usar los ajustes del piloto revisado restaura el modelo y la generación, conservando el glosario/estilo actual.

En Revisión, Volver a traducir los registros de esta página envía hasta 200 registros de la página filtrada visible a la cola común con el modelo actual y el glosario/estilo guardado. Se requiere una prueba revisada con los mismos ajustes. Se excluyen borradores y registros en curso. El texto aprobado sigue seleccionado; los nuevos candidatos aparecen en el historial. La pestaña Traducir muestra el progreso.

En Revisión, **Acciones en lote** permite aprobar traducciones no vacías exactamente idénticas al original o devolver las vacías a Pendiente. Abarca todas las páginas de los filtros actuales, con recuento y ejemplos antes de confirmar. Borre los filtros para abarcar todo el proyecto. Se excluyen borradores, registros en cola/en proceso y aprobaciones existentes. Una copia puede ser una frase sin traducir: aprobarla es su decisión explícita. Devolver vacíos conserva el historial y no envía solicitudes al modelo; después inicie un trabajo en Traducir con el piloto revisado habitual.

Al devolver traducciones vacías a Pendiente, se permiten entradas de trabajos pausados. La vista previa las cuenta; al reanudar se omitirán las entradas antiguas porque cambia la versión del registro. Se conserva el historial. Otras entradas en cola/en proceso siguen bloqueando la acción; los registros excluidos se distinguen de la ausencia de coincidencias.
