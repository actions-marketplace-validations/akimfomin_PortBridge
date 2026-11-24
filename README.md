# PortBridge

Каталог проблем совместимости Xbox Series с ПК. Он помогает найти уже предложенное решение, увидеть границы его проверки и передать результат нужному репозиторию. Начальные источники — Leonida Continued, LeonidaReforge, XCL и VIctory.

## Запуск на Windows

Нужен Python 3.10 или новее. Пакеты ставить не требуется. Из папки PortBridge:

```powershell
python -m portbridge sync
python -m portbridge serve
```

Откройте <http://127.0.0.1:8765/>. Сервер обновляет данные каждые 15 минут, пока он запущен. Остановить его можно через `Ctrl+C`. Если GitHub недоступен, карточки и сохранённые записи остаются доступными. Для запуска без сетевых запросов используйте `python -m portbridge serve --offline`. SQLite хранится в `.portbridge` рядом с кодом. Переопределить путь можно через `python -m portbridge --db <путь> serve`.

`python -m portbridge status` показывает время последней попытки и состояние синхронизации. `python -m portbridge sync --force --pages 2` обновляет кэш и берёт до двух страниц. Для регулярного сбора можно передать `PORTBRIDGE_GITHUB_TOKEN` через переменные окружения с доступом только на чтение публичных данных. В файлах проекта токен хранить не нужно.

## Что выбрать на главной

- Введите название ошибки, номер PR или ID `PB-0001`. Карточка показывает реализацию в каждом проекте, версии, платформы, ссылки и происхождение проверок.
- Во вкладке совпадений сверьте первоисточники. Автоматическое сходство заголовков остаётся подсказкой. Группировку постоянных карточек проверяет куратор.
- В частичном прогрессе найдите, где одна команда уже продвинулась. Откройте её PR, затем найдите обсуждение команды, которая ещё разбирает проблему.
- Ориентир для общей сборки имеет обозначенный статус. Он меняется после подтверждённого прогона и решения сопровождающих. Скриншот меню, успешный тест шейдера и запуск игры считаются разными результатами.
- Подпишитесь на `feed.xml` в приложении для Atom, если хотите получать проверенные обновления. Лента показывает карточки, где есть проверенное или принятое решение. Подробности проверки доступны по ID карточки.
- Черновик ответа даёт ссылку на первоисточник и на открытое обсуждение команды. Вы проверяете текст, решаете, стоит ли его отправлять, и сами публикуете сообщение на GitHub. Для агентов также доступен `GET /api/v1/outreach`. [Документация API](API.md)

## Публичный сайт

```powershell
python -m portbridge export --out dist --repository akimfomin/PortBridge
```

В `dist` лежат автономный сайт, JSON и лента Atom. Статическую папку можно вручную загрузить в проект Cloudflare Pages, созданный в режиме Direct Upload. Публичная страница будет открываться без учётной записи. Флаг `--repository` добавляет ссылку на [форму подтверждений PortBridge](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml). Участник открывает и отправляет форму сам. Проверенные изменения вносятся в `portbridge/data/seed.json` через ревью. [Cloudflare Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)

Для автоматической публикации в Cloudflare подготовлен `.github/workflows/pages.yml`. В GitHub откройте **Settings → Secrets and variables → Actions** и настройте:

| Тип | Имя | Значение |
| --- | --- | --- |
| Переменная | `PORTBRIDGE_ENABLE_CLOUDFLARE_PAGES` | `true` после подготовки проекта Pages |
| Переменная | `PORTBRIDGE_CLOUDFLARE_PROJECT` | Имя существующего проекта Direct Upload с основной веткой `main` |
| Секрет | `CLOUDFLARE_ACCOUNT_ID` | ID аккаунта Cloudflare, где создан проект |
| Секрет | `CLOUDFLARE_API_TOKEN` | Токен с разрешением Account / Cloudflare Pages / Edit для этого аккаунта |

После настройки запустите **Actions → PortBridge static snapshots → Run workflow** на `main`. Workflow выполняет тесты и экспорт также при изменениях в `main` и каждый час. Шаг Cloudflare публикует папку `dist` только при включённой переменной и заданных реквизитах. [Публикация Cloudflare из CI](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/)

Для отдельного варианта на GitHub Pages включите **Settings → Pages → GitHub Actions** и установите `PORTBRIDGE_ENABLE_GITHUB_PAGES` в `true`. Оба варианта публикации выключены при отсутствии своих переменных. [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

## Работа куратора

1. Связать открытые задачи по наблюдаемому симптому. Указать, совпадает ли причина, если она установлена.
2. Зафиксировать источник, автора, точную версию, платформу и результат. Для CI указать конкретный запуск и итог.
3. Показать, где уже есть подходящая правка. Обсудить перенос с сопровождающим проекта и сохранить авторство.
4. После принятия обновить карточку и ссылку на коммит. Для ответа в чужой ветке открыть исходное обсуждение и отправить сообщение вручную.

PortBridge выполняет только запросы чтения к GitHub. В кэше остаются нормализованные метаданные. Тела сообщений, вложения, логи заданий и исходники при синхронизации не сохраняются. Текст источников не исполняется. Публичный экспорт включает только файлы интерфейса и каталог. Для совместной работы нужны решение о сборке-ориентире, подтверждение спорных совпадений, независимые прогоны и согласие сопровождающих на переносы.

Собственный код PortBridge открыт по лицензии MIT. Ссылки на другие проекты и имена авторов сохраняются. Лицензия PortBridge распространяется на его код и документацию. [Лицензия](LICENSE)

## Проверки и структура

```powershell
python -m unittest discover -s tests -v
```

- `portbridge/github.py` получает метаданные и сохраняет кэш. [GitHub REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- `portbridge/catalog.py` хранит карточки и связи в SQLite, строит подсказки совпадений. [Python SQLite](https://docs.python.org/3/library/sqlite3.html)
- `portbridge/__main__.py` запускает локальный API. [Python HTTP server](https://docs.python.org/3/library/http.server.html)
- `portbridge/export.py` формирует переносимую публикацию. [API для агентов](API.md)

## Что добавляет PortBridge

| Что изучили | Что показывает | Что добавляет PortBridge |
| --- | --- | --- |
| [GTA VI PC Race](https://vuyp.github.io/gta6-pc-race/) | Рубежи запуска и хронология по проектам | Поиск одной ошибки и проверенных решений в разных репозиториях |
| [Leonida progress](https://loopersalty.github.io/AnyXboxX/leonida/progress.html) | Метрики, тесты и принятые изменения Leonida | Сопоставление версий разных проектов и видимость происхождения результата |
| [GitHub Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects) | Планирование по Issues и PR | Читаемый каталог доказательств и кандидатов на совпадение по независимым проектам |
