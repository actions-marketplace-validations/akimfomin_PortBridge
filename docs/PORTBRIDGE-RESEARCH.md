# PortBridge 3.0 · журнал исследований / Research log

## Что уже есть / Existing evidence

История, отрицательные результаты и аппаратные ограничения сохранены в [аудите](FINAL-AUDIT.ru.md), [исходниках исследований](../research) и [описи](engineering-inventory.json). Поиск на старом корпусе из 184 записей повторён для M0. Сводка, команды и ограничения — в [baseline](PORTBRIDGE-STATUS.md#baseline). Семь внешних запросов зафиксированы отдельно в [результатах оценки поиска](SEARCH-EVALUATION.md#точность-внешнего-поиска-по-семи-техническим-запросам).

## Первичная проверка / Initial screening

| Кандидат | Проверенное в M0 | Решение для сравнения |
| --- | --- | --- |
| SQLite FTS5 | В Python 3.12.14 на SQLite 3.53.1 успешно создана таблица FTS5 в памяти. Документация описывает BM25 и настройку токенизации. SQLite распространяется как public domain. [Документация](https://www.sqlite.org/fts5.html) · [лицензия](https://www.sqlite.org/copyright.html) | Сравнить с текущим поиском на одном корпусе в M2. Измерить символы GPU/API, точные ID, размер базы, время индексации и p95. |
| Git patch-id | В окружении Git 2.56.0.windows.4. Документация показывает режимы stable/verbatim и ограничения эквивалентности патчей. Git — GPL-2.0. [Команда](https://git-scm.com/docs/git-patch-id) · [лицензия](https://github.com/git/git/blob/v2.56.0/COPYING) | Проверить совпадение на атрибутированных переносах и отрицательных парах. Оценить вызов существующего Git без копирования кода и отдельно отмечать общий предок. |
| FastEmbed | Рассмотрены входы и зависимости по документации проекта. Для варианта нужно отдельно закрепить релиз пакета, ревизию и условия конкретной модели. [Исходники](https://github.com/qdrant/fastembed) | M2 сравнивает lexical-only и гибрид на holdout. Замерить CPU, память, загрузку модели, офлайн-поведение и ложные совпадения. В M0 модель не загружалась. |

Следующие сравнения: Sourcegraph и поисковые решения для PR/Issues в M2, KernelCI и labgrid для Lab в M3, CHAOSS/Augur/GrimoireLab для People и Impact в M4, MCP/Actions/Apps и opt-in оркестрация в M5–M6. Полный список в [§6](PORTBRIDGE-SPEC.md#6-обязательное-исследование-аналогов-и-повторное-использование). Для каждого прототипа сохранить точную ревизию, исходники, лицензию, команды, сырые измерения и причину выбора.

## M2 · аналоги и эксперименты

| Компонент | Проверенная версия и лицензия | Польза, стоимость и решение |
| --- | --- | --- |
| Sourcegraph и Zoekt | Zoekt `c639b2fafda5f63a072d6ab0fb7bb7da71c1e2ec`, Apache-2.0. Документация Sourcegraph прочитана 26 ноября. [Zoekt](https://github.com/sourcegraph/zoekt/tree/c639b2fafda5f63a072d6ab0fb7bb7da71c1e2ec) · [синтаксис Sourcegraph](https://sourcegraph.com/docs/code-search/queries) | Символы, регулярные выражения и триграммы подходят для сплошного поиска по коду. Синхронизация репозиториев требует Go-инструментов, диска и обслуживания. Для M2 выбран точный поиск по символам и фильтрам в ограниченном корпусе с проверяемой применимостью. |
| Doppelganger | `3e45602468d9b12f83bc70d022ba2095be5dbdbf`. Файл LICENSE на ревизии недоступен, лицензия для копирования не подтверждена. [Исходник](https://github.com/dannyl1u/doppelganger/tree/3e45602468d9b12f83bc70d022ba2095be5dbdbf) | App сравнивает issue/PR с MiniLM и ChromaDB, для закрытия и комментариев нужны права записи. По этому примеру оценили локальные векторы. Модель, хранилище и App в продукт не добавлялись. |
| PR Prism | `12c8ef11d2cf4cb1e0ed79200cf5b44ee0a70e3c`, MIT. [Исходник](https://github.com/StressTestor/pr-prism/tree/12c8ef11d2cf4cb1e0ed79200cf5b44ee0a70e3c) | Группирует PR для triage. Требует Node-инструмента и доступа к репозиториям. Для M2 полезно различать дубликат и технически сходную самостоятельную работу. Заявленный масштаб работы самостоятельно не воспроизводился. |
| Repo Assistant AI | `53274f1ecbe8160bc23ac905de9af1dbd4bad87b`, ISC. [Исходник](https://github.com/guillermoscript/repo-assistant/tree/53274f1ecbe8160bc23ac905de9af1dbd4bad87b) | Использует pgvector, embeddings и LLM для решения о duplicate и действий в GitHub. Полезен порог для поиска, однако база, модель и права GitHub увеличивают цену ошибочной выдачи. Для M2 выбран формат подсказки с источником. |
| SQLite FTS5 | SQLite 3.53.1, public domain. [FTS5 и BM25](https://www.sqlite.org/fts5.html) · [лицензия](https://www.sqlite.org/copyright.html) | Воспроизведён на штатном SQLite, база 36 КиБ. Высокая полнота сопровождается 13 размеченными ложными совпадениями и выдачей по семи из 12 отрицательных контролей. Сохранён для сравнения. |
| FastEmbed и SVD | FastEmbed `2099c36036115e689ea9b3b5bf1aafa79dc01190`, Apache-2.0. Прототип TF-IDF/SVD использует NumPy 2.3.5, BSD-3-Clause. [FastEmbed](https://github.com/qdrant/fastembed/tree/2099c36036115e689ea9b3b5bf1aafa79dc01190) · [SVD](https://numpy.org/doc/2.3/reference/generated/numpy.linalg.svd.html) · [лицензия NumPy](https://github.com/numpy/numpy/blob/v2.3.5/LICENSE.txt) | FastEmbed требует модели и её отдельной лицензии. Модель не загружалась. Прототип с восемью признаками, порогом cosine 0,21 и 36 КиБ векторов дал 92,5% полноты и 15 ложных совпадений. Подготовка около 11 мс. В продукте остались смысловые группы на стандартной библиотеке. |
| Git patch-id | Git 2.56.0.windows.4, GPL-2.0. [Документация](https://git-scm.com/docs/git-patch-id) · [лицензия](https://github.com/git/git/blob/v2.56.0/COPYING) | Системный Git сравнивает два локальных diff до 256 КиБ. Проверено равенство при смене положения строки и различие содержимого. Общий предок выводится отдельно от равенства патчей. |

Технический корпус сохраняет ревизии, лицензии и исходные ограничения. Исходный код внешних проектов не переносился. Привычный поиск остаётся полезен для проверки символа и поиска новых обсуждений. [Корпус](../portbridge/data/discovery.json) · [Измерения и 13 задач](PORTBRIDGE-M2.md)

KernelCI и labgrid относятся к проверке Lab. CHAOSS/Augur и GrimoireLab — к People и Impact. Права App, сервисы обмена и оркестрация остаются для следующих этапов.

## English

The M0 baseline reruns the existing offline search benchmark. SQLite FTS5 is available in the local runtime. FTS5, Git patch IDs and FastEmbed are comparison candidates. No code or model was imported for M0. Later evaluations will record pinned versions, licenses, resource costs and negative results alongside the evidence.
