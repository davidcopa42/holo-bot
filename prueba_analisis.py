"""
Prueba aislada del análisis de reseñas de HOLO.
Consulta a Gemini sin pasar por Telegram.
"""

import asyncio
import os

from dotenv import load_dotenv
from google import genai

from analisis import analizar_resena


load_dotenv()

cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
modelo = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


async def main():
    resenas = [
        "Los stickers son hermosos, tienen muy buena calidad y los colores son excelentes. Me encantaron.",

        "La agenda quedó preciosa y la personalización fue excelente, pero tardaron varios días más de lo acordado.",

        "Muy caro para lo que recibí. La impresión tiene poca calidad y la atención no fue buena.",
    ]

    for texto in resenas:
        print("\nReseña original:", texto)

        analisis = await analizar_resena(cliente, modelo, texto)

        print("Sentimiento:", analisis.sentimiento)
        print("Puntaje:", analisis.puntaje)
        print("Aspectos:", analisis.aspectos)
        print("Resumen:", analisis.resumen)


asyncio.run(main())
