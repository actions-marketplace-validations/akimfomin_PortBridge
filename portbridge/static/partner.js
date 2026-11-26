'use strict';

(async function partnerWidget() {
  const query = new URLSearchParams(location.search);
  const ru = query.get('lang') === 'ru';
  const text = (en, russian) => ru ? russian : en;
  const notice = document.querySelector('#partner-status');
  const list = document.querySelector('#partner-items');
  const filters = {
    project: query.get('project') || '', console: query.get('console') || '', kind: query.get('kind') || '',
  };
  document.documentElement.lang = ru ? 'ru' : 'en';
  document.querySelector('#partner-title').textContent = text('PortBridge technical work', 'Проверки и результаты PortBridge');
  const home = document.querySelector('#partner-home');
  home.textContent = text('Open PortBridge', 'Открыть PortBridge');
  if (ru) home.href = './start.ru.html';

  async function read(path) {
    const result = await fetch(path, {credentials: 'omit', cache: 'no-cache'});
    if (!result.ok) throw new Error('Source unavailable');
    return result.json();
  }

  try {
    if (filters.project && !/^[a-z0-9][a-z0-9-]{0,60}$/.test(filters.project)
        || !['', 'xbox-series', 'ps5'].includes(filters.console)
        || !['', 'task', 'result'].includes(filters.kind)) throw new Error('Invalid filter');
    let data;
    try {
      const manifest = await read('./data/site.json');
      const filename = manifest.snapshots?.partner;
      if (!/^partner-[0-9a-f]{24}\.json$/.test(filename)) throw new Error('Invalid snapshot');
      data = await read('./data/' + filename);
    } catch {
      const params = new URLSearchParams(Object.entries(filters).filter(([,value]) => value));
      params.set('limit', '10');
      data = await read('/api/v1/partner?' + params);
    }
    if (data.schema_version !== 1 || !Array.isArray(data.items)) throw new Error('Invalid snapshot');
    const stale = Date.now() - Date.parse(data.generated_at) > 48 * 3600000;
    const chosen = data.items.filter(item => (!filters.project || item.projects.includes(filters.project))
      && (!filters.console || item.consoles.includes(filters.console)) && (!filters.kind || item.kind === filters.kind))
      .slice(0,10);
    notice.textContent = chosen.length ? (stale ? text('Older public snapshot', 'Снимок требует обновления')
      : text('Public sources · PortBridge', 'Публичные источники · PortBridge'))
      : text('No items match these filters.', 'По этим фильтрам результатов пока нет.');
    for (const item of chosen) {
      if (!/^#\/(lab|impact)\?[A-Za-z0-9%_.+&=-]+$/.test(item.link)) continue;
      const line = document.createElement('li');
      const link = document.createElement('a');
      link.textContent = item.title;
      link.href = './' + (ru ? '?lang=ru' : '') + item.link;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      const state = {available: text('Lab task', 'Задание Lab'),
        check_source: text('Check source status', 'Уточните состояние источника'), accepted: text('Accepted', 'Принято'),
        reviewed: text('Reviewed', 'Проверено')};
      line.append(document.createTextNode((state[item.state] || '') + ' · '), link);
      list.append(line);
    }
  } catch {
    notice.textContent = text('The public feed is unavailable. Use the main catalog when it is reachable.',
      'Лента временно недоступна. Откройте основной каталог, когда он станет доступен.');
  }
})();
