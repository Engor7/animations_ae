# Claude ↔ After Effects bridge

Панель внутри AE поднимает локальный сервер, а Claude Code ходит в него через MCP.
Даёт настоящие результаты и ошибки скриптов (без «молчаливых» обрывов), состояние проекта
с выделением и кадры прямо из композиции.

## Установка
```
tools/ae-bridge/install.sh      # копирует панель в ~/Library/Application Support/Adobe/CEP/extensions
```
Дальше перезапустить AE. Панель открывается сама (Window > Extensions > Claude Bridge),
слушает 127.0.0.1:37812, токен лежит в `~/animations/.ae-bridge/token` (без него запросы отвергаются).

MCP-сервер прописан в `~/animations/.mcp.json` как `after-effects`, запускается из `.venv`.
Чтобы Claude Code его увидел, его нужно перезапустить из папки `~/animations`.

## Инструменты
- `ae_eval(code)` — ExtendScript в открытом AE; `code` это тело функции, значение возвращается через `return`
  (строкой: в ExtendScript нет JSON). Ошибка приходит с номером строки.
- `ae_state()` — версия, файл проекта, все композиции, активная композиция и время, выделенные слои
  и свойства, очередь рендера.
- `ae_frame(comp?, time?, crop?, max_width?, bg?)` — кадр композиции картинкой (по умолчанию активная
  композиция на текущем времени), уменьшенный и положенный на серый фон.

## Разработка
После правки `extension/bridge.js`: `./install.sh` и затем
`curl -s -X POST -H "X-Bridge-Token: $(cat ~/animations/.ae-bridge/token)" -d '{}' http://127.0.0.1:37812/reload`
— панель перечитает файл без перезапуска AE.

Известные грабли AE-скриптинга: дробный `TextDocument.tracking` и `OutputModule.setSettings({"Color":…})`
обрывают скрипт молча; поворот 2D-слоя это `ADBE Rotate Z`.
