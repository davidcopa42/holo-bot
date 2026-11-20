import json # convierte los resultados de las funciones a texto JSON
import logging # registro de eventos en la terminal
import os # acceso a las variables de entorno
from dotenv import load_dotenv # lee el archivo .env
from google import genai # SDK oficial de Gemini
from telegram import Update # representa cada novedad recibida de Telegram
from telegram.constants import ChatAction # acciones de chat, como "escribiendo..."
from telegram.ext import (
    Application, # motor del bot: recibe y distribuye updates
    CommandHandler, # handler para comandos (/start, /help)
    ContextTypes, # tipo del parámetro context de los handlers
    MessageHandler, # handler para mensajes que no son comandos
    filters, # filtros para seleccionar qué mensajes atender
)
import db # módulo propio: acceso a la base SQLite
from herramientas import DECLARACIONES, ejecutar_funcion # funciones propias del bot
from prompts import PROMPT_SISTEMA # prompt de sistema definido en prompts.py

# Carga en el entorno las variables del archivo .env.
load_dotenv()
# Lectura de las variables. os.getenv devuelve None si la variable no existe.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Cantidad de mensajes anteriores que se envían al modelo en cada consulta
# (20 mensajes = 10 preguntas y sus respuestas). Un valor mayor da más memoria,
# pero cada consulta resulta más lenta y consume más cuota.
MAX_MENSAJES_HISTORIAL = 20
# Cantidad máxima de vueltas del ciclo de function calling en un mismo mensaje.
# Evita un bucle infinito si el modelo pidiera funciones una y otra vez.
MAX_VUELTAS_HERRAMIENTAS = 5
# El segundo argumento es el valor por defecto si GEMINI_MODEL no está en el .env.
# Leer el modelo del .env permite cambiarlo sin modificar el código.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Formato de cada línea de registro: fecha y hora | nivel | origen | mensaje.
logging.basicConfig(
format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
level=logging.INFO, # se muestran INFO, WARNING, ERROR y CRITICAL
)
# httpx registra cada consulta HTTP; se limita a advertencias para no saturar la consola.
logging.getLogger("httpx").setLevel(logging.WARNING)
# Registrador propio del bot; sus mensajes aparecen con el nombre "holo".
logger = logging.getLogger("holo")
# Longitud máxima de un mensaje de Telegram, en caracteres.
LIMITE_TELEGRAM = 4096

# Se crea un único cliente para todo el programa. El cliente guarda la clave
# de API y administra las conexiones HTTP con los servidores de Google.
# Crearlo una sola vez evita abrir una conexión nueva en cada mensaje.
cliente_gemini = genai.Client(api_key=GEMINI_API_KEY)

def armar_entrada(historial: list[tuple[str, str]], mensaje_nuevo: str) -> list[dict]:
    """
    Convierte el historial guardado en la lista de pasos (steps) que espera
    la Interactions API y agrega al final el mensaje nuevo del usuario.
    """
    # Equivalencia entre el rol guardado en la base y el tipo de paso de la API.
    tipo_de_paso = {"user": "user_input", "model": "model_output"}

    # Lista por comprensión: un diccionario por cada fila del historial.
    # Cada paso indica su tipo y su contenido, que es una lista de bloques;
    # aquí, un único bloque de texto.
    pasos = [
        {"type": tipo_de_paso[rol], "content": [{"type": "text", "text": texto}]}
        for rol, texto in historial
    ]

    # El último paso es siempre el mensaje que el usuario acaba de enviar.
    pasos.append({"type": "user_input", "content": [{"type": "text", "text": mensaje_nuevo}]})

    return pasos


async def consultar_gemini(historial: list[tuple[str, str]], mensaje: str) -> str:
    """
    Envía la conversación a Gemini y resuelve el ciclo de function calling:
    mientras el modelo pida funciones, se ejecutan y se le devuelven los
    resultados; cuando responde con texto, se devuelve ese texto.
    """

    # Lista de pasos que se envía al modelo. Empieza con el historial y el
    # mensaje nuevo, y crece dentro de este turno con los pedidos de funciones
    # y sus resultados. Esos pasos intermedios no se guardan en la base.
    entrada = armar_entrada(historial, mensaje)

    for vuelta in range(MAX_VUELTAS_HERRAMIENTAS):
        interaccion = await cliente_gemini.aio.interactions.create(
            model=GEMINI_MODEL,
            system_instruction=PROMPT_SISTEMA,
            input=entrada,
            tools=DECLARACIONES,  # funciones que el modelo puede pedir
            store=False,
        )

        # Pasos de tipo function_call: el modelo pide ejecutar una función.
        # Puede pedir más de una en la misma respuesta (por ejemplo, clima y dólar).
        llamadas = [
            paso for paso in interaccion.steps if paso.type ==
            "function_call"
        ]

        if not llamadas:
            # Sin pedidos de funciones: el modelo ya redactó la respuesta final.
            return interaccion.output_text or "No se me ocurrió nada para responder 🤔"

        # Se agregan a la entrada TODOS los pasos que devolvió el modelo, sin
        # modificarlos (incluidos los de razonamiento interno). La API los
        # necesita para relacionar cada resultado con su pedido.
        for paso in interaccion.steps:
            entrada.append(paso.model_dump())

        # Se ejecuta cada función pedida y se agrega su resultado como un paso
        # function_result. call_id debe coincidir con el id del pedido.
        for llamada in llamadas:
            resultado = await ejecutar_funcion(llamada.name, llamada.arguments)

            entrada.append({
                "type": "function_result",
                "call_id": llamada.id,
                "name": llamada.name,
                # ensure_ascii=False conserva tildes y ñ en lugar de códigos ñ
                "result": [{"type": "text", "text": json.dumps(resultado,
                ensure_ascii=False)}],
            })

        # Se repite el ciclo: el modelo recibe los resultados y decide si
        # necesita otra función o si ya puede responder.
        # Se agotaron las vueltas sin respuesta final.

    logger.warning("Se alcanzó el máximo de %d vueltas de herramientas",
    MAX_VUELTAS_HERRAMIENTAS)

    return "No pude completar la consulta. ¿Podés reformular la pregunta? 🤔"


def describir_error(error: Exception) -> str:
    """Traduce un error de la API a un mensaje comprensible para el usuario."""
# Los errores HTTP de la API traen el código en el atributo status_code.
# getattr devuelve None si el error no tiene ese atributo (por ejemplo,
# una falla de red sin respuesta del servidor).
    codigo = getattr(error, "status_code", None)
    if codigo == 429: # 429: se superó la cuota de consultas
        return "Estoy recibiendo demasiadas consultas. Probá de nuevo en un minuto, por favor. ⏳"
    if codigo in (401, 403): # 401/403: clave inválida o sin permiso
        return "Tengo un problema de configuración. Avisale a quien me administra. 🔧"
    # Cualquier otro caso: falla de red, error del servicio, modelo inexistente.
    return "Tuve un problema para pensar la respuesta. ¿Me lo preguntás de nuevo? 🙏"

#Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde al comando /start."""
    nombre = update.effective_user.first_name # nombre de pila del usuario
    logger.info("Nuevo /start de %s (id %s)", nombre, update.effective_user.id)
    await update.message.reply_text(
        f"¡Hola, {nombre}! 👋 Soy HoloMzaBot, el asistente virtual de HOLO.\n\n"
        "Estoy acá para ayudarte a consultar nuestro catálogo, "
        "conocer los precios y verificar la disponibilidad de nuestros productos. 🛍️\n\n"
        "Podés preguntarme por stickers, agendas, remeras y otros productos personalizados.\n\n"
        "Escribí /help para conocer cómo puedo ayudarte."
    )


#Comando /help
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde al comando /help."""
    await update.message.reply_text(
        "Estos son mis comandos:\n\n"
        "/start - Presentación de HoloMzaBot\n"
        "/help - Esta ayuda\n\n"
        "/olvidar - Borra nuestra conversación y empezamos de cero\n\n"
        "También podés escribirme directamente para:\n"
        "🛍️ Consultar productos y categorías.\n"
        "💲 Conocer precios de productos y variantes.\n"
        "📦 Consultar disponibilidad y stock.\n"
        "🔎 Buscar productos por nombre, diseño o material.\n\n"
        "¡Escribime qué estás buscando y te ayudo!"
    )


async def olvidar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde al comando /olvidar: borra el historial del usuario."""
    borrados = await db.borrar_historial(update.effective_user.id)
    logger.info("Usuario %s borró %d mensajes", update.effective_user.id, borrados)
    await update.message.reply_text("Listo, empezamos de cero. ¿En qué te ayudo?🙂")


#Responder un texto
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde con Gemini, teniendo en cuenta la conversación previa."""
    user_id = update.effective_user.id # identifica de quién es la conversación
    texto = update.message.text
    logger.info("Mensaje de %s: %s", user_id, texto)
    await update.message.chat.send_action(ChatAction.TYPING)

    # Paso 1: recuperar lo que ya se habló con este usuario.
    historial = await db.obtener_historial(user_id, MAX_MENSAJES_HISTORIAL)

    # Paso 2: consultar al modelo con el historial más el mensaje nuevo.
    try:
        respuesta = await consultar_gemini(historial, texto)
    except Exception as error:
        logger.error("Error al consultar a Gemini: %s", error)
        await update.message.reply_text(describir_error(error))
        # Si la consulta falló, no se guarda nada: así el historial nunca
        # queda con una pregunta sin su respuesta.
        return

    # Paso 3: guardar la pregunta y la respuesta para la próxima consulta.
    await db.guardar_intercambio(user_id, texto, respuesta)

    for inicio in range(0, len(respuesta), LIMITE_TELEGRAM):
        await update.message.reply_text(respuesta[inicio:inicio + LIMITE_TELEGRAM])



#Manejo de errores
async def manejo_error(update: Update, context: ContextTypes.DEFAULT_TYPE)-> None:
    #Registra cualquier error para que el bot no se detenga en silencio
    logger.error("Error al procesar una actualizacion",exc_info=context.error)


async def al_iniciar(app: Application) -> None:
    """Se ejecuta una sola vez, antes de comenzar a recibir mensajes."""
    # Es una corrutina porque inicializar la base requiere await;
    # por eso no puede llamarse directamente desde main(), que es síncrona.
    await db.inicializar()
    logger.info("Base de datos lista (%s).", db.RUTA_DB)


def main() -> None:
    faltantes = [nombre for nombre, valor in [("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
    ("GEMINI_API_KEY", GEMINI_API_KEY)]
    if not valor]

    if faltantes:
        raise SystemExit(f"Faltan variables en el .env: {', '.join(faltantes)}")

    # post_init registra una corrutina que la Application ejecuta al arrancar,
    # dentro del bucle de eventos, antes de procesar el primer update.
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(al_iniciar).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", ayuda))
    app.add_handler(CommandHandler("olvidar", olvidar)) # nuevo comando de la v3
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.add_error_handler(manejo_error)

    logger.info("Holo v4 en línea con el modelo %s.", GEMINI_MODEL)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()