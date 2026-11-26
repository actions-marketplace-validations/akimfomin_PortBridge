# M3 · локальные действия Lab

Для работы нужен существующий отдельный файл Exchange с ключами `read + contribute` для добровольца или `read + review` для ревьюера. Пароль ключа передаётся через переменную окружения `PORTBRIDGE_EXCHANGE_TOKEN`. Публичный режим сохраняет чтение без ключа и отправки. [Права и отзыв](EXCHANGE-API.md)

```sh
python -m portbridge.lab_workflow --db catalog.sqlite3 --exchange-db permissions.sqlite3 dashboard --task rad-...
python -m portbridge.lab_workflow --db catalog.sqlite3 --exchange-db permissions.sqlite3 queue --file review-queue.json
python -m portbridge.lab_workflow --db catalog.sqlite3 --exchange-db permissions.sqlite3 claim --file claim.json
```

Каждое изменение принимает `request_id` длиной 8–80 символов. Повторяйте прежний ID с прежним содержимым при восстановлении после сбоя. Для нового действия указывайте новый ID.

- `propose` задаёт `target_url`, `comparison_url`, две `revisions`, `title`, `kind`, `expected` и необязательные `equipment`, `os`. Источники должны быть публичными и индексироваться на указанных версиях.
- `queue` принимает `task` и `note` после оценки черновика ревьюером. `claim` и `release` используют `task`. Настраиваемая длительность `ttl_seconds` от 60 до 604800. `recheck` открывает независимый раунд.
- `submit` принимает `task` и объект `report`. У отчёта есть `revisions`, `environment`, `equipment`, `commands`, `outcome`, `expected`, `observed`, `artifact_sha256`, `source_url`, `limitations`, `ai_assistance`, `share_public`. Допустимы PASS, FAIL, SKIP и ERROR. Отсутствующие данные снижают признание до incomplete.
- `correct` и `withdraw_report` требуют `report_id` автора. `review` принимает `report_id`, `decision`, `note` и явное `checked_artifact`. Для проверенного FAIL ревьюер может указать `hypothesis_rejected`. Отчёт сохраняется, даже если гипотезу отклонили.
- `deliver`, `adopt`, `decline` регистрируют локально уже наблюдавшееся подтверждение с `evidence_url`, `note` и `checked_artifact`. Укажите конкретный комментарий или, для принятия, отдельный PR либо полный SHA коммита принимающего проекта. Подготовленный в dashboard текст можно показать владельцу.
- `profile` включает добровольную подборку по `equipment`, `os` и `specialty`. `enabled: false` убирает сохранённые предпочтения.

HTTP-эквиваленты доступны на loopback в `/api/v1/exchange/lab-action` и `/api/v1/exchange/lab-dashboard?task=...` при включённом Exchange. В POST тело содержит поле `action` и указанные поля команды. Чтение на сайте, через `portbridge_radar` и `portbridge_lab` не выполняет операций очереди. Команды из источников и отчётов считаются данными. Перед запуском внешнего кода нужен явный выбор добровольца.
