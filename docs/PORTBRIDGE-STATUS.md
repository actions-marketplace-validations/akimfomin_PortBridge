# PortBridge 3.0 · состояние проекта

## Пилот M5 и приёмка M6

Владелец разрешил испытания в GitHub, согласованный пилот, выпуск и откат. Текущие ревизии, результаты и открытые условия публикуются в [постоянном отчёте](https://github.com/akimfomin/PortBridge/blob/audit/review/audit/LATEST.md) и [реестре 122 требований](PORTBRIDGE-CHECKLIST.md). Ниже сохранены результаты на момент каждого этапа.

## M5 · состояние до публичного пилота

Владелец предварительно принял M4 и разрешил M5. Готовы локальный добровольный обмен, вход с одной страницы, партнёрская лента и три сценария на реальных задачах. Независимая проверка M0–M5, широкая выдача SEARCH-08, независимая оценка RAD-07, проверка на GitHub и публичная эксплуатация остаются открытыми. NET-12: исторический повтор подтверждён у 1 команды из 3 (FrameLab). Для перезапуска M5 подтверждено 0 из 3. [Проверка через CLI](../audit/evidence/network.md). [Результаты](PORTBRIDGE-M5.md) · [План пилота](PORTBRIDGE-M5-PILOT.md)

## M4 · локальная приёмка

Владелец предварительно принял M3 и разрешил M4. Карта People, Impact и связи Xbox Series с PS5 подготовлены локально. [Отчёт](PORTBRIDGE-M4.md) · [Публичный пилот](PORTBRIDGE-M4-PILOT.md)

Независимые аудиты прежних этапов, SEARCH-08, независимая оценка Radar и публичная эксплуатационная приёмка открыты. Владелец разрешил следующий этап M5.

## M3 · локальный кандидат

Владелец предварительно принял M2.1 и разрешил M3. Radar, очередь Lab и расширение наблюдения на PS5 проверены в локальном кандидате. [Разбор M3](PORTBRIDGE-M3.md) · [PS5](PORTBRIDGE-PS5-SPEC.md)

Независимый аудит M0–M2.1, качество широкой поисковой выдачи и публичная эксплуатационная приёмка остаются открытыми. M3 предварительно принят владельцем.

## M2.1 · локальный кандидат

Владелец предварительно оценил M2 положительно и запросил ограниченную коррекцию перед приёмкой. В M2.1 разделены исследовательская выдача и технические рекомендации, добавлен ограниченный самостоятельный поиск для новых наблюдений. Результаты старой проверки и нового holdout, десять примеров и оставшиеся условия описаны в [отчёте M2.1](PORTBRIDGE-M2.1.md).

Пакет M0–M2.1 подготовлен для независимой проверки. Независимый аудит M0–M1 и публичная эксплуатационная приёмка M1 открыты. Владелец предварительно принял M2.1 и разрешил M3. Открытые условия перенесены в реестр.

## M2 · локальный кандидат

Ветка `codex/portbridge-v3-m2` начата от `a203e1f`. Discovery встроен в поиск. Исследованы 13 открытых задач в шести репозиториях, закреплены 23 исторических источника. Сравнительный набор из 71 проверки, измерения, команды и условия приёмки приведены в [отчёте M2](PORTBRIDGE-M2.md). Обязательный [реестр](PORTBRIDGE-CHECKLIST.md) сохраняет 116 исходных требований и добавляет DISC-01–06.

M2 предварительно оценён положительно. Окончательная приёмка перенесена на M2.1. Шесть подготовленных обращений сохранены локально, отправок в M2 не было.

## M1 · кандидат для приёмки

Локальная ветка `codex/portbridge-v3-m1` начата от `5129e43`. Разбор 35 предупреждений, проверки восстановления, статусы требований и ограничения зафиксированы в [отчёте M1](PORTBRIDGE-M1.md). [Реестр требований](PORTBRIDGE-CHECKLIST.md) различает локальную проверку, межмодульную приёмку и проверку после публикации.

Владелец предварительно принял отчёт M1 и разрешил M2. Независимый аудит пакета M0–M1 и публичная эксплуатационная приёмка открыты. Публикация и наблюдение на GitHub требуют отдельного разрешения.

## M0 · исходная точка

Сверка 26 ноября 2026 UTC. Этап M0 завершён локально. Исходный HEAD `56e2262d62c492f4a866c350f3f708c3f694f77f` совпал с публичным `main` и тегом `handover-2026-11-26`. Ветка работы `codex/portbridge-v3-m0` создана от чистой восстановленной копии, где `origin` указывает на автономный bundle. Внешняя папка передачи содержит отдельный пустой Git-репозиторий. Прежняя рабочая копия на `d78d300` содержала изменённый журнал и незарегистрированный `HANDOFF.md`. Для M0 использованы исходники точного релиза, прежнее рабочее дерево сохранено. [Релиз](https://github.com/akimfomin/PortBridge/releases/tag/handover-2026-11-26)

[Спецификация](PORTBRIDGE-SPEC.md) сохранена побайтно. SHA-256 `152a0e916772f2d2dbd1ea664077ef449ac951823af16f7c00b3a843ae14a34d`. [Реестр](PORTBRIDGE-CHECKLIST.md) и [план](PORTBRIDGE-PLAN.md) задают точку продолжения.

## Карта текущего проекта

| Путь | Роль на проверенной версии |
| --- | --- |
| [`portbridge/github.py`](../portbridge/github.py), [`catalog.py`](../portbridge/catalog.py), [`data/`](../portbridge/data) | Сбор issues/PR/коммитов/запусков GitHub, кэш страниц и история, SQLite, исходные проверенные карточки, задачи и связи. |
| [`matching.py`](../portbridge/matching.py), [`preflight.py`](../portbridge/preflight.py), [`preflight_index.py`](../portbridge/preflight_index.py), [`public_browse.py`](../portbridge/public_browse.py) | Межпроектные кандидаты, точный контекст PR, публичные сегменты поиска и навигация по наблюдениям. |
| [`activity.py`](../portbridge/activity.py), [`radar.py`](../portbridge/radar.py), [`lab.py`](../portbridge/lab.py), [`lab_reports.py`](../portbridge/lab_reports.py) | Лента активности, кандидаты к проверке, проверенные запросы, сбор и ревью отчётов. |
| [CLI / localhost API](../portbridge/__main__.py), [MCP](../portbridge/mcp.py), [export](../portbridge/export.py), [static](../portbridge/static) | Один каталог, локальный API, публичный статический экспорт, потребители CLI/MCP/Action. API/снимок имеют версию 1 и разные маршруты чтения. |
| [Обмен](EXCHANGE-API.md), [Action](GITHUB-ACTION.md), [Workflows](../.github/workflows) | Закрытая очередь требует отдельного добровольного подключения. Четыре публичных workflow активны по API. Pages, intake, one-PR пилот и ручные приглашения имеют собственные условия. |
| [Тесты](../tests), [исследования](../research), [вклады](../contrib), [решения](decisions) | Автоматические проверки приложения и фиксированные корпуса. Исследования и вклады содержат отдельные ревизии, лицензии и аппаратные ограничения. |

Прочитаны [правила](../AGENTS.md), [README](../README.md) и [README.ru](../README.ru.md), [финальный аудит](FINAL-AUDIT.md), [журнал](COMMUNITY-COORDINATION.md), [пассивное сопровождение](PASSIVE-MAINTENANCE.md), [поиск](SEARCH-EVALUATION.md), [MCP](MCP.md), [Action](GITHUB-ACTION.md), [запросы](TEST-REQUESTS.md), [Lab](TEST-LAB.md), [промпт](AGENT-PROMPT.md), [закрытый обмен](EXCHANGE-API.md) и [приоритеты](WORK-PRIORITIES.md). Дополнительный контекст дают [Quickstart](QUICKSTART.md), [пилот](PILOT.md), [карта проектов](PROJECTS.md) и [руководство сопровождающего](MAINTAINERS.md).

Текущий поток: GitHub → кэш и SQLite → карточки/связи/отчёты → версионированные JSON → Pages, CLI, MCP, Action. Обсуждения и проверенные решения Lab имеют отдельный вход через GitHub Issues. [Целевая диаграмма](PORTBRIDGE-SPEC.md#4-сквозная-архитектура-и-модель-данных)

## Baseline

Python 3.12.14, SQLite 3.53.1, Node 24.22.1. Команды из корня репозитория, с отдельной базой для локального снимка.

| Проверка | Результат и ограничение |
| --- | --- |
| `python -B -m unittest discover -s tests -q` | 197/197 на исходном HEAD, 198/198 с исправлением. |
| `python -B -m unittest discover -s tests -p test_portbridge.py -k test_health_keeps_the_last_success -v` | До исправления 1 падение: дата PR исчезла. После 1/1: сохранённое время, ошибка, первая загрузка и восстановление. Дополнительно проверен экспорт после сохранённого успеха и нового сбоя: оба health JSON показывают ошибку и прежнее время. [Тест](../tests/test_portbridge.py) |
| `python -B -m portbridge --db .portbridge/m0/seed.sqlite3 export --out .portbridge/m0/dist --repository akimfomin/PortBridge` | Успешно. База 311 296 байт. Экспорт 262 файла, 1 562 455 байт. Размер приведён для чистой базы с исходной подборкой, без сетевого обогащения. |
| `python -B -m portbridge --db .portbridge/m0/seed.sqlite3 serve --offline --port 8765`; `python -B -m http.server --directory .portbridge/m0/dist --bind 127.0.0.1 8766` | В Chrome 6 маршрутов с данными: локальный API, статическая лента, RU Lab по прямой ссылке, статический поиск PB-0011, публичная лента и публичный RU Lab. Ширины 1365 и 390, без горизонтального переполнения и исключений JS. У статической страницы ожидаемый 404 попытки локального API перед переходом на снимок. Браузер также запросил отсутствующий favicon. Процессы остановлены. Полный аудит доступности и всех ссылок остаётся в UX. |
| `node --check portbridge/static/app.js` | Успешно. |
| `python -B -m portbridge.benchmark tests/fixtures/search-evaluation-v1.json` | 184 записи, 10 задач: PortBridge 8/10, только заголовки 7/10, технические признаки 7/10, попадание в первые пять. Q06 и Q09 пропущены. В опубликованном предыдущем замере PortBridge 7/10, GitHub 8/10. Живой GitHub Search здесь заново не замерялся. [Предыдущий замер](SEARCH-EVALUATION.md#первый-замер) |
| `python -B -m portbridge.preflight --url https://github.com/LooperSalty/AnyXboxX/pull/133 --limit 3` | PR индексирован, найдена карточка PB-0011, состояние каталога partial. Это одна проверка точного URL. |
| `python -B -m portbridge.exchange_demo` | Локальная демонстрация прошла, неавторизованное ревью получило 403. Результаты демо синтетические. |
| `git diff --check` | Успешно. |

### Публичный снимок / Published snapshot

Сверка около 05:18 UTC. Публикация `02:39:28Z`, попытка сбора `02:38:47Z`, состояние `partial`. Браузер показал, что данным больше двух часов. Из 45 источников 37 `ok`, один `partial`, один `stale`, шесть `unavailable`. Видны 35 предупреждений, 23 600 наблюдений и 81 742 автоматически рассчитанные пары. Radar в этом снимке предлагает шесть аппаратных проверок и шесть сравнений источников. Точность Radar пока не измерена. Reforge по исходному API вернул HTTP 404. Для XCL последняя успешная загрузка `02:38:01Z`, для FrameLab `02:37:23Z`. [Health](https://akimfomin.github.io/PortBridge/data/health.json) · [Manifest](https://akimfomin.github.io/PortBridge/data/site.json) · [Activity](https://akimfomin.github.io/PortBridge/data/activity.json) · [Browse counts](https://akimfomin.github.io/PortBridge/data/browse-66b61c0592212a6619247bf2-index.json)

Test Lab: 16 задач, 6 `needs_run`, 5 `awaiting_review`, 4 `needs_revision`, 1 `blocked`. Снимок пометил результаты сканирования всех 16 задач как fresh на время проверки источников. Общая отметка проверки `00:58:50Z`, в задачах видны четыре записи отчётов. Локальный seed показывает 10/4/1/1 соответственно, поскольку он не загружает публичные отчёты. [Lab JSON](https://akimfomin.github.io/PortBridge/data/lab.json) · [Условия ревью](TEST-LAB.md)

### Автоматика / Operations

В публичном репозитории 87 веток, 20 открытых issues и 4 PR по API, 2 звезды и 1 форк. Среди текущих записей #78 и #84–87, а также канал передачи #91. Из опубликованных запусков #143 на `56e2262` завершил сборку, Pages и сверку публичного JSON. Прочитаны журнал сборки и журнал сверки через GitHub connector. Сборка показала 197 тестов, восстановленный SQLite-кэш и предупреждения GitHub 404. Загруженный артефакт Pages весил 45 080 930 байт по API, размер публичной SQLite-базы неизвестен. Cloudflare пропущен. #144 и #145 пропущены по фильтру комментариев. [Запуск #143](https://github.com/akimfomin/PortBridge/actions/runs/45743531751) · [№145](https://github.com/akimfomin/PortBridge/actions/runs/45747698034) · [Issues](https://github.com/akimfomin/PortBridge/issues) · [PR](https://github.com/akimfomin/PortBridge/pulls)

Запланировано на :13 и :43 UTC. Доступны успешные scheduled runs #53, #55, #93, #129, интервалы около 7 ч 04 мин, 10 ч 22 мин и 8 ч 40 мин. На момент сверки с #129 прошло более пяти часов. Это исходное измерение, а недельное наблюдение и проверка восстановления остаются в M1/M6. Из наблюдения невозможно установить причину пропуска конкретного запуска. [История](https://github.com/akimfomin/PortBridge/actions/workflows/pages.yml) · [Расписание GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Участие, обязательства, неизвестные данные

- AnyXboxX #203 влит, автор KainanP. Отчёты FrameLab #15 и XCL #2584 разделены с состояниями задач и слияний. Continued #1713 и XCL #2322 открыты без merge. PortBridge #78 открыт, аппаратные пробы ещё требуют подтверждения. Проверенные роли и открытые вопросы приведены в [журнале](COMMUNITY-COORDINATION.md). [AnyXboxX #203](https://github.com/LooperSalty/AnyXboxX/pull/203) · [FrameLab #15](https://github.com/5headsmartbtw/leonida-framelab/issues/15) · [XCL #2584](https://github.com/xcl-dev/xcl/issues/2584) · [Continued #1713](https://github.com/ubiquitarianism/leonida/pull/1713) · [XCL #2322](https://github.com/xcl-dev/xcl/pull/2322) · [PortBridge #78](https://github.com/akimfomin/PortBridge/pull/78)
- Yoshi-233 самостоятельно описал пользу ссылок PortBridge в своей независимой проверке AnyXboxX. Это конкретное внешнее свидетельство. Цель трёх команд с повторными техническими событиями остаётся неподтверждённой. Внешние установки Action/MCP, экономия времени и облачная стоимость по фактическим счетам неизвестны. [Отзыв](https://github.com/akimfomin/PortBridge/issues/91#issuecomment-7181534388)
- Подготовлено шесть локальных английских черновиков, включая условные предложения. Учитываются прежние контакты, отказ PC Race и отсутствие ответа PortWatch VI. Отправок в M0 — 0. [Правила сотрудничества](PORTBRIDGE-OUTREACH.md)

## Решения и откат

- Чистая ветка с точного релиза позволяет сверять изменения без смешивания с работой из старой папки.
- Исправление `9b80d21` сохраняет последнее успешное время отдельно для каждого канала при ошибке новой попытки. Текущее состояние и размер ответа сохраняются как пришли. При успехе дата обновляется. Формат SQLite и JSON той же версии. Для локального отката кода подходит `git revert 9b80d21` на чистой рабочей ветке.
- Публичный сайт остаётся на релизе передачи. Запись в GitHub, разрешения, развёртывание и обращения требуют отдельного одобрения.
- Первый срез M1 продолжил работу с попыткой и последним успехом, replay и восстановлением снимка. [Критерии](PORTBRIDGE-PLAN.md#следующий-срез-m1)

## English

M0 is complete on the local `codex/portbridge-v3-m0` branch. The public handover release served the existing site at the time of inspection. The baseline passed 197 tests, and the feed freshness fix passed 198 tests including a regression. Public source health remains partial, with four observed scheduled runs several hours apart. The M1 report has provisional owner acceptance. Its independent audit and operational acceptance remain open. The local M2 search and Discovery candidate is ready for review before M3.
