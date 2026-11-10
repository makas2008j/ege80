EGE Russian 80+ — AI через Cloudflare Tunnel
============================================

Запуск (все в одном):
1. Запусти start_ege.bat. Он поднимет:
   - Ollama (если не запущена),
   - AI Bridge (ai_bridge.py, порт 8000, защита токеном),
   - Cloudflare Tunnel (публичный https://...trycloudflare.com),
   - локальный сайт на http://127.0.0.1:8080.
2. В окне батника появятся PHONE URL и AI TOKEN.
3. На телефоне открой сайт -> вкладка 🤖 AI.
4. Вставь PHONE URL и AI TOKEN, нажми Сохранить, затем Проверить.

Примечания:
- Туннель меняет адрес при каждом запуске — бери новый URL из окна батника.
- Токен лежит в data/ai_token.txt (рядом) и переиспользуется между запусками.
- Без токена bridge отвечает 401 — только локально на ПК.

Модель: qwen2.5vl:7b (vision — читает фото заданий).
Если её нет в Ollama, скачать:
  ollama pull qwen2.5vl:7b

Файлы:
- start_ege.bat — главный запуск
- start.bat — только локальный сервер сайта (http.server 8080)
- bridge/ai_bridge.py — AI Bridge v6 (Ollama/Qwen, поддержка фото)
- data/ai_token.txt — токен (создаётся при первом запуске)
- index.html — сайт с вкладкой AI