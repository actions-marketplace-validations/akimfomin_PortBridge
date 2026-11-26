# PortBridge · дополнение наблюдения PlayStation 5

Дополнение владельца к M3. [Реестр Master Spec V3 и Discovery](PORTBRIDGE-CHECKLIST.md) сохраняет все 122 исходных ID. Условия ниже ведутся отдельно, чтобы не менять нумерацию реестра.

| ID | Условие | Этап и состояние |
| --- | --- | --- |
| PS5-01 | Проверять публичные проекты совместимости PS5. Хранить источник, точную ревизию, лицензию, статус доступа, связь с upstream и предел проверенной применимости. | M3. Семь источников проверены. Два включены в регулярное наблюдение публичных метаданных. |
| PS5-02 | Различать Xbox Series, PS5 и общие технические компоненты. Передавать платформы через Search, Discovery, Radar и Lab. События должны сохранять эту связь для People и Impact. | M3. Индекс, находки и карточки передают поля платформы. Для межплатформенных связей нужен отдельный контроль. |
| PS5-03 | Проверять общие механизмы RDNA2, компиляторов, Vulkan, текстур, памяти и синхронизации. Учитывать лицензию и происхождение перед любым переносом. | M3. Исходники и допущения сверены. Независимые прогоны применимости остаются открытыми. |
| PS5-04 | В дальнейшем отразить публичное техническое участие и добровольные компетенции руководителей, разработчиков и тестировщиков PS5. Предлагать партнёрства только после разрешения. | People, Impact и outreach на своих этапах. В M3 сохранены стабильные идентификаторы и роли. |
| PS5-05 | Использовать законно опубликованные исходники, документацию и синтетические тесты. Закрытые игровые файлы, исполняемые файлы и ключи не принимаются в Lab и не служат источником Discovery. | Действует с M3. Лицензии репозитория и отдельных файлов проверяются по первоисточникам. |

## Публичные проекты

| Проект | Что подтверждено |
| --- | --- |
| [AnyPS5](https://github.com/boykopovar/AnyPS5) | Публичный проект совместимости PS5. Проверены GPL-2.0 и код теста Wave32, компилятора и Vulkan. [Закреплённый README](https://github.com/boykopovar/AnyPS5/blob/0b16257796508b77472154e48c927d6fc4035d26/README.md) |
| [KytyPS5](https://github.com/KytyPS5/KytyPS5) | C++/Vulkan для PS5. README указывает Windows, Linux и экспериментальный macOS. Проверены GPL-2.0 и исходник кэша текстур. [Закреплённый README](https://github.com/KytyPS5/KytyPS5/blob/93cce66564bdced2fc7054ca9794451dfeef4d9d/README.md) |
| [GTAVI-Recomp](https://github.com/JamesCicada/GTAVI-Recomp) | Проект исследования одной предполагаемой игры. README указывает незавершённые компоненты и ссылку на AnyPS5. Проверен текст GPL-2.0. Работа с файлами игры не проводилась. [Закреплённый README](https://github.com/JamesCicada/GTAVI-Recomp/blob/0b332f88343b0fdebf20a640a5c625a2132a521b/README.md) |
| [KytyPs5-GTA-VI](https://github.com/ZazaJr24/KytyPs5-GTA-VI) | Публичная страница 26 ноября вернула HTTP 404. Состояние проекта, лицензия и возможный переезд не установлены. |
| [InoriRus/Kyty](https://github.com/InoriRus/Kyty) | Исторический проект PS4 и PS5, MIT. Возможен поиск прежних архитектурных решений. [Закреплённый README](https://github.com/InoriRus/Kyty/blob/4733b7e1c91b10554a52007903d74dc76c39a230/README.md) |
| [Jetsku/KytyPS5](https://github.com/Jetsku/KytyPS5) | README прямо описывает происхождение от KytyPS5 и собственные доработки. GitHub в проверке не отметил проект платформенным форком. Текст GPL-2.0 доступен. [Закреплённый README](https://github.com/Jetsku/KytyPS5/blob/dd9f9901dbafc5419a8f8e98b8bda0eb80492b2c/README.md) |
| [craziiEmu](https://github.com/craze1pirate/craziiEmu) | Экспериментальный C# проект для Windows с Vulkan. Проверен текст GPL-2.0. Сведения README о совместимости остаются заявлениями проекта. [Закреплённый README](https://github.com/craze1pirate/craziiEmu/blob/cdd12d697e75d0dab9ad3d5ffa79d96930e4242f/README.md) |

## Возможные общие проверки

| Механизм | Как сравнить | Где нужна отдельная проверка |
| --- | --- | --- |
| RDNA2 и Wave32 | Сравнить поведение операций внутри половины аппаратной подгруппы синтетическими масками и перестановкой полос. Использовать контроль из AnyPS5 и изолированный пример Xbox. [AnyPS5 Wave32](https://github.com/boykopovar/AnyPS5/blob/0b16257796508b77472154e48c927d6fc4035d26/core/libs/tests/Wave32WideSubgroup.cpp#L149) · [AnyXboxX #334](https://github.com/LooperSalty/AnyXboxX/pull/334) | Размер волны хоста и консоли, правила масок и перенос между половинами Wave64. |
| Шейдерные компиляторы | Общее контрольное задание может проверять таблицу результатов инструкции на границах ±0, NaN и переполнения, а также валидность выходного кода. [PS5 recompiler](https://github.com/boykopovar/AnyPS5/blob/0b16257796508b77472154e48c927d6fc4035d26/core/shader/recompiler/Recompiler.cpp) · [VIctory #3056](https://github.com/Marvisak/VIctory/pull/3056) | SPIR-V и DXIL имеют разные правила типов и шейдерных ресурсов. Источник каждого opcode и лицензия файла сверяются перед переносом. |
| Vulkan и синхронизация | Сопоставить aspect/mip/layer и пары stage/access по синтетической картинке с перекрывающимися диапазонами. [AnyPS5 PlaceholderImages](https://github.com/boykopovar/AnyPS5/blob/0b16257796508b77472154e48c927d6fc4035d26/core/libs/prx/libSceAgcDriver/Graphics/src/PlaceholderImages.cpp#L51) · [Continued #1713](https://github.com/ubiquitarianism/leonida/pull/1713) | Передача владения очередью, данные layout и ожидание fence зависят от backend. |
| Текстуры | Сравнить набор маленьких синтетических изображений по размеру блока, row pitch, mip и слою. [KytyPS5 texture cache](https://github.com/KytyPS5/KytyPS5/blob/93cce66564bdced2fc7054ca9794451dfeef4d9d/src/graphics/host_gpu/renderer/cache/textureCache.cpp#L958) · [Continued #461](https://github.com/ubiquitarianism/leonida/pull/461) | Разметка ресурсов AGC и Xbox XG проверяется отдельно. Совпадение размера блока само по себе не подтверждает совместимость layout. |
| Память и время жизни | Выделять и освобождать искусственные ресурсы при контролируемом бюджете, отдельно измерять освобождение после завершения работы GPU. [AnyPS5 Resources](https://github.com/boykopovar/AnyPS5/blob/0b16257796508b77472154e48c927d6fc4035d26/core/libs/prx/libSceAgcDriver/Graphics/src/Resources.cpp#L104) · [AnyXboxX #354](https://github.com/LooperSalty/AnyXboxX/pull/354) | Vulkan memory type и DXGI budget имеют разные API. Совместимость физической памяти и ограничений драйвера требует прогона на принимающей архитектуре. |

Автоматический прогон на свежих PR нашёл [AnyPS5 #25660](https://github.com/boykopovar/AnyPS5/pull/25660) из [AnyXboxX #317](https://github.com/LooperSalty/AnyXboxX/pull/317). В обоих обсуждениях есть `v_readfirstlane_b32`. AnyPS5 расширяет чтение с узкой аппаратной подгруппы до гостевой Wave32. AnyXboxX сравнивает гостевую Wave64 с двумя аппаратными половинами по 32. Совпадение остаётся в исследовательской выдаче без назначения. Поиск с PS5 отдельно вернул исходники XCL и Continued по этому символу. Повторный цикл пропустил неизменные события.

Записи наблюдения и лицензии доступны в [конфигурации](../portbridge/data/console_sources.json). Для первичного обмена предлагаются ссылки на проверенные публичные работы, выбор наблюдаемого условия и самостоятельно написанный синтетический тест. Перенос кода возможен только после проверки происхождения, условий конкретных файлов и совместимости лицензий. Числа из README остаются данными авторов.
