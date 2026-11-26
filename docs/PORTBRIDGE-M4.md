# M4 · People и Impact

People связывает публичные технические действия с GitHub-аккаунтами, проектами и задачами Xbox Series и PS5. Impact фиксирует проверенные действия с раздельным авторством. [Реестр](PORTBRIDGE-CHECKLIST.md) · [Расширение PS5](PORTBRIDGE-PS5-SPEC.md) · [Правила данных](decisions/016-community-evidence.md)

## Карта участников

GitHub показывает LooperSalty владельцем AnyXboxX, boykopovar владельцем AnyPS5, xcl-dev и KytyPS5 организациями. LooperSalty также подписал ревью AnyXboxX #133. 5headsmartbtw подписал решение по FL-07. GeorgiyDemo независимо проверил перенос Continued на Apple M5 Pro. malekaifa открыл AnyPS5 #25660, mihiii1337 и другие участники внесли ревью. Discovery связал механизм с работой erizheng-amd и ревью LLVM. Роль в работе ограничена её источником. [AnyXboxX #133](https://github.com/LooperSalty/AnyXboxX/pull/133#pullrequestreview-6041873843) · [FrameLab](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587) · [Отчёт Continued](https://github.com/ubiquitarianism/leonida/pull/701#issuecomment-7131731339) · [AnyPS5](https://github.com/boykopovar/AnyPS5/pull/25660) · [LLVM](https://github.com/llvm/llvm-project/pull/234715)

Дата, область, источник и уверенность видны рядом с ролью. Граф отмечает конкретное ревью, техническую связь, тест и перенос. Специализация выводится из тем публичных работ. Карта поддерживает фильтры проекта, платформы, периода и специальности. Мобильное представление показывает компактный список связей. Доступность для тестов возникает только по отдельному согласию с датой окончания.

## Исправления истории

| Проверка | Уточнённый результат |
| --- | --- |
| AnyXboxX #129 фигурировал среди принятых передач. | GitHub указывает Skyfrye автором собственного изменения команды. PortBridge не получил кредит за реализацию. [Первичный PR](https://github.com/LooperSalty/AnyXboxX/pull/129) |
| Автор принимающего PR мог выглядеть автором исходного D16 в Continued #701. | Оригинал написал ecox982745, akimfomin подготовил перенос, abnalstlll-byte провёл ревью, GeorgiyDemo проверил. PR открыт. [Оригинал](https://github.com/ecox982745/Leonida/commit/a300ba63d1a9a4cdfde1d64f136728545b4ab7b8) · [Принимающий PR](https://github.com/ubiquitarianism/leonida/pull/701) |
| Два самостоятельных аппаратных отчёта FrameLab могли удвоить число добровольцев. | JoeY54 выполнил оба прогона. Второе устройство — встроенная графика Ryzen 9 9950X3D. [Решение FrameLab](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587) |
| Статус closed не устанавливает факт принятия. | AnyXboxX #133 принят, Continued #1026 закрыт без слияния, itsSio #9 — открытый черновик. Его актуальный head отличается от измеренного. [AnyXboxX](https://github.com/LooperSalty/AnyXboxX/pull/133) · [Continued](https://github.com/ubiquitarianism/leonida/pull/1026) · [itsSio](https://github.com/itsSio/xcl/pull/9) |

## Истории Impact

- KainanP использовал измерение Lyrnc в AnyXboxX #133. PortBridge подготовил запрос, LooperSalty подписал ревью, GitHub подтвердил слияние. [Измерение](https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663) · [Применение](https://github.com/LooperSalty/AnyXboxX/pull/133#issuecomment-7136721736)
- clquwu включил оптимизацию Vulkan в Leonida Ultimate с указанием исходной работы Continued. Исходный PR остаётся открытым. [Оригинал](https://github.com/ubiquitarianism/leonida/pull/1713) · [Принимающий коммит](https://github.com/clquwu/leonida-ultimate/commit/e7124f97bff187968a30931fb31e7c42bd88622b)
- FrameLab применил Test Lab в отдельной задаче и сослался на него в документации. Это один подтверждённый случай использования. Звёзды, упоминания и пробные запуски Action в PortBridge отражаются отдельно. [Документация FrameLab](https://github.com/5headsmartbtw/leonida-framelab/blob/1b1c3cfc371225cd020bf4bfbba50e8c696a86f1/docs/evidence/independent-vulkan-handoff.md)
- JoaoPauluu опубликовал три отрицательных результата на Linux с vkd3d-proton 3.1. Kalmarv сравнил другую версию. Причина остаётся открытой. [Первичный отчёт](https://github.com/xcl-dev/xcl/pull/2080#issuecomment-7153700167) · [Сверка](https://github.com/xcl-dev/xcl/pull/2080#issuecomment-7154185295)

## Сквозная проверка

На AnyXboxX #354 Discovery самостоятельно запросил историю по бюджету памяти и переиспользовал тот же ответ для victory-fork #1289. Найдены AnyPS5 #4472, KytyPS5 #1395 и wgpu #11065. Radar создал отдельный Lab-черновик по закреплённой паре Xbox. People нашёл автора обеих реализаций и публичных авторов внешних находок. Impact получил результат только после ревью другой учётной записью. Отрицательный сценарий #350 сохранил разные patch-ID. Доброволец и ревьюер сквозного прогона были локальными тестовыми ролями. [AnyXboxX](https://github.com/LooperSalty/AnyXboxX/pull/354) · [AnyPS5](https://github.com/boykopovar/AnyPS5/pull/4472) · [KytyPS5](https://github.com/KytyPS5/KytyPS5/pull/1395) · [wgpu](https://github.com/gfx-rs/wgpu/pull/11065)

Граф связывает AnyXboxX #317 с AnyPS5 #25660 по чтению первой полосы. Авторство и общий механизм закреплены источниками. Разные размеры гостевой волны ограничивают перенос. Связь KytyPS5 #2551 с AnyXboxX #354 тоже исследовательская. [Сравнение PS5](PORTBRIDGE-PS5-SPEC.md) · [KytyPS5 #2551](https://github.com/KytyPS5/KytyPS5/pull/2551)

## Проверка и границы

В проверенном срезе 24 279 публичных записей, 1 500 профилей и 1 859 связей участник–репозиторий. Источники обнаружены для 38 из 47 отслеживаемых проектов. С несколькими репозиториями связаны 259 участников. С PS5 связаны 33, с обеими платформами — 6. В срезе 368 связей работ, включая исторические и исследовательские, и 24 прямых связей ревью. Impact содержит 20 историй и 44 вкладов. Слияния в принимающих проектах включают их собственную работу.

Источники включают сохранённый публичный индекс, восемь свежих выборок PR и отдельно сверенные первоисточники. Дополнительный сбор комментариев и ревью ограничен по запросам и обходит проекты по очереди. Технические роли проверены только в пределах полученных данных. Открыты независимый аудит M0–M3, независимая оценка качества Radar, SEARCH-08 и публичная эксплуатация. Система сохраняет все 122 ID, дополнение PS5 и открытые условия. [План пилота](PORTBRIDGE-M4-PILOT.md)

```sh
python -m portbridge --db catalog.sqlite3 people --console ps5 --specialty shaders
python -m portbridge --db catalog.sqlite3 impact
python -m portbridge --db catalog.sqlite3 refresh-people
python -m portbridge.community_partners --db catalog.sqlite3
```

Браузер показывает People и Impact. В MCP доступны `portbridge_people` и `portbridge_impact`.
