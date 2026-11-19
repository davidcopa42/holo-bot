"""
Prueba de conexión y lectura de Supabase.
No utiliza Telegram ni Gemini.
"""

import os
from dotenv import load_dotenv
from supabase import create_client


# ---------------------------------------------------------------------------
# 1. Conexión
# ---------------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Faltan las credenciales de Supabase en el archivo .env"
    )

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

print("\nConexión con Supabase configurada correctamente.")


# ---------------------------------------------------------------------------
# 2. Prueba de lectura de tablas
# ---------------------------------------------------------------------------

TABLAS = [
    "productos",
    "categorias",
    "subcategorias",
    "variantesProducto",
    "catalogoProductos",
    "bannersHero"
]


def probar_tabla(nombre_tabla):

    print(f"\n{'=' * 50}")
    print(f"CONSULTANDO: {nombre_tabla}")
    print("=" * 50)

    try:
        respuesta = (
            supabase
            .table(nombre_tabla)
            .select("*")
            .limit(3)
            .execute()
        )

        registros = respuesta.data

        print(f"Registros encontrados: {len(registros)}")

        if registros:
            for indice, registro in enumerate(registros, start=1):
                print(f"\nRegistro {indice}:")
                print(registro)
        else:
            print("La consulta funcionó, pero no devolvió registros.")

    except Exception as error:
        print(f"ERROR al consultar {nombre_tabla}:")
        print(type(error).__name__)
        print(error)

def probar_relaciones():

    print("\n" + "=" * 50)
    print("CONSULTA DE PRODUCTOS CON RELACIONES")
    print("=" * 50)

    respuesta = (
        supabase
        .table("productos")
        .select("""
            id,
            nombreProducto,
            descripcion,
            categorias (
                id,
                nombreCategoria
            ),
            subcategorias (
                id,
                nombreSubcategoria
            ),
            variantesProducto (
                id,
                nombreVariante,
                precioUnitario,
                urlImagen
            )
        """)
        .limit(10)
        .execute()
    )

    for producto in respuesta.data:
        print("\nPRODUCTO:")
        print(producto)

# ---------------------------------------------------------------------------
# 3. Ejecutar todas las pruebas
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    for tabla in TABLAS:
        probar_tabla(tabla)
    probar_relaciones()
    print("\nPruebas finalizadas.")
