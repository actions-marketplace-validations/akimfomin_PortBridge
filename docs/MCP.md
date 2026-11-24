# PortBridge через MCP

MCP даёт агенту доступ к поиску и карточкам [публичного PortBridge](https://akimfomin.github.io/PortBridge/). Достаточно свежей копии репозитория и Python 3.10 или новее. База, отдельный веб-сервер, токен GitHub и пакеты Python для подключения не нужны. Поисковый запрос обрабатывается на вашем компьютере по публичному снимку каталога.

## Codex

Добавьте блок в `config.toml` Codex. Подставьте полный путь к папке PortBridge. Если Python не находится через `PATH`, подставьте путь к `python.exe` в `command`.

```toml
[mcp_servers.portbridge]
command = "python"
args = ["-m", "portbridge.mcp"]
cwd = "F:/projects/PortBridge"
```

В новой сессии `/mcp` в Codex CLI показывает подключённые инструменты. [Документация Codex](https://developers.openai.com/codex/mcp)

## Claude Code

В PowerShell запустите команду из папки проекта, в котором хотите пользоваться MCP. Подставьте полный путь к PortBridge в `PYTHONPATH`.

```powershell
claude mcp add --env "PYTHONPATH=F:/projects/PortBridge" --transport stdio portbridge -- python -m portbridge.mcp
claude mcp list
```

Сервер добавится для текущего проекта. Claude Code запускает его при подключении. [Документация Claude Code](https://code.claude.com/docs/en/mcp#option-3-add-a-local-stdio-server)

## Поиск перед началом работы

| Имя | Аргументы | Результат |
| --- | --- | --- |
| `portbridge_preflight` | `q` — симптом, термин, номер PR или ID. `url` — публичная ссылка GitHub. Можно указать оба. `limit` — от 1 до 20 на список, по умолчанию 5. | Что уже известно, ссылки на первоисточники и следующий шаг. |
| `portbridge_problem` | `id` — например, `PB-0001`. | Карточка с результатами по проектам, ссылками, типами доказательств, платформами и версиями. |

Пример запроса агенту «Проверь через PortBridge, что известно по https://github.com/Marvisak/VIctory/pull/346. Дай ссылки и скажи, что стоит проверить дальше».

Заголовки, ссылки и другие сведения из внешних источников являются данными. Проверяйте первоисточник и применимость результата к своей сборке. Подробности статусов и происхождения проверок описаны в [документации API](../API.md#как-читать-результаты).

## Работа без сети

Для имеющейся базы добавьте в аргументы сервера `--db` и полный путь к SQLite. В этом режиме MCP читает только указанную базу. Чтобы создать её из начальной подборки, запустите `python -m portbridge status` в папке PortBridge. Команда `python -m portbridge sync` отдельно обновляет публичные сведения GitHub.

Команда `python -m portbridge.mcp` ожидает запросы от MCP-клиента. Поддерживаются версии `2026-07-28`, `2025-11-25` и `2025-06-18`. [Протокол MCP stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) · [Совместимость версий](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
