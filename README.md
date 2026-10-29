# Mis lugares

**De una lista de direcciones a un mapa de lugares.**

Mis lugares es una aplicación web liviana para transformar una lista de
direcciones en coordenadas geográficas revisadas, listas para exportar y
utilizar en herramientas como Google My Maps.

El proyecto nació de una necesidad práctica: geocodificar direcciones
sin depender de plataformas pagas, comparar resultados de más de una
fuente y mantener una instancia de revisión humana antes de dar por
correcta una ubicación.

> **Resumen del caso:** una herramienta gratuita, desplegable como
> aplicación web, que combina dos servicios de geocodificación,
> comparación espacial, validación manual y exportación estructurada en
> CSV o Excel.

------------------------------------------------------------------------

## Índice

-   [Problema](#problema)
-   [Solución](#solución)
-   [Flujo de trabajo](#flujo-de-trabajo)
-   [Funcionalidades](#funcionalidades)
-   [Criterios de validación](#criterios-de-validación)
-   [Tecnologías](#tecnologías)
-   [Estructura del proyecto](#estructura-del-proyecto)
-   [Instalación local](#instalación-local)
-   [Despliegue en Streamlit Community
    Cloud](#despliegue-en-streamlit-community-cloud)
-   [Formato de entrada](#formato-de-entrada)
-   [Formato de salida](#formato-de-salida)
-   [Limitaciones y consideraciones](#limitaciones-y-consideraciones)
-   [Privacidad y uso responsable](#privacidad-y-uso-responsable)
-   [Decisiones de producto y diseño](#decisiones-de-producto-y-diseño)
-   [Caso de éxito: valor generado](#caso-de-éxito-valor-generado)
-   [Próximas mejoras posibles](#próximas-mejoras-posibles)
-   [Licencia](#licencia)

------------------------------------------------------------------------

## Problema

Geocodificar una lista de direcciones puede parecer una tarea simple,
pero en la práctica aparecen varios problemas:

-   No siempre una fuente devuelve la misma ubicación que otra.
-   Una coincidencia puede corresponder a una calle o zona aproximada y
    no necesariamente al número de puerta correcto.
-   Revisar coordenadas fila por fila en una planilla es lento y poco
    intuitivo.
-   Las soluciones comerciales pueden requerir una cuenta, una API key o
    un presupuesto.
-   El resultado necesita un formato consistente para poder reutilizarse
    en mapas y otros procesos.

El objetivo no fue construir una plataforma geográfica compleja, sino
resolver ese flujo cotidiano con una herramienta accesible y fácil de
operar.

## Solución

Mis lugares ofrece una interfaz guiada que permite:

1.  Cargar un archivo CSV con direcciones.
2.  Consultar dos servicios de geocodificación: **Nominatim**, de
    OpenStreetMap, y **Photon**.
3.  Comparar las coordenadas devueltas por ambas fuentes.
4.  Identificar coincidencias, discrepancias, resultados de una sola
    fuente y direcciones no encontradas.
5.  Revisar cada candidato en un mapa y elegir la ubicación correcta.
6.  Visualizar el conjunto de ubicaciones validadas.
7.  Descargar solo los registros aprobados en CSV o Excel.

La aplicación mantiene el control de la decisión en manos de la persona
usuaria. La coincidencia entre dos fuentes sirve como señal de
confianza, no como garantía de exactitud.

## Flujo de trabajo

### 1. Cargar

-   Subir un archivo CSV.
-   Seleccionar la columna que contiene las direcciones.
-   Indicar el país que se agregará a las búsquedas cuando no figure en
    el texto.
-   Ajustar, opcionalmente, la distancia máxima para considerar que dos
    resultados coinciden.
-   Descargar un CSV de ejemplo para conocer la estructura esperada.

### 2. Validar

Para cada dirección, la aplicación muestra los candidatos disponibles en
un mapa:

-   **Azul:** resultado de Nominatim.
-   **Naranja:** resultado de Photon.
-   **Verde:** ubicación final validada.

La persona usuaria puede elegir uno de los resultados disponibles o
hacer clic directamente en el mapa para proponer una coordenada manual.
También puede volver a dejar una dirección como pendiente.

La interfaz permite filtrar el listado para ver todos los registros,
solo pendientes o solo validados.

### 3. Mapa validado

Permite visualizar en conjunto los puntos aprobados. Los registros
pendientes o sin coordenadas quedan fuera de este mapa.

### 4. Descargar

Antes de descargar, se presenta una vista previa del archivo final. Se
ofrecen dos formatos:

-   **CSV:** práctico para importar datos en otras herramientas,
    incluido Google My Maps.
-   **Excel (.xlsx):** conserva las coordenadas como valores numéricos y
    agrega filtros, encabezado destacado y fila superior congelada.

------------------------------------------------------------------------

## Funcionalidades

  -----------------------------------------------------------------------
  Área                                Funcionalidad
  ----------------------------------- -----------------------------------
  Entrada                             Carga de CSV y detección inicial de
                                      la columna de direcciones

  Ejemplo                             Descarga de un archivo CSV de
                                      muestra

  Geocodificación                     Consulta de Nominatim y Photon

  Comparación                         Cálculo de distancia geográfica
                                      entre las dos respuestas

  Clasificación                       Coincidencia, discrepancia, fuente
                                      única, dirección vacía o error de
                                      consulta

  Revisión                            Mapa por dirección, elección de
                                      fuente y selección de punto manual

  Seguimiento                         Estados de validación y metadatos
                                      del proceso

  Exploración                         Filtro de todos, pendientes y
                                      validados

  Vista general                       Mapa conjunto de ubicaciones
                                      validadas

  Exportación                         CSV y Excel con columnas originales
                                      y coordenadas finales

  Interfaz                            Flujo dividido en pestañas y guía
                                      breve de uso
  -----------------------------------------------------------------------

## Criterios de validación

La aplicación calcula la distancia entre las coordenadas de Nominatim y
Photon usando la fórmula de Haversine.

El umbral de coincidencia se puede configurar entre **25 y 1.000
metros**, con un valor predeterminado de **100 metros**.

Comportamiento general:

-   **Ambas fuentes devuelven coordenadas dentro del umbral:** el
    registro se preselecciona como coincidencia, pero se recomienda
    revisar la altura o número de puerta cuando sea importante.
-   **Ambas fuentes devuelven puntos separados por más del umbral:** se
    marca como discrepancia y queda pendiente de revisión.
-   **Solo una fuente devuelve coordenadas:** se conserva el candidato
    disponible, pero requiere validación.
-   **Ninguna fuente devuelve coordenadas:** el registro queda sin
    ubicación y no se exporta como validado.
-   **Dirección vacía o error de consulta:** se informa mediante su
    estado correspondiente.

La revisión manual permite corregir las decisiones automáticas antes de
la exportación.

> **Importante:** dos proveedores pueden coincidir y aun así devolver
> una ubicación aproximada. Para casos que requieren precisión de
> puerta, entrega, logística o cumplimiento, se debe verificar el punto
> contra una fuente confiable adicional.

## Tecnologías

-   **Python:** lógica de la aplicación y procesamiento de datos.
-   **Streamlit:** interfaz web y flujo de interacción.
-   **Pandas:** lectura, transformación y preparación de tablas.
-   **Requests:** consultas HTTP a los servicios de geocodificación.
-   **Nominatim / OpenStreetMap:** primera fuente de geocodificación.
-   **Photon:** segunda fuente de geocodificación.
-   **Folium:** construcción de mapas interactivos.
-   **streamlit-folium:** integración de mapas Folium en Streamlit.
-   **OpenPyXL:** generación y formato de archivos Excel.

No requiere una base de datos propia para el flujo de uso básico. El
resultado de trabajo se conserva en el estado de sesión de Streamlit
durante la interacción; por lo tanto, conviene descargar los resultados
antes de reiniciar o perder la sesión.

## Estructura del proyecto

``` text
mis-lugares/
├── app.py
├── requirements.txt
└── README.md
```

### `app.py`

Contiene la interfaz, las llamadas a las fuentes, la comparación de
coordenadas, la lógica de validación, los mapas y la exportación.

### `requirements.txt`

Declara las dependencias necesarias para ejecutar la aplicación:

``` text
streamlit
pandas
requests
folium
streamlit-folium
openpyxl
```

## Instalación local

Se recomienda Python 3.10 o superior.

1.  Clonar o descargar el repositorio.
2.  Crear un entorno virtual.
3.  Instalar las dependencias.
4.  Ejecutar Streamlit.

``` bash
git clone <URL_DEL_REPOSITORIO>
cd mis-lugares

python -m venv .venv
```

Activar el entorno virtual:

**Windows (PowerShell):**

``` powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

``` bash
source .venv/bin/activate
```

Instalar y ejecutar:

``` bash
pip install -r requirements.txt
streamlit run app.py
```

Streamlit mostrará la URL local de la aplicación en la terminal,
habitualmente `http://localhost:8501`.

## Despliegue en Streamlit Community Cloud

1.  Subir `app.py`, `requirements.txt` y `README.md` a un repositorio de
    GitHub.
2.  Ingresar a Streamlit Community Cloud.
3.  Crear una aplicación nueva y seleccionar el repositorio, la rama y
    `app.py`.
4.  Esperar la instalación de dependencias y el inicio de la aplicación.
5.  Probar el flujo completo con el CSV de ejemplo antes de usar
    archivos reales.

El despliegue depende de la disponibilidad del servicio de hosting y de
los servicios externos de geocodificación. La aplicación no incluye
credenciales privadas ni necesita una API key para el flujo
implementado.

## Formato de entrada

La entrada es un archivo **CSV** con una fila por registro y una columna
que contenga la dirección a buscar.

La aplicación intenta detectar automáticamente columnas con nombres
como:

-   `direccion`
-   `dirección`
-   `address`
-   `domicilio`

Si no encuentra ninguna de ellas, propone la primera columna del
archivo; la persona usuaria puede seleccionar otra.

Ejemplo:

``` csv
direccion,referencia
"Obelisco, Avenida 9 de Julio, Buenos Aires, Argentina",Ejemplo 1
"Casa Rosada, Balcarce 50, Buenos Aires, Argentina",Ejemplo 2
"Congreso de la Nación, Avenida Entre Ríos 51, Buenos Aires, Argentina",Ejemplo 3
```

Se intenta leer el archivo con codificaciones UTF-8 y Latin-1. Para
obtener resultados consistentes, conviene incluir ciudad, región y país
en cada dirección cuando esos datos estén disponibles.

### País y alcance actual

Aunque la interfaz permite escribir un país para completar las
consultas, la implementación actual restringe las búsquedas de Nominatim
a Argentina mediante el parámetro `countrycodes=ar`. Photon no recibe
esa misma restricción por código. Por eso, **la versión actual debe
considerarse orientada a direcciones de Argentina**; el campo de país no
constituye todavía una configuración multi-país completa.

## Formato de salida

La exportación conserva todas las columnas originales del CSV y agrega:

  Campo                     Descripción
  ------------------------- -------------------------------------
  `Latitude`                Latitud final validada
  `Longitude`               Longitud final validada
  `fecha_geocodificacion`   Fecha y hora local del proceso
  `id_proceso`              Identificador único de la ejecución

Solo se exportan registros que cumplen ambas condiciones:

-   Tienen estado de validación aprobado.
-   Tienen latitud y longitud disponibles.

Las coordenadas internas de cada proveedor se usan para comparar y
revisar, pero no se incluyen en el archivo final.

### Uso con Google My Maps

1.  Crear un mapa en Google My Maps.
2.  Elegir **Importar** y subir el CSV validado.
3.  Seleccionar `Latitude` y `Longitude` como campos de ubicación.
4.  Seleccionar `Name` como título si se necesita un rótulo por punto.

La aplicación exporta las columnas originales, pero no agrega
obligatoriamente una columna `Name` si esa columna no existe en el
archivo de entrada. Si se quiere usar `Name` como título, se recomienda
incluir esa columna en el CSV original o adaptar el archivo antes de
importarlo.

## Limitaciones y consideraciones

-   La geocodificación es una estimación basada en los datos disponibles
    en cada proveedor; no garantiza precisión a nivel de puerta.
-   Los servicios gratuitos tienen límites de uso y políticas propias.
    Nominatim requiere uso responsable y la aplicación introduce una
    pausa entre consultas.
-   Procesar listas grandes puede llevar varios minutos. Evitar ejecutar
    múltiples procesos simultáneos o enviar grandes volúmenes de
    consultas sin revisar las políticas vigentes de cada servicio.
-   Los errores temporales de red o las limitaciones de un proveedor
    pueden producir resultados incompletos.
-   El sistema compara dos respuestas, pero no calcula una probabilidad
    estadística de que una coordenada sea correcta.
-   El país está restringido a Argentina para Nominatim en esta versión.
-   Los resultados viven en el estado de la sesión de Streamlit; no hay
    almacenamiento persistente ni historial de ejecuciones en una base
    de datos.
-   La app requiere acceso a internet para consultar los proveedores y
    cargar las teselas del mapa.
-   El comportamiento debe probarse en el entorno de despliegue elegido,
    especialmente después de actualizar dependencias o modificar la
    interfaz.

## Privacidad y uso responsable

Las direcciones ingresadas se envían a los servicios externos de
geocodificación para poder resolver sus coordenadas. No se debe cargar
información sensible, confidencial o personal sin contar con la
autorización correspondiente y sin revisar las políticas aplicables.

El campo de contacto es opcional y se utiliza para añadir un
identificador al `User-Agent` de las consultas a Nominatim. No convierte
la aplicación en un servicio privado ni implica un acuerdo de nivel de
servicio con el proveedor.

Antes de utilizar la herramienta con información de clientes, se
recomienda validar los requisitos internos de privacidad, seguridad y
tratamiento de datos.

## Decisiones de producto y diseño

El producto prioriza simplicidad y control por encima de la
automatización total:

-   **Dos fuentes en lugar de una:** permite comparar candidatos y
    detectar discrepancias.
-   **Validación humana:** evita tratar una respuesta geográfica como
    verdad absoluta.
-   **Flujo por pestañas:** separa carga, revisión, mapa general y
    descarga.
-   **Exportación limpia:** el archivo final contiene las columnas
    originales, coordenadas elegidas y metadatos mínimos de
    trazabilidad.
-   **Stack accesible:** utiliza bibliotecas habituales de Python y
    servicios gratuitos, evitando infraestructura compleja.
-   **Diseño sobrio:** interfaz clara, con una paleta azul y celeste,
    jerarquía visual simple y sin elementos decorativos innecesarios.

## Caso de éxito: valor generado

Mis lugares muestra cómo una necesidad operativa acotada puede
convertirse en una herramienta reutilizable con una arquitectura
liviana.

### Antes

-   Direcciones en una planilla sin coordenadas confiables.
-   Resultados dependientes de una única fuente o procesos manuales.
-   Dificultad para comparar alternativas y detectar inconsistencias.
-   Necesidad de preparar el archivo final por separado.

### Después

-   Un flujo guiado desde el CSV de entrada hasta el archivo final.
-   Comparación espacial de dos proveedores.
-   Revisión visual de candidatos y selección manual de coordenadas.
-   Exportación consistente en formatos habituales.
-   Una aplicación que puede reutilizarse con distintos archivos sin
    desarrollar un proceso desde cero cada vez.

### Qué demuestra el proyecto

-   **Orientación a producto:** se resuelve el flujo completo, no solo
    una consulta aislada.
-   **Pensamiento analítico:** se explicitan las limitaciones de los
    datos y se comparan fuentes.
-   **Automatización con criterio:** se automatiza el trabajo repetitivo
    sin eliminar la revisión humana donde aporta valor.
-   **Pragmatismo tecnológico:** se combinan componentes conocidos y de
    bajo costo para entregar una solución funcional.
-   **Reusabilidad:** el usuario puede procesar distintos archivos con
    la misma herramienta.

No se publican cifras de ahorro de tiempo, precisión o volumen procesado
porque no hay mediciones comparativas documentadas. Para convertirlo en
un caso cuantificado, se recomienda registrar el tiempo medio del
proceso manual y del proceso asistido, el porcentaje de direcciones
encontradas, el porcentaje aprobado sin corrección, el porcentaje
corregido manualmente y el costo por ejecución.

## Próximas mejoras posibles

1.  **Selector real de país:** aplicar el país seleccionado tanto a
    Nominatim como a Photon y retirar la restricción fija a Argentina.
2.  **Reintentos y tratamiento de errores:** distinguir errores
    temporales, límites de uso y direcciones sin resultados.
3.  **Caché persistente opcional:** evitar repetir consultas para
    direcciones ya procesadas, con controles adecuados de privacidad y
    políticas del proveedor.
4.  **Historial de procesos:** guardar archivos y decisiones cuando
    exista una necesidad real de trazabilidad persistente.
5.  **Métricas de calidad:** reportar tasas de coincidencia,
    discrepancia, resultados únicos y correcciones manuales.
6.  **Pruebas automatizadas:** cubrir lectura de CSV, cálculo de
    distancia, reglas de estado y formato de exportación.
7.  **Validación de precisión por muestreo:** comparar una muestra de
    resultados contra direcciones verificadas, especialmente para
    números de puerta.
8.  **Soporte para otros formatos de entrada:** agregar Excel u otros
    formatos solo si el uso real lo requiere.

## Licencia

No se ha definido una licencia de distribución en este repositorio.
Antes de publicarlo o reutilizarlo fuera de un entorno personal o
interno, definir una licencia para el código y revisar las condiciones
de uso de los servicios externos.
