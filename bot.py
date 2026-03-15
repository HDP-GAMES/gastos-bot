import os
import json
import re
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SHEET_ID = os.environ["SHEET_ID"]
GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]

LUCAS = "Lucas"
SERRI = "Serri"

def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def get_username(update: Update) -> str:
    name = update.effective_user.first_name or ""
    name_lower = name.lower()
    if "serri" in name_lower or "serra" in name_lower:
        return SERRI
    return LUCAS

def parse_expense_with_ai(text: str, sender: str) -> dict | None:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Analiza este mensaje de un chat de finanzas del hogar y extrae el gasto si hay uno.

Mensaje: "{text}"
Enviado por: {sender}

Responde SOLO con JSON valido, sin texto extra, sin markdown, sin explicaciones, sin backticks.
Si hay un gasto responde exactamente asi:
{{"es_gasto": true, "descripcion": "descripcion corta", "monto": 1234, "quien_pago": "{sender}", "categoria": "Comida"}}

Las categorias posibles son: Comida, Servicios, Transporte, Salud, Salidas, Hogar, Otros

Si NO es un gasto responde exactamente:
{{"es_gasto": false}}

Reglas:
- monto es siempre un numero entero sin simbolos
- Si dice "yo" quien_pago es {sender}
- Si no dice quien pago, asumir {sender}
- Si menciona a Lucas o Serri, asignarlo a esa persona
- NO uses backticks ni markdown en tu respuesta"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": prompt
            },
            {
                "role": "assistant",
                "content": "{"
            }
        ]
    )

    raw = "{" + response.content[0].text.strip()
    logger.info(f"Claude respondio: {raw}")

    raw = re.sub(r"```json|```", "", raw).strip()
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return json.loads(raw)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    sender = get_username(update)

    if text.startswith("/"):
        return

    try:
        result = parse_expense_with_ai(text, sender)

        if not result or not result.get("es_gasto"):
            return

        sheet = get_sheet()
        fecha = datetime.now().strftime("%d/%m/%Y")
        row = [
            fecha,
            result["quien_pago"],
            result["descripcion"],
            result["monto"],
            result["categoria"],
            text
        ]
        sheet.append_row(row)

        await update.message.reply_text(
            f"✓ {result['descripcion']} — ${result['monto']:,} ({result['categoria']}) pagado por {result['quien_pago']}"
        )
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()

        if not rows:
            await update.message.reply_text("Todavia no hay gastos cargados.")
            return

        now = datetime.now()
        mes_actual = now.strftime("%m/%Y")

        args = context.args
        if args and args[0].lower() in ["todo", "all"]:
            gastos = rows
            titulo = "todos los gastos"
        else:
            gastos = [r for r in rows if str(r.get("fecha", "")).endswith(mes_actual)]
            titulo = f"este mes ({now.strftime('%m/%Y')})"

        if not gastos:
            await update.message.reply_text(f"No hay gastos cargados {titulo}.")
            return

        total = sum(float(str(r["monto"]).replace(",", "")) for r in gastos)
        lucas_total = sum(float(str(r["monto"]).replace(",", "")) for r in gastos if r["quien_pago"] == LUCAS)
        serri_total = sum(float(str(r["monto"]).replace(",", "")) for r in gastos if r["quien_pago"] == SERRI)

        diff = lucas_total - serri_total

        if abs(diff) < 1:
            balance_txt = "Estan 50/50 ✓"
        elif diff > 0:
            balance_txt = f"Serri le debe a Lucas: ${diff/2:,.0f}"
        else:
            balance_txt = f"Lucas le debe a Serri: ${abs(diff)/2:,.0f}"

        cats = {}
        for r in gastos:
            cat = r.get("categoria", "Otros")
            cats[cat] = cats.get(cat, 0) + float(str(r["monto"]).replace(",", ""))
        cats_sorted = sorted(cats.items(), key=lambda x: x[1], reverse=True)
        cats_txt = "\n".join(f"  {cat}: ${monto:,.0f}" for cat, monto in cats_sorted)

        msg = f"""Resumen {titulo}

Total: ${total:,.0f}
{LUCAS}: ${lucas_total:,.0f}
{SERRI}: ${serri_total:,.0f}

{balance_txt}

Por categoria:
{cats_txt}

{len(gastos)} gastos registrados"""

        await update.message.reply_text(msg)

    except Exception as e:
        logger.error(f"Error en resumen: {e}")
        await update.message.reply_text("Hubo un error al calcular el resumen.")

async def borrar_ultimo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_values()
        if len(rows) <= 1:
            await update.message.reply_text("No hay gastos para borrar.")
            return
        last = rows[-1]
        sheet.delete_rows(len(rows))
        await update.message.reply_text(f"Borrado: {last[2]} — ${last[3]} ({last[1]})")
    except Exception as e:
        logger.error(f"Error borrando: {e}")
        await update.message.reply_text("Hubo un error al borrar.")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """Comandos:

/resumen — resumen del mes
/resumen todo — historico completo
/borrar — borra el ultimo gasto
/ayuda — este mensaje

Para cargar un gasto escribi cualquier cosa natural:
"fui al super, gaste 1200"
"pague la luz 2300"
"cena con amigos $800 Serri"
"farmacia 450"

El bot detecta automaticamente quien pago y la categoria."""
    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CommandHandler("borrar", borrar_ultimo))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("start", ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()
