# M2 · поиск и PortBridge Discovery

Локальный кандидат расширяет существующий поиск. Сайт, CLI, API, MCP и сводка Action используют проверенный корпус исторических работ. На 26 ноября 2026 года в нём 23 записи с закреплёнными ревизиями. Карточки содержат задачу источника, сходство, различия, ограничения, лицензию, способ адаптации и проверочный тест. [Корпус](../portbridge/data/discovery.json) · [Карточки на русском](../portbridge/data/discovery.ru.json)

## Попробовать на XCL #2322

Запустите из папки этого кандидата. Команды работают на штатном Python от 3.10 и не требуют токена.

```sh
python -m portbridge.discovery_search --url https://github.com/xcl-dev/xcl/pull/2322
python -m portbridge.discovery_search --q "DXGI adapter LUID" --project dxvk
```

В местном веб-интерфейсе откройте каталог проблем и вставьте ссылку PR. Через MCP вызовите `portbridge_preflight` с полем `url`. API принимает текст, URL и фильтры проекта, типа, состояния, платформы и даты проверки источника. [Быстрый запуск](QUICKSTART.md#try-discovery-locally) · [MCP](MCP.md#работа-без-сети) · [API](../API.md#исторические-решения-discovery)

## Проверенные открытые задачи

Состояние задач подтверждено через GitHub 26 ноября 2026 года. Проверены исходники на указанных коммитах. Аппаратную проверку и решение о применении принимает сторона, работающая над исходной задачей.

| Открытая задача | Внешний первоисточник и применимость | Первый проверочный тест |
| --- | --- | --- |
| [XCL #2584](https://github.com/xcl-dev/xcl/issues/2584) · перенос Wave32 на краях примитивов | [LLVM Whole Quad Mode](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/Target/AMDGPU/SIWholeQuadMode.cpp#L10) даёт эталон расширения маски EXEC. | Сравнить соседние назначения carry на краю треугольника, включая активную и вспомогательную полосы. |
| [XCL #2322](https://github.com/xcl-dev/xcl/pull/2322) · повторное использование scratch | [LLVM StackColoring](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/CodeGen/StackColoring.cpp#L8) и [Mesa ACO](https://gitlab.freedesktop.org/mesa/mesa/-/blob/5c142e46f3f6e752ed745fd48912ebb8fad67145/src/amd/compiler/aco_spill.cpp#L1406) показывают анализ пересечений. У XCL время жизни может охватывать несколько GPU dispatch. | Сравнить данные и расход памяти на парах с пересекающимся и непересекающимся временем жизни. |
| [XCL #2003](https://github.com/xcl-dev/xcl/issues/2003) · тёплый кэш NVIDIA | [Vulkan](https://github.com/KhronosGroup/Vulkan-Docs/blob/dad857284bf63d027ac9d6a97e9a1689831bab0d/chapters/pipelines.adoc#L8000) задаёт заголовок cache blob. [VKD3D-Proton](https://github.com/HansKristian-Work/vkd3d-proton/blob/0d66699b1b1e250ef19d793f2649d9288b0808ff/libs/vkd3d/cache.c#L365) сверяет device ID и UUID. Причина взаимодействия кэшей открыта. | Воспроизвести четыре сочетания холодного и тёплого кэшей приложения и драйвера. |
| [Continued #1713](https://github.com/ubiquitarianism/leonida/pull/1713) · объединение Vulkan-переходов | [DXVK](https://github.com/doitsujin/dxvk/blob/9d6f54a1ade20d1d27dd421024717a636f3d8c68/src/dxvk/dxvk_barrier.cpp#L457) даёт эталон записи барьеров по диапазонам. Эквивалентность слияния требует теста. | Сравнить полные и частичные перекрытия mip/layer, разные layout и передачу между очередями. |
| [Continued #1042](https://github.com/ubiquitarianism/leonida/pull/1042) · спящие потоки при смене режима | [glibc broadcast](https://github.com/bminor/glibc/blob/74f59e9271cbb4071671e5a474e7d4f1622b186f/nptl/pthread_cond_broadcast.c#L38) даёт модель пробуждения. Приложению нужна собственная проверка предиката. | Прогнать смену режима и shutdown по обе стороны входа ожидающего потока. |
| [VIctory #984](https://github.com/Marvisak/VIctory/pull/984) · разные размеры элементов | [DXIL](https://github.com/microsoft/DirectXShaderCompiler/blob/b4711839eb9a87da7c3436d9b212e0492359fbbd/docs/DXIL.rst#L1094) описывает StructureByteStride. [SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools/blob/a62abcb402009b9ca5975e6167c09f237f630e0e/source/val/validate_memory.cpp#L1460) проверяет типы адресации. | Прочитать два ресурса с разными stride и сравнить адреса и значения. |
| [VIctory #2637](https://github.com/Marvisak/VIctory/issues/2637) · WARP перезаписывает библиотеку GPU | [VKD3D-Proton](https://github.com/HansKristian-Work/vkd3d-proton/blob/0d66699b1b1e250ef19d793f2649d9288b0808ff/libs/vkd3d/cache.c#L365) показывает ключ с идентификатором устройства. D3D12 нужна своя проверка адаптера и формата. | Открыть одну сцену на GPU → WARP → GPU и проверить сохранность обеих библиотек. |
| [AnyXboxX #213](https://github.com/LooperSalty/AnyXboxX/issues/213) · Wave64 на NVIDIA Wave32 | [shadPS4](https://github.com/shadps4-emu/shadPS4/blob/9c2f71326a0c09795864a138050ee87ffd2d010f/src/shader_recompiler/backend/spirv/emit_spirv_warp.cpp#L16) показывает операции внутри подгруппы. Для обмена между половинами Wave64 нужна отдельная реализация. | Сравнить shuffle в половине и между полосами 31, 32 и 63. |
| [AnyXboxX #264](https://github.com/LooperSalty/AnyXboxX/issues/264) · чёрный экран под Wine | **Переносимое исправление не найдено.** [Wine D3DCompile2](https://github.com/wine-mirror/wine/blob/b073859675060c9211fcbccfd90e4e87520dc2c2/dlls/d3dcompiler_43/compiler.c#L451) помогает выделить путь legacy DXBC. | На свободном шейдере сравнить флаги, DXBC-сигнатуры и результат при том же feature level. |
| [FrameLab #24](https://github.com/5headsmartbtw/leonida-framelab/issues/24) · сообщение WAW в NGX | **Переносимое исправление не найдено.** [Контроль SyncVal](https://github.com/KhronosGroup/Vulkan-ValidationLayers/blob/7f40c4da068ccd81a426ae4bf355a63e07a106f1/tests/unit/sync_val.cpp#L2468) даёт публичный тест. Граница записи NGX остаётся открытым вопросом. | Сравнить два перекрывающихся доступа с барьером и без него с наблюдаемым случаем в NGX. |
| [victory-fork #55](https://github.com/fxceless/victory-fork/issues/55) · сопоставление LUID адаптера | [DXVK](https://github.com/doitsujin/dxvk/blob/9d6f54a1ade20d1d27dd421024717a636f3d8c68/src/dxgi/dxgi_adapter.cpp#L158) проверяет, валиден ли LUID. У Windows-счётчиков может быть другой источник идентификатора. | Проверить два адаптера, неизвестный LUID и перестановку порядка перечисления. |
| [victory-fork #1243](https://github.com/fxceless/victory-fork/issues/1243) · индексы в группах 2D/3D | [Vulkan LocalInvocationIndex](https://github.com/KhronosGroup/Vulkan-Docs/blob/dad857284bf63d027ac9d6a97e9a1689831bab0d/chapters/interfaces.adoc#L3480) даёт линейный индекс. Раскладка подгруппы проверяется отдельно. | Сверить координаты, локальный индекс и номер полосы на асимметричных группах. |
| [FrameLab #2](https://github.com/5headsmartbtw/leonida-framelab/issues/2) · завершение на другой очереди | [Vulkan release/acquire](https://github.com/KhronosGroup/Vulkan-Docs/blob/dad857284bf63d027ac9d6a97e9a1689831bab0d/chapters/synchronization.adoc#L6981) задаёт контракт. [RPCS3](https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/rpcs3/Emu/RSX/VK/vkutils/sync.cpp#L105) сохраняет поля барьера. | Передать ресурс между двумя управляемыми очередями с ожиданием и с пропуском одного шага. |

Xenia, RADV, оба AMD GPUOpen Memory Allocator и GPUOpen также изучены. Они дают примеры асинхронной сборки pipeline и повторного использования памяти. Закрытые [wgpu #10155](https://github.com/gfx-rs/wgpu/pull/10155) и [SyncVal #7743](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/7743), а также открытый [MoltenVK #2892](https://github.com/KhronosGroup/MoltenVK/pull/2892) доступны с исходным состоянием и закреплённой ревизией. [Журнал исследований](PORTBRIDGE-RESEARCH.md#m2--аналоги-и-эксперименты)

## Сравнение качества поиска

Набор из 71 проверки сохранён в `151c1d3` до реализации ранжирования. Он включает 31 точный PB-ID, восемь ссылок на прежние отчёты и 32 технических запроса. У 20 есть размеченные ответы. У 12 проверяется отказ от рекомендации. Разметку по первоисточникам сделали в этом цикле. Внешняя повторная разметка открыта. [Замороженный набор](../tests/fixtures/discovery-holdout-v1.json)

| Метод | Recall@5 | Precision@5, нижняя граница | MRR | Явные ложные совпадения | Запросы без ответа, где были находки |
| --- | ---: | ---: | ---: | ---: | ---: |
| Совпадение технических слов | 80,0% | 18% | 0,825 | 3 | 2 из 12 |
| Discovery · слова и смысловые группы | 97,5% | 22% | 0,975 | 5 | 2 из 12 |
| SQLite FTS5 / BM25 | 97,5% | 22% | 1,000 | 13 | 7 из 12 |
| Локальные TF-IDF/SVD-векторы | 92,5% | 21% | 0,879 | 15 | 6 из 12 |

Recall@5 — средняя доля ожидаемых источников в первых пяти на 20 запросах с ответами. Precision@5 делит размеченные попадания на пять позиций по каждому положительному запросу. Пустые позиции и источники без оценки балла не добавляют. Явные ложные совпадения считаются по отрицательным меткам. MRR учитывает позицию первого попадания.

PortBridge из `a203e1f` и M2 вернули все 39 точных ссылок и ID первыми. В M1 по умолчанию ещё отсутствовал этот внешний корпус. M2 показал находки по 22 из 32 запросов, включая два без ожидаемого ответа. Гибрид выбран за полноту и меньший шум по сравнению с FTS5 и SVD. Два дополнительных ложных совпадения по сравнению с простым поиском остаются предметом приёмки SEARCH-08.

Обычный GitHub Search вернул 73 результата по 15 запросам к Issues и PR. На той же подвыборке Discovery дал 96,7% Recall@5. Среди результатов GitHub не было точных совпадений с замороженными URL, многие из которых ведут на строки кода и спецификаций. GitHub при этом нашёл полезные обсуждения ограничений stack coloring и обнаружения WAW во вторичных командных буферах. Второй пример добавлен отдельно от контрольной выборки. Сравнение относится к этим запросам и типам источников. [GitHub Search API](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests) · [LLVM #57725](https://github.com/llvm/llvm-project/issues/57725) · [SyncVal #7743](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/7743)

В дополнительной проверке поиск по коду через GitHub-коннектор получил 17 результатов по пяти запросам с заданными репозиториями. Он нашёл те же файлы для LLVM StackColoring и VKD3D-Proton cache.c на других ревизиях. По запросу LUID он также нашёл полезную сверку в VKD3D-Proton. Это сравнение по пути файла, без требования совпасть с выбранной старой ревизией. [LLVM в выдаче](https://github.com/llvm/llvm-project/blob/dcc012829759b85539075386a5e613b4dd772b8f/llvm/lib/CodeGen/StackColoring.cpp) · [VKD3D-Proton в выдаче](https://github.com/HansKristian-Work/vkd3d-proton/blob/71cae091b06571e51446cf2a937f0b04c237c04d/libs/vkd3d/cache.c)

Один замер Windows дал p95 0,122 мс для гибрида, 0,067 мс для слов и 0,037 мс для FTS5 без сети и загрузки приложения. Снимок Discovery занял 77 216 байт. Подготовка признаков заняла около 1,196 мс, сборка FTS5 около 0,57 мс. Разметка и перепроверка источников требуют времени исследователя. Рабочий поиск обходится без фонового обхода репозиториев и платных запросов.

## Сквозные проверки и приёмка

По XCL #2322 браузер, локальный CLI и API, MCP по stdio и сводка Action вернули LLVM StackColoring. Сводка использовала изолированный HTTP-снимок. Нерелевантный PR не получил историческую рекомендацию. Проверены поиск без сети и возврат к встроенной подборке при пропаже версионного снимка. Старый публичный сайт проверен отдельно. [Тесты](../tests/test_discovery_search.py) · [Проверка Action](GITHUB-ACTION.md#verify-a-release-candidate)

На первой проверке чистой копии Windows иногда закрывал соединение до чтения отказа API. Сбой воспроизведён на M1. После исправления отказ с кодом 405 проверен 100 раз подряд. API обрабатывает только короткое тело в пределах заданного времени.

Итоговый прогон в Windows прошёл 213 тестов. Ранжирование Python и браузера совпало на 46 запросах. В Chrome проверены восемь местных маршрутов и два контрольных маршрута старого публичного сайта на экранах 1365 и 390 пикселей.

Подготовлен пилот для одного PR. После согласия сопровождающего он сможет сравнить сводку по XCL #2322 со своим процессом и решить, полезен ли тест с пересекающимся временем жизни. Пилот пока проверен локально, без запуска в чужом репозитории. [Ручной запуск](GITHUB-ACTION.md#try-it-on-one-pull-request)

Кандидат отдаёт структурированную рекомендацию для будущего Radar. Radar и добровольная проверка Lab относятся к M3, атрибуция People и подтверждённое переиспользование Impact — к M4. Независимый аудит M0–M1 и публичная эксплуатационная приёмка M1 остаются открытыми. Следующее решение — приёмка M2 владельцем. [Реестр](PORTBRIDGE-CHECKLIST.md) · [План](PORTBRIDGE-PLAN.md)
