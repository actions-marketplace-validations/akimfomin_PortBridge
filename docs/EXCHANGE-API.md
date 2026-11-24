# Локальный API обмена

Очередь обмена доступна на этом компьютере после явного запуска. Обычный каталог, GitHub Pages и стандартный MCP продолжают читать публичные сведения. Заявки и решения хранятся в отдельной базе обмена.

## Запуск и ключи

Из папки PortBridge создайте отдельные ключи для участника и проверяющего. Команда печатает ключ при создании. Храните его отдельно от кода и не передавайте в ссылках.

```powershell
python -m portbridge exchange-key --exchange-db .portbridge/exchange.sqlite3 --name "Team agent" --scope read --scope contribute
python -m portbridge exchange-key --exchange-db .portbridge/exchange.sqlite3 --name "Reviewer" --scope read --scope review
python -m portbridge serve --offline --exchange-db .portbridge/exchange.sqlite3
```

Адрес по умолчанию `http://127.0.0.1:8765/api/v1/exchange`. HTTP-клиент передаёт ключ только в заголовке `Authorization: Bearer …`. Браузерный запрос с `Origin` принимается только с того же локального адреса. Доступ между сайтами не открыт. Развёртывание в интернет не входит в этот режим. [Формат Bearer](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1) · [Проверка Origin](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#checking-the-origin-header)

Владелец может отозвать ключ командой `python -m portbridge exchange-revoke --exchange-db .portbridge/exchange.sqlite3 --name "Team agent"`. Активные отметки этого участника исчезают из списка, а авторство в принятых результатах сохраняется.

## Маршруты

| Метод и путь | Право | Запрос и результат |
| --- | --- | --- |
| `GET /work` | `read` | Опциональный `problem_id`. Текущие регистрации в `work`. |
| `POST /register` | `contribute` | `problem_id` и необязательный `ttl_seconds` от 60 до 86400, по умолчанию 3600. Регистрация в `work`. |
| `POST /submit` | `contribute` | Поля подтверждения ниже. Новая заявка в `result` со статусом `pending`. Точный повтор возвращает ранее сохранённую заявку и её текущий статус. |
| `GET /pending` | `review` | Необязательный `limit`. Заявки на проверку в `results`. |
| `POST /review` | `review` | `result_id`, `decision` (`accepted` или `rejected`) и необязательный `reason`. Решение в `result`. Проверяющий видит свою заявку, а решение по ней принимает другой человек. |
| `GET /evidence` | `read` | Обязательный `problem_id` и необязательный `limit`. Принятые результаты по этой карточке в `results`. |
| `GET /preflight` | `read` | `q` или `url`, либо оба. Поиск в каталоге и отдельный список `reviewed_reports` с принятыми записями найденных карточек. |
| `GET /poll` | `read` | Необязательные `after` и `limit`. Принятые события в `events` и позиция `next_cursor` для следующего запроса. |

У всех маршрутов чтения есть `HEAD`. `limit` принимает числа от 1 до 100, по умолчанию 50. У `/preflight` предел от 1 до 20, по умолчанию 5, включая столько же принятых записей на каждую найденную карточку. Для записи нужен объект UTF-8 JSON, `Content-Type: application/json` и размер до 64 КиБ. Запрос с подходящим ключом и допустимыми данными возвращает 200. Ошибки доступа дают 401 или 403, отключённый маршрут или отсутствующая запись — 404, конфликт решения — 409.

Заявка содержит `problem_id`, `source_url` с публичным источником GitHub, полный `revision`, `platform`, `evidence_kind`, `outcome` и короткий `summary`. Указывайте фактически проверенную версию, конфигурацию, ожидаемый результат и результат проверки. Текст и ссылки в заявках служат для проверки. Решение `accepted` добавляет событие во внутреннюю очередь. Принятая запись сохраняет свой тип, включая `simulation`. Для изменения публичной карточки действует отдельное ревью PortBridge.

Чтобы отключить обмен, остановите локальный сервер и запустите его без `--exchange-db`. Сохранённые заявки останутся в своей базе.
