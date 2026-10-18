# Camera Studio Community 0.9 — Guía de uso

[English](guide-en.md) · [Deutsch](guide-de.md) · [Dansk](guide-da.md) · [Español](guide-es.md) · [Polski](guide-pl.md) · [Français](guide-fr.md)

## Instalar, iniciar y desinstalar

Esta aplicación independiente para Ubuntu tiene su propio lanzador y configuración. No sustituye a Tiny 2 Studio. Requiere Python 3.10+, GTK 4.8+, GStreamer y Tesseract 5. Ubuntu 24.04 es el destino de las pruebas de GitHub; no se admiten versiones anteriores de GTK.

Descarga el DEB, abre una terminal en su carpeta y ejecuta:

```sh
sudo apt install ./camera-studio-community_0.9.0_all.deb
camera-studio-community
```

También puedes extraer el ZIP de código, instalar las dependencias de `build.py` y ejecutar `./Starten.sh`. Los modelos y SDK de cámara opcionales no se incluyen ni descargan automáticamente. H.264/H.265 pueden requerir `gstreamer1.0-plugins-bad` y `gstreamer1.0-libav`.

Puedes desinstalar aunque la aplicación no aparezca en App Center:

```sh
sudo apt remove camera-studio-community
```

Se conservan ajustes personales, proyectos de libros y el Tiny 2 Studio original. Una copia solo extraída se elimina borrando su carpeta después de guardar el trabajo.

## Idioma y ayuda

Al pie de la ventana principal, elige English, Deutsch, Dansk, Español, Polski o Français. La selección se guarda; cierra y reinicia la aplicación para aplicarla. Así no se interrumpen las cámaras activas. Al iniciar por primera vez se usa el idioma del sistema, o inglés si no está disponible. Guía abre la ayuda local en el idioma activo sin internet. `--language es` cambia el idioma durante un inicio sin modificar la preferencia guardada.

## Controles Tiny 2 y precisión

Conecta la cámara e inicia la vista previa. Conectar solo lee ajustes. Movimiento ofrece ángulos objetivo, pasos relativos, centrar, detener, zoom y activación/reposo. El movimiento manual desactiva el seguimiento. Las posiciones guardan localmente ángulos objetivo y zoom; no son posiciones físicas medidas. Los ángulos sin procesar del SDK son valores de diagnóstico con asignación de ejes y precisión sin verificar.

La cámara ejecuta el seguimiento y su velocidad. Un modo solo se confirma tras recibir la respuesta correspondiente. Los gestos dependen de los ajustes de la cámara; esta aplicación no puede activarlos ni consultar si están activos. Los controles de imagen dependen del controlador. No se incluyen efectos de belleza ni sustitución de fondo.

Separa la imagen para abrir una ventana desplazable. El control manual usa arrastre con botón izquierdo; la rueda cambia el zoom. F11 activa pantalla completa; Escape sale y desactiva el control manual/G13. Las superposiciones de texto, reloj y PNG/JPEG aparecen en esta aplicación; no se transmiten a otros programas como cámara virtual.

## Otras cámaras y tamaños de imagen

Abre Cámaras y perfiles, activa los adaptadores deseados y pulsa Buscar de nuevo. Tiny 2 siempre está integrada. Las cámaras Linux/UVC usan el perfil USB genérico. Los perfiles JSON adicionales asocian identificadores USB de fabricante y producto; plantilla: `profiles/usb-camera.example.json`. Contienen datos, no controladores ejecutables. No pueden sustituir a Tiny 2. Las cámaras propietarias requieren desarrollar un adaptador.

Cada cámara puede tener su ventana y conversación IA. Haz clic derecho en la imagen para herramientas y tamaños de ventana. Resolución y fotogramas por segundo se eligen entre los modos informados por el dispositivo. Los tamaños personalizados solo están disponibles en rangos admitidos por la cámara. Reinicia la vista previa tras cambiar de modo. Cambiar el tamaño de ventana no cambia la resolución de captura. Fuente de imagen muestra las dimensiones recibidas.

AmScope/MU300 requiere una instalación existente de AmLite para Linux. Cierra primero su vista previa. Se busca en `~/.local/opt/AmLite`, `/opt/AmLite`, `/usr/local/lib` y `/usr/lib`; `TINY2_AMCAM_LIBRARY` permite indicar otra biblioteca. Andonstar usa LiveView-MJPEG en el puerto 8192: conecta Ubuntu a la Wi-Fi de la cámara, activa el perfil y vuelve a buscar. La aplicación no cambia de red Wi-Fi. Estos adaptadores negocian el tamaño de captura; no se puede elegir aquí la resolución del sensor. Andonstar ofrece zoom digital, no control del enfoque del microscopio.

## Compartir, dibujar y escanear libros

Compartir imagen permite copiar al portapapeles y exportar PNG. Dibuja sobre una imagen fija con ratón o tableta: lápiz, resaltador, borrador de trazos completos, presión, deshacer y rehacer. Envía explícitamente el resultado a IA o guárdalo como PNG.

Escanear libro captura una página completa por toma. Usa una imagen estable e iluminación uniforme. La captura automática espera un cambio de página y una imagen estable y se pausa para revisar. Marca cuatro esquinas en sentido horario desde la superior izquierda o deja que las encuentre la IA seleccionada. Revisa la página enderezada antes de aceptarla; se conserva el original. El OCR local produce texto editable. Revisa el resultado antes de exportar PDF o EPUB. Los proyectos `.tinybook` conservan imágenes y correcciones. Límites: 500 páginas por proyecto y 20 megapíxeles por página.

Solo se incluyen datos OCR en alemán e inglés. Cambiar el idioma de interfaz no traduce libros ni añade idiomas OCR. La corrección de página con IA es independiente: envía una imagen reducida al proveedor seleccionado y rectifica el original localmente. La corrección IA automática está desactivada inicialmente y se desactiva al cambiar de proveedor.

## Proveedores de IA y datos

Elige Local, ChatGPT, Grok o Gemini en la ventana IA o al escanear. En Ajustes de IA, indica un ID de modelo con visión y respuestas JSON estructuradas. Local utiliza un modelo Ollama ya instalado en `127.0.0.1`; el puerto es configurable. Los proveedores en la nube requieren cuenta API propia, acceso al modelo y clave. No es un inicio de sesión en sus webs de chat; el uso de API puede tener coste.

Cambiar de proveedor no envía nada. Enviar transmite la imagen fija elegida, la pregunta y hasta ocho mensajes de texto de la conversación de ese proveedor. No se reenvían fotos anteriores. Cada proveedor tiene su historial en memoria, que se descarta al cerrar la ventana. Se muestran destino y modelo. Cancelar descarta respuestas posteriores, pero no recupera datos ya enviados. No hay cambio automático de proveedor si falla. Las respuestas y marcas pueden ser incorrectas; se pide a la IA responder en el idioma de interfaz.

Las claves nuevas solo duran la sesión por defecto. Guardarlas opcionalmente escribe `api-keys.json` sin cifrar, con permisos 0600 para la cuenta propietaria. Alternativas: `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` o `GOOGLE_API_KEY`. Prioridad: sesión, entorno, clave guardada. Eliminar borra la clave guardada y la bloquea durante la sesión; elimina variables de entorno fuera de la aplicación. OpenAI/xAI usan `store=false`, lo que no garantiza la ausencia de todos los registros del proveedor.

## Dictado, cómics y G13

El dictado requiere Python existente con faster-whisper y una carpeta de modelo local con `model.bin` y `config.json`. Configúralos en IA y servicios. Una carpeta compatible opcional con `guard_common.py` puede limitar el uso concurrente de memoria. El audio se procesa localmente; el texto se inserta para revisión antes de enviar. No se descargan modelos.

Leer cómic · OCR local abre una herramienta de portadas InvenTree compatible configurada aparte. Tesseract lee dos veces el recuadro del número para obtener serie, número y fecha; la búsqueda Panini ayuda a comprobar la edición. Es independiente del proveedor IA, no identifica con fiabilidad toda la portada y no registra existencias automáticamente. Sin esa herramienta siguen funcionando copiar y exportar PNG. La aplicación no traduce la interfaz de la herramienta externa.

G13 requiere un servicio g13d compatible existente y un perfil M2 vacío llamado `Tiny 2 Studio`. No se instalan perfiles de teclado. La pestaña G13 explica las teclas. Actívalo expresamente; bloquea el control por ratón y el zoom por rueda. Suelta la palanca tras cambiar de foco o perfil. G1/G22/pulsar palanca detiene y desactiva G13; G15 permite movimiento fino. G16 captura una página y G17 acepta una página revisada. Sin G13, los controles habituales siguen disponibles.

## Archivos, problemas y límites

Ajustes: `${XDG_CONFIG_HOME:-~/.config}/camera-studio-community/`. Libros: `${XDG_DATA_HOME:-~/.local/share}/camera-studio-community/books/`. `--config-dir RUTA` elige otra carpeta de configuración. Guarda copias de los proyectos antes de borrar datos personales; desinstalar no los elimina.

Si falta imagen, comprueba permisos USB, cierra otras aplicaciones de cámara, elige Automático o una resolución menor y reinicia la vista previa. Para errores IA, revisa capacidades del modelo, acceso API y destino mostrado. No subas claves, fotos personales ni archivos de configuración a informes de errores.

La compatibilidad de hardware y la precisión mecánica no están confirmadas para todas las cámaras. Las pruebas automáticas usan cámaras sintéticas y respuestas de nube simuladas. No se han verificado cuentas reales de nube ni todos los modos de hardware. Evidencias y procedencia: `TESTERGEBNIS.txt` y `SOURCES.txt`.
