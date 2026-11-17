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
from prompts import PROMPT_SISTEMA # prompt de sistema definido en prompts.py

# Carga en el entorno las variables del archivo .env.
load_dotenv()
# Lectura de las variables. os.getenv devuelve None si la variable no existe.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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
# Registrador propio del bot; sus mensajes aparecen con el nombre "malbi".
logger = logging.getLogger("malbi")
# Longitud máxima de un mensaje de Telegram, en caracteres.
LIMITE_TELEGRAM = 4096


logging.getLogger("httpx").setLevel(logging.WARNING)

# Se crea un único cliente para todo el programa. El cliente guarda la clave
# de API y administra las conexiones HTTP con los servidores de Google.
# Crearlo una sola vez evita abrir una conexión nueva en cada mensaje.
cliente_gemini = genai.Client(api_key=GEMINI_API_KEY)
async def consultar_gemini(mensaje: str) -> str:
    """Envía un mensaje a Gemini y devuelve el texto de la respuesta."""
# .aio accede a la versión asíncrona del cliente; por eso la llamada
# lleva await. Mientras se espera la respuesta, el bucle de eventos
# puede atender los mensajes de otros usuarios.
    interaccion = await cliente_gemini.aio.interactions.create(
        model=GEMINI_MODEL, # nombre del modelo, leído del .env
        system_instruction=PROMPT_SISTEMA, # personalidad y reglas de Malbi
        input=mensaje, # texto enviado por el usuario
        store=False, # Google no conserva la interacción
    )
# output_text contiene el texto generado por el modelo. Si llega vacío
# (None o ""), el operador "or" devuelve el mensaje alternativo para que
# el bot nunca envíe una respuesta en blanco.
    return interaccion.output_text or "No se me ocurrió nada para responder 🤔"

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
        "También podés escribirme directamente para:\n"
        "🛍️ Consultar productos y categorías.\n"
        "💲 Conocer precios de productos y variantes.\n"
        "📦 Consultar disponibilidad y stock.\n"
        "🔎 Buscar productos por nombre, diseño o material.\n\n"
        "¡Escribime qué estás buscando y te ayudo!"
    )

#Responder un texto (funcion eco)
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde cualquier mensaje de texto usando Gemini."""
    texto = update.message.text # texto enviado por el usuario
    logger.info("Mensaje de %s: %s", update.effective_user.id, texto)

    # Muestra "escribiendo..." en el chat. La indicación dura unos segundos
    # o hasta que el bot envía su respuesta.
    await update.message.chat.send_action(ChatAction.TYPING)

    # La consulta a una API externa puede fallar por causas ajenas al código;
    # try/except evita que el error llegue al usuario como silencio.
    try:
        respuesta = await consultar_gemini(texto)
    except Exception as error:
        logger.exception("Error al consultar a Gemini") # detalle técnico, para el desarrollador
        await update.message.reply_text(describir_error(error)) # mensaje amable, para el usuario
        return # se termina el handler

    # Si la respuesta supera el límite de Telegram, se envía en partes.
    # range(0, len, LIMITE) produce 0, 4096, 8192, ...: el inicio de cada parte.
    for inicio in range(0, len(respuesta), LIMITE_TELEGRAM):
        await update.message.reply_text(respuesta[inicio:inicio + LIMITE_TELEGRAM])


#Manejo de errores
async def manejo_error(update: Update, context: ContextTypes.DEFAULT_TYPE)-> None:
    #Registra cualquier error para que el bot no se detenga en silencio
    logger.error("Error al procesar una actualizacion",exc_info=context.error)

def main() -> None:
    # Lista con los nombres de las variables obligatorias que faltan en el .env.
    faltantes = [nombre for nombre, valor in [("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
    ("GEMINI_API_KEY", GEMINI_API_KEY)]
    if not valor]
    if faltantes:
        # SystemExit termina el programa mostrando el mensaje indicado.
        raise SystemExit(f"Faltan variables en el .env: {', '.join(faltantes)}")

    # Se construye la Application con el token del bot.
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registro de handlers. El orden importa: se usa el primero que coincide.
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", ayuda))

    # Texto que no sea comando: ahora lo atiende responder (antes, eco).
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.add_error_handler(manejo_error)

    logger.info("HoloBot v2 en línea con el modelo %s.", GEMINI_MODEL)

    # Polling: el bot consulta a Telegram, de forma continua, si hay mensajes nuevos.
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()