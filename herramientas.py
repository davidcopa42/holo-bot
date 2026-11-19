
"""
Herramientas de HOLO: funciones que Gemini puede pedir que se ejecuten.

El módulo tiene cuatro partes:
1. Configuración y conexión con Supabase.
2. Funciones que consultan el catálogo.
3. Declaraciones: descripción de las funciones para Gemini.
4. Despachador que ejecuta la función solicitada por el modelo.
"""

import asyncio
import logging
import os
import unicodedata

from dotenv import load_dotenv
from supabase import create_client


logger = logging.getLogger("holo")


# ---------------------------------------------------------------------------
# 1. Configuración y datos auxiliares
# ---------------------------------------------------------------------------

# Carga las variables del archivo .env.
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Faltan SUPABASE_URL o SUPABASE_KEY en el archivo .env"
    )

# Cliente reutilizable durante toda la ejecución del bot.
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cantidad máxima de productos devueltos en una búsqueda.
MAX_PRODUCTOS = 10

# Cantidad máxima de coincidencias al consultar un producto específico.
MAX_RESULTADOS_PRODUCTO = 5


def _normalizar(texto: str) -> str:
    """
    Pasa el texto a minúsculas y elimina las tildes.

    Ejemplo:
    'Agendas' y 'AGENdas' quedan iguales.
    'Holográficos' y 'holograficos' quedan iguales.
    """

    sin_tildes = unicodedata.normalize("NFD", texto)

    return "".join(
        caracter
        for caracter in sin_tildes
        if unicodedata.category(caracter) != "Mn"
    ).lower().strip()


def _preparar_resultado(datos: list) -> list:
    """
    Evita devolver None cuando una consulta no encuentra registros.
    """

    return datos or []


# ---------------------------------------------------------------------------
# 2. Funciones de consulta
# ---------------------------------------------------------------------------

def _buscar_id_categoria(nombre_categoria: str):
    """
    Busca el ID de una categoría comparando su nombre
    sin distinguir mayúsculas ni tildes.

    Esta función es interna y síncrona.
    """

    respuesta = (
        supabase
        .table("categorias")
        .select("id, nombreCategoria")
        .execute()
    )

    categorias = _preparar_resultado(respuesta.data)

    nombre_normalizado = _normalizar(nombre_categoria)

    for categoria in categorias:
        if _normalizar(categoria["nombreCategoria"]) == nombre_normalizado:
            return categoria["id"]

    return None


def _consultar_productos(termino, limite, id_categoria=None):
    consulta = supabase.table("productos").select("""
        id,
        nombreProducto,
        descripcion,
        categorias(id,nombreCategoria),
        subcategorias(id,nombreSubcategoria),
        variantesProducto(id,nombreVariante,precioUnitario,urlImagen)
    """)

    # Si hay un término, filtra por nombre.
    if termino and termino.strip():
        consulta = consulta.ilike(
            "nombreProducto",
            f"%{termino.strip()}%"
        )

    # Si hay una categoría, filtra por su ID.
    if id_categoria is not None:
        consulta = consulta.eq("idCategoria", id_categoria)

    respuesta = consulta.limit(limite).execute()
    return respuesta.data or []


async def buscar_productos(
    termino: str,
    categoria: str = None
) -> dict:
    """
    Busca productos por nombre y opcionalmente por categoría.

    Ejemplos:
    - buscar_productos("sticker")
    - buscar_productos("agenda")
    - buscar_productos("remera", "Remeras")
    """

    if not termino or not termino.strip():
        return {
            "error": "Tenés que indicar qué producto estás buscando."
        }

    try:
        id_categoria = None

        if categoria:
            id_categoria = await asyncio.to_thread(
                _buscar_id_categoria,
                categoria
            )

            if id_categoria is None:
                return {
                    "error": f"No encontré la categoría '{categoria}'.",
                    "categorias_disponibles": await listar_categorias()
                }

        termino_busqueda = termino

        # Si el término coincide con la categoría,
        # buscamos todos los productos de esa categoría.
        if (
            categoria
            and _normalizar(termino).rstrip("s")
            == _normalizar(categoria).rstrip("s")
        ):
            termino_busqueda = None

        productos = await asyncio.to_thread(
            _consultar_productos,
            termino_busqueda,
            MAX_PRODUCTOS,
            id_categoria
        )        

        
        if not productos:
            return {
                "cantidad": 0,
                "mensaje": (
                    f"No encontré productos que coincidan con '{termino}'."
                )
            }

        return {
            "cantidad": len(productos),
            "productos": productos
        }

    except Exception as error:
        logger.exception("Error al buscar productos")

        return {
            "error": f"No se pudieron buscar los productos: {type(error).__name__}"
        }


async def obtener_producto(nombre: str) -> dict:
    """
    Obtiene información detallada de uno o varios productos.

    Devuelve:
    - Nombre y descripción.
    - Categoría y subcategoría.
    - Variantes.
    - Precios.
    - Imágenes.
    """

    if not nombre or not nombre.strip():
        return {
            "error": "Tenés que indicar el nombre del producto."
        }

    try:
        productos = await asyncio.to_thread(
            _consultar_productos,
            nombre,
            MAX_RESULTADOS_PRODUCTO
        )

        if not productos:
            return {
                "cantidad": 0,
                "mensaje": (
                    f"No encontré productos que coincidan con '{nombre}'."
                )
            }

        return {
            "cantidad": len(productos),
            "productos": productos
        }

    except Exception as error:
        logger.exception("Error al obtener producto")

        return {
            "error": f"No se pudo obtener el producto: {type(error).__name__}"
        }


def _consultar_categorias() -> list:
    """
    Consulta las categorías y sus subcategorías.

    Esta función es interna y síncrona.
    """

    respuesta = (
        supabase
        .table("categorias")
        .select("""
            id,
            nombreCategoria,
            subcategorias(
                id,
                nombreSubcategoria
            )
        """)
        .order("nombreCategoria", desc=False)
        .execute()
    )

    return _preparar_resultado(respuesta.data)


async def listar_categorias() -> dict:
    """
    Devuelve todas las categorías y sus subcategorías.
    """

    try:
        categorias = await asyncio.to_thread(
            _consultar_categorias
        )

        return {
            "cantidad": len(categorias),
            "categorias": categorias
        }

    except Exception as error:
        logger.exception("Error al listar categorías")

        return {
            "error": f"No se pudieron obtener las categorías: {type(error).__name__}"
        }


def _consultar_variantes(id_producto: int) -> list:
    """
    Consulta las variantes y sus precios para un producto.

    Esta función es interna y síncrona.
    """

    respuesta = (
        supabase
        .table("variantesProducto")
        .select("""
            id,
            idProducto,
            nombreVariante,
            precioUnitario
        """)
        .eq("idProducto", id_producto)
        .execute()
    )

    return _preparar_resultado(respuesta.data)


async def consultar_precio(id_producto: int) -> dict:
    """
    Consulta los precios de todas las variantes de un producto.

    Recibe el ID del producto, no el ID de la variante.
    """

    try:
        if id_producto <= 0:
            return {
                "error": "El identificador del producto debe ser positivo."
            }

        variantes = await asyncio.to_thread(
            _consultar_variantes,
            id_producto
        )

        if not variantes:
            return {
                "id_producto": id_producto,
                "mensaje": "No encontré variantes para ese producto."
            }

        return {
            "id_producto": id_producto,
            "variantes": variantes
        }

    except Exception as error:
        logger.exception("Error al consultar precios")

        return {
            "error": f"No se pudieron consultar los precios: {type(error).__name__}"
        }


# ---------------------------------------------------------------------------
# 3. Declaraciones para Gemini
# ---------------------------------------------------------------------------

# Esto es lo que Gemini conoce de las funciones.
# Las descripciones indican qué hace cada herramienta y cuándo utilizarla.

DECLARACIONES = [

    {
        "type": "function",
        "name": "buscar_productos",
        "description": (
            "Busca productos en el catálogo de HOLO por nombre "
            "y opcionalmente por categoría. Usala cuando el usuario "
            "quiera encontrar productos o explorar el catálogo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "termino": {
                    "type": "string",
                    "description": "Nombre o palabra clave del producto."
                },
                "categoria": {
                    "type": "string",
                    "description": (
                        "Nombre de la categoría, si el usuario la especifica. "
                        "Por ejemplo: Stickers, Agendas o Remeras."
                    )
                }
            },
            "required": ["termino"]
        }
    },

    {
        "type": "function",
        "name": "obtener_producto",
        "description": (
            "Obtiene información detallada de uno o varios productos "
            "de HOLO, incluyendo descripción, categoría, subcategoría, "
            "variantes, precios e imágenes. Usala cuando el usuario "
            "pregunte por un producto específico."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre o parte del nombre del producto."
                }
            },
            "required": ["nombre"]
        }
    },

    {
        "type": "function",
        "name": "listar_categorias",
        "description": (
            "Obtiene las categorías y subcategorías disponibles "
            "en el catálogo de HOLO. Usala cuando el usuario quiera "
            "saber qué tipos de productos ofrece la tienda."
        ),
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },

    {
        "type": "function",
        "name": "consultar_precio",
        "description": (
            "Consulta los precios actuales de todas las variantes "
            "de un producto de HOLO. Usala cuando el usuario pregunte "
            "cuánto cuesta un producto. Necesitás el ID del producto, "
            "que podés obtener previamente con obtener_producto "
            "o buscar_productos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id_producto": {
                    "type": "integer",
                    "description": "Identificador del producto."
                }
            },
            "required": ["id_producto"]
        }
    }

]


# ---------------------------------------------------------------------------
# 4. Despachador
# ---------------------------------------------------------------------------

# Relaciona el nombre de la herramienta con su función de Python.
FUNCIONES = {
    "buscar_productos": buscar_productos,
    "obtener_producto": obtener_producto,
    "listar_categorias": listar_categorias,
    "consultar_precio": consultar_precio,
}


async def ejecutar_funcion(nombre: str, argumentos: dict) -> dict:
    """
    Ejecuta la función solicitada por Gemini y devuelve siempre
    un diccionario con el resultado o el error.
    """

    logger.info(
        "El modelo pidió %s(%s)",
        nombre,
        argumentos
    )

    funcion = FUNCIONES.get(nombre)

    if funcion is None:
        return {
            "error": f"Función desconocida: {nombre}"
        }

    try:
        return await funcion(**(argumentos or {}))

    except Exception as error:
        # Cualquier error se devuelve como dato para que Gemini
        # pueda explicárselo al usuario sin interrumpir el bot.
        logger.exception("Falló la herramienta %s", nombre)

        return {
            "error": f"No se pudo obtener el dato: {type(error).__name__}"
        }
