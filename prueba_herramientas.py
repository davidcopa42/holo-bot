"""
Prueba aislada de las herramientas, consulta Supabase sin Telegram ni Gemini.
Llama a cada función directamente y muestra lo que devuelve.
"""

import asyncio  # permite ejecutar corrutinas desde un script
import json  # para mostrar los resultados con formato legible

from herramientas import (
    buscar_productos,
    obtener_producto,
    listar_categorias,
    consultar_precio,
    ejecutar_funcion
)


def mostrar_resultado(titulo: str, resultado: dict):
    print("\n" + "=" * 60)
    print(titulo)
    print("=" * 60)

    print(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2
        )
    )


async def main():

    # -------------------------------------------------------
    # 1. Buscar productos por nombre
    # -------------------------------------------------------

    resultado = await buscar_productos("Sticker")

    mostrar_resultado(
        "PRUEBA 1: BUSCAR PRODUCTOS",
        resultado
    )

    # -------------------------------------------------------
    # 2. Buscar productos por nombre y categoría
    # -------------------------------------------------------

    resultado = await buscar_productos(
        "Sticker",
        "Stickers"
    )

    mostrar_resultado(
        "PRUEBA 2: BUSCAR POR CATEGORÍA",
        resultado
    )

    # -------------------------------------------------------
    # 3. Obtener información detallada de un producto
    # -------------------------------------------------------

    resultado = await obtener_producto("Sticker 9z #1")

    mostrar_resultado(
        "PRUEBA 3: OBTENER PRODUCTO",
        resultado
    )

    # -------------------------------------------------------
    # 4. Listar categorías y subcategorías
    # -------------------------------------------------------

    resultado = await listar_categorias()

    mostrar_resultado(
        "PRUEBA 4: LISTAR CATEGORÍAS",
        resultado
    )

    # -------------------------------------------------------
    # 5. Consultar precios por ID de producto
    # -------------------------------------------------------

    resultado = await consultar_precio(10)

    mostrar_resultado(
        "PRUEBA 5: CONSULTAR PRECIO",
        resultado
    )

    # -------------------------------------------------------
    # 6. Probar el despachador
    # -------------------------------------------------------

    resultado = await ejecutar_funcion(
        "buscar_productos",
        {"termino": "Sticker"}
    )

    mostrar_resultado(
        "PRUEBA 6: EJECUTAR FUNCIÓN MEDIANTE DESPACHADOR",
        resultado
    )

    # -------------------------------------------------------
    # 7. Probar una función inexistente
    # -------------------------------------------------------

    resultado = await ejecutar_funcion(
        "funcion_inexistente",
        {}
    )

    mostrar_resultado(
        "PRUEBA 7: FUNCIÓN INEXISTENTE",
        resultado
    )


if __name__ == "__main__":
    asyncio.run(main())
