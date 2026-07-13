"""Helper: lista los chat_id que ve el bot (para migrar a un canal/supergrupo).

Uso:
1. Crear un canal (o supergrupo) PRIVADO en Telegram.
2. Agregar el bot como administrador con permiso "Eliminar mensajes".
3. Publicar cualquier mensaje en el canal (o que el bot publique).
4. Correr:  python get_telegram_chat_id.py
5. Copiar el chat_id (-100xxxxxxxxxx) a telegram_credentials.txt.

Lee el token de:
  C:\\Users\\k_99_\\Desktop\\codding\\data_footprint_generator\\trade_results_score\\telegram_credentials.txt
"""

import json
import os
from urllib.request import urlopen


RESULTS_FOLDER = (
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)


def read_token():
    path = os.path.join(RESULTS_FOLDER, "telegram_credentials.txt")
    with open(path, "r", encoding="utf-8") as file:
        for raw in file:
            line = raw.strip()
            if line.lower().startswith("token") and "=" in line:
                return line.split("=", 1)[1].strip()
    raise SystemExit("No encontre 'token' en telegram_credentials.txt")


def main():
    token = read_token()
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    with urlopen(url, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        raise SystemExit(f"Telegram getUpdates fallo: {payload}")

    seen = {}
    for update in payload.get("result", []):
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            chat = (update.get(key) or {}).get("chat")
            if chat:
                seen[chat["id"]] = chat

    if not seen:
        print(
            "No hay updates. Publica un mensaje en el canal con el bot ya admin y "
            "vuelve a correr. (getUpdates solo muestra lo reciente.)"
        )
        return

    print("Chats visibles para el bot:")
    for chat_id, chat in seen.items():
        title = chat.get("title") or chat.get("username") or chat.get("first_name", "")
        chat_type = chat.get("type", "?")
        flag = "  <-- canal/supergrupo (borra cualquier edad)" if str(chat_id).startswith("-100") else ""
        print(f"  chat_id={chat_id}  tipo={chat_type}  '{title}'{flag}")


if __name__ == "__main__":
    main()
