# PortBridge

PortBridge помогает командам, которые продолжают работу Leonida и развивают совместимость Xbox Series с ПК. После разделения проекта работа разошлась по разным репозиториям. Одна команда может уже разбираться с той же ошибкой, другая держит у себя подходящий тест, а третья повторяет исследование с нуля. PortBridge связывает такие работы и помогает довести находку до проверки или правки в нужном проекте.

[Проверить свою задачу / Search existing work](https://akimfomin.github.io/PortBridge/) · [Поделиться результатом / Share a result](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)

## Как пользоваться

1. **Перед работой** введите точную ошибку, название операции или номер PR. Откройте связанный первоисточник и проверьте, совпадают ли условия.
2. **Возьмите один проверяемый шаг.** Попробуйте готовый тест, сравните две реализации или подтвердите, где перенос не подходит. Запишите версию, стенд, ожидаемое и фактическое поведение.
3. **Передайте результат по назначению.** Оставьте одну запись со ссылкой на исходную работу и тем, что проверили. Если она помогает другому проекту, сослитесь на неё в его существующем PR или issue и предложите конкретный следующий шаг.
4. **Замкните обратную связь.** Добавьте ссылку на ответ, перенос или причину отказа. Следующая команда увидит, что уже проверено, на какой версии и кому принадлежит работа.

Работать можно из своего проекта. Сопровождающие решают, что применять в своей сборке. Для первых шагов достаточно публичного каталога и GitHub. Время поиска, повторные прогоны и фактическое применение результата учитываются в пилоте.

## For contributors

Work that started in Leonida now continues across several repositories. A fix can be under review in one project while another already has the test it needs. PortBridge connects the sources so each team can reuse work and keep credit attached to the original contribution.

1. **Search before starting** by exact error, instruction, or PR number. Open the original source to confirm the scope.
2. **Run one focused check** in your project's configuration. Record the revision, platform, expected behavior, actual result, and any limitations.
3. **Share the result once.** Link your report in the relevant issue or PR with a concrete suggestion. Add the reply, follow-up patch, or reason the result could not be reused. [Evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)

For agents and maintainers. [Agent prompt](docs/AGENT-PROMPT.md) · [MCP](docs/MCP.md) · [API](API.md) · [Optional PR check](docs/GITHUB-ACTION.md) · [Suggest an improvement](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml)

## Запуск на Windows

Нужен Python 3.10 или новее. Пакеты ставить не требуется. Из папки PortBridge:

```powershell
python -m portbridge sync
python -m portbridge serve
```

Откройте <http://127.0.0.1:8765/>. Сервер обновляет данные каждые 15 минут, пока он запущен. Остановить его можно через `Ctrl+C`. Если GitHub недоступен, карточки и сохранённые записи остаются доступными. Для запуска без сетевых запросов используйте `python -m portbridge serve --offline`. SQLite хранится в `.portbridge` рядом с кодом. Переопределить путь можно через `python -m portbridge --db <путь> serve`.

`python -m portbridge status` показывает время последней попытки и состояние синхронизации. `python -m portbridge sync --force --pages 2` обновляет кэш и берёт до двух страниц. Для регулярного сбора можно передать `PORTBRIDGE_GITHUB_TOKEN` через переменные окружения с доступом только на чтение публичных данных. В файлах проекта токен хранить не нужно.

`python -m portbridge backfill --pages 6` догружает старые публичные задачи и PR. Повторный запуск продолжает с сохранённой страницы. `python -m portbridge incremental --pages 6` подбирает изменения с прошлого обновления. Оба запуска ограничены по времени и сохраняют прогресс. GitHub Actions выполняет эти команды при публикации.

## Что выбрать на главной

- Введите название ошибки, номер PR или ID `PB-0001`. Карточка показывает реализацию в каждом проекте, версии, платформы, ссылки и происхождение проверок.
- Во вкладке совпадений сверьте первоисточники. PortBridge учитывает прямые ссылки между репозиториями, технические термины и коды ошибок. Подсказка требует проверки куратором перед внесением в постоянную карточку.
- В частичном прогрессе найдите, где одна команда уже продвинулась. Откройте её PR, затем найдите обсуждение команды, которая ещё разбирает проблему.
- Ориентир для общей сборки имеет обозначенный статус. Он меняется после подтверждённого прогона и решения сопровождающих. Скриншот меню, успешный тест шейдера и запуск игры считаются разными результатами.
- Подпишитесь на `feed.xml` в приложении для Atom, если хотите получать проверенные обновления. Лента показывает карточки, где есть проверенное или принятое решение. Подробности проверки доступны по ID карточки.
- Черновик ответа даёт ссылку на первоисточник и на открытое обсуждение команды. Вы проверяете текст, решаете, стоит ли его отправлять, и сами публикуете сообщение на GitHub. Для агентов также доступен `GET /api/v1/outreach`. [Документация API](API.md)

## Публичный сайт

```powershell
python -m portbridge export --out dist --repository akimfomin/PortBridge
```

В `dist` лежат автономный сайт, JSON и лента Atom. Публичная страница будет открываться без учётной записи. Флаг `--repository` добавляет ссылку на форму подтверждений PortBridge. Участник открывает и отправляет форму сам. Проверенные изменения вносятся в `portbridge/data/seed.json` через ревью.

Workflow `.github/workflows/pages.yml` выполняет тесты и экспорт при изменениях в `main`, каждый час и при ручном запуске через **Actions → PortBridge static snapshots → Run workflow** на `main`.

Для публикации на GitHub Pages выберите **Settings → Pages → GitHub Actions**. Установите переменную репозитория `PORTBRIDGE_ENABLE_GITHUB_PAGES` в `true` и запустите workflow. [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

Для Cloudflare Pages можно вручную загрузить `dist` в проект Direct Upload. Для автоматической публикации через тот же workflow откройте **Settings → Secrets and variables → Actions** в GitHub и добавьте следующие параметры. [Cloudflare Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)

| Тип | Имя | Значение |
| --- | --- | --- |
| Переменная | `PORTBRIDGE_ENABLE_CLOUDFLARE_PAGES` | `true` после подготовки проекта Pages |
| Переменная | `PORTBRIDGE_CLOUDFLARE_PROJECT` | Имя существующего проекта Direct Upload с основной веткой `main` |
| Секрет | `CLOUDFLARE_ACCOUNT_ID` | ID аккаунта Cloudflare, где создан проект |
| Секрет | `CLOUDFLARE_API_TOKEN` | Токен с разрешением Account / Cloudflare Pages / Edit для этого аккаунта |

Шаг Cloudflare публикует папку `dist` при включённой переменной и заданных реквизитах. Каждый вариант автоматической публикации включается своей переменной. [Публикация Cloudflare из CI](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)

## Работа куратора

1. Связать открытые задачи по наблюдаемому симптому. Указать, совпадает ли причина, если она установлена.
2. Зафиксировать источник, автора, точную версию, платформу и результат. Для CI указать конкретный запуск и итог.
3. Показать, где уже есть подходящая правка. Обсудить перенос с сопровождающим проекта и сохранить авторство.
4. После принятия обновить карточку и ссылку на коммит. Для ответа в чужой ветке открыть исходное обсуждение и отправить сообщение вручную.

PortBridge выполняет только запросы чтения к GitHub. В кэше остаются нормализованные метаданные. Тела сообщений, вложения, логи заданий и исходники при синхронизации не сохраняются. Текст источников не исполняется. Публичный экспорт включает только файлы интерфейса и каталог. Для совместной работы нужны решение о сборке-ориентире, подтверждение спорных совпадений, независимые прогоны и согласие сопровождающих на переносы.

Если находка PortBridge помогла переиспользовать тест или отказаться от повторной работы, добавьте ссылку на подтверждение в форму. Такие отчёты позволяют считать наблюдаемый эффект отдельно от числа предложенных совпадений. [Форма подтверждений](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)

Собственный код PortBridge открыт по лицензии MIT. Ссылки на другие проекты и имена авторов сохраняются. Лицензия PortBridge распространяется на его код и документацию. [Лицензия](LICENSE)

## Проверки и структура

```powershell
python -m unittest discover -s tests -v
```

- `portbridge/github.py` получает метаданные и сохраняет кэш. [GitHub REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- `portbridge/catalog.py` хранит карточки и связи в SQLite, строит подсказки совпадений. [Python SQLite](https://docs.python.org/3/library/sqlite3.html)
- `portbridge/__main__.py` запускает локальный API. [Python HTTP server](https://docs.python.org/3/library/http.server.html)
- `portbridge/export.py` формирует переносимую публикацию. [API для агентов](API.md)

Для быстрой проверки описания задачи или ссылки можно запустить `python -m portbridge.preflight --q rectlist`. Команда читает публичный каталог без ключа GitHub и показывает, какой источник проверить первым. [Результаты оценки поиска](docs/SEARCH-EVALUATION.md)

## Обмен между подключёнными агентами

Публичный каталог доступен на чтение. Владелец локального экземпляра может включить общую очередь и выдать отдельные права на чтение, предложение результата и проверку. Регистрация задачи действует ограниченное время и позволяет нескольким участникам работать параллельно. Принятый результат доступен другим подключённым агентам с именем автора и проверяющего. [Настройка локального обмена](docs/EXCHANGE-API.md)

`python -m portbridge.exchange_demo` запускает изолированную демонстрацию двух тестовых агентов на основе карточки с реальными источниками. Вторая часть демонстрации использует синтетический тест. [Ход и границы проверки](docs/EXCHANGE-DEMO.md)

Для резервной копии каталога используйте `python -m portbridge backup --out .portbridge/catalog-backup.sqlite3`. Для очереди укажите её путь глобальным параметром `--db` перед `backup`. Копия очереди содержит сведения об участниках и хеши ключей. Храните её вместе с другими закрытыми данными проекта.

## Что добавляет PortBridge

| Что изучили | Что показывает | Что добавляет PortBridge |
| --- | --- | --- |
| [GTA VI PC Race](https://vuyp.github.io/gta6-pc-race/) | Рубежи запуска и хронология по проектам | Поиск одной ошибки и проверенных решений в разных репозиториях |
| [Leonida progress](https://loopersalty.github.io/AnyXboxX/leonida/progress.html) | Метрики, тесты и принятые изменения Leonida | Сопоставление версий разных проектов и видимость происхождения результата |
| [GitHub Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects) | Планирование по Issues и PR | Читаемый каталог доказательств и кандидатов на совпадение по независимым проектам |
