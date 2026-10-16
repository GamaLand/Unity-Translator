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
   trabajo completo. Selecciona de 1 a 16 solicitudes paralelas según la capacidad del
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
