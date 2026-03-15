# Bot de Gastos del Hogar — Lucas & Serri

Bot de Telegram que registra gastos automáticamente en Google Sheets usando IA.

## Variables de entorno necesarias

```
TELEGRAM_TOKEN=tu_token_de_botfather
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
SHEET_ID=id_de_tu_google_sheet
GOOGLE_CREDS_JSON={"type":"service_account",...} (todo el JSON en una línea)
```

## Uso

Escribí en el grupo:
- "super $1200" → detecta gasto de Lucas
- "cena $800 Serri" → detecta gasto de Serri
- "luz $2300" → servicios

Comandos:
- /resumen → resumen del mes
- /resumen todo → histórico completo
- /borrar → borra el último gasto
- /ayuda → ayuda
