"""
Análisis de reseñas de clientes de HOLO con salida estructurada.

Gemini analiza las opiniones de los clientes y devuelve un JSON
que cumple un esquema definido con Pydantic. Así el programa puede
guardar, contar y promediar los resultados sin interpretar texto.

"""

from typing import Literal # restringe un campo a un conjunto fijo de valores
from pydantic import BaseModel, Field # definición y validación de estructuras de datos


class AnalisisResena(BaseModel):
    """Estructura que debe tener el análisis de una reseña."""

    # Literal: el modelo solo puede responder uno de estos tres valores.
    sentimiento: Literal["positivo", "neutral", "negativo"] = Field(
        description="Sentimiento general del cliente sobre su experiencia con HOLO."
    )

    puntaje: int = Field(
        ge=1,
        le=5,
        description="Satisfacción estimada del cliente, de 1 (muy mala) a 5 (excelente)."
    )

    aspectos: list[str] = Field(
        description=(
            "Aspectos mencionados en la reseña, en una o dos palabras. "
            "Ejemplos: calidad, diseño, precio, atención, entrega, packaging."
        )
    )

    resumen: str = Field(
        description="Resumen de la opinión del cliente en una sola oración breve."
    )


# Instrucciones específicas para analizar opiniones de clientes de HOLO.
# Son distintas del prompt de sistema de la conversación: aquí el modelo no conversa, solo clasifica.
PROMPT_ANALISIS = """
Analizás opiniones y reseñas de clientes sobre HOLO, un emprendimiento
de Mendoza, Argentina, dedicado a la venta de stickers, agendas, remeras
y otros productos personalizados.

Tu tarea es identificar:
- El sentimiento general del cliente.
- Su nivel de satisfacción.
- Los aspectos concretos que menciona.
- Un resumen breve de su experiencia.

Tené en cuenta aspectos como:
calidad, diseño, personalización, precio, atención al cliente,
tiempo de preparación, entrega y packaging.

Respondé únicamente con el análisis solicitado, en español.

Si la reseña mezcla elogios y críticas, clasificá el sentimiento como
neutral, salvo que uno de los dos predomine claramente.

No inventes aspectos que el cliente no haya mencionado.
El puntaje debe reflejar la satisfacción general expresada en la reseña.
""".strip()


async def analizar_resena(cliente, modelo: str, texto: str) -> AnalisisResena:
    """Envía la reseña a Gemini y devuelve el análisis validado."""

    interaccion = await cliente.aio.interactions.create(
        model=modelo,
        system_instruction=PROMPT_ANALISIS,
        input=texto,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": AnalisisResena.model_json_schema(),
        },
        store=False,
    )

    # Convierte el JSON recibido en un objeto Pydantic y valida sus campos.
    return AnalisisResena.model_validate_json(interaccion.output_text)
