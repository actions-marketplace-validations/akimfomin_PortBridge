/* Offline Discovery ranking over the same frozen fields used by the Python API. */
const PortBridgeDiscovery = (() => {
  const stop = new Set(('the a an to for of at in on and or is was does are how do need which what one use'
    + ' from by as with into this that same different without when gpu cpu vulkan linux windows'
    + ' xbox series source data problem candidate pipeline cache shader buffer test code work state'
    + ' для где как что это с в на и или по').split(' '));

  function words(value) {
    return value.toLowerCase().match(/[a-zа-яё0-9]+(?:[_.:+-][a-zа-яё0-9]+)*/g) || [];
  }

  function sourceKey(url) {
    if (typeof url !== 'string') return '';
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password
        || !['github.com', 'gitlab.freedesktop.org'].includes(parsed.host)) return '';
      return parsed.host + parsed.pathname.toLowerCase().replace(/\/+$/, '');
    } catch {
      return '';
    }
  }

  function rank(index, request, limit = 5) {
    if (!index || index.schema_version !== 1 || !Array.isArray(index.entries) || index.entries.length > 128
      || typeof request !== 'string' || request.length > 200) return [];
    request = request.trim();
    const normalized = (url) => sourceKey(url).replace(/^github\.com\/([^/]+\/[^/]+)\//, (_, repo) =>
      'github.com/' + (index.repository_moves?.[repo] || repo) + '/');
    const requestedUrl = /#(?:issuecomment-|discussion_r|pullrequestreview-)/.test(request) ? '' : normalized(request);
    const found = index.cases.find((item) => normalized(item.origin_url) === requestedUrl);
    const query = found ? found.query : request;
    const recommended = found?.state === 'open' && found.verdict === 'candidate' && found.primary;
    const tokens = new Set(words(query).filter((word) => !stop.has(word)));
    const phrase = ' ' + words(query).join(' ') + ' ';
    const active = new Set(Object.entries(index.facets)
      .filter(([, aliases]) => aliases.some((alias) => phrase.includes(' ' + words(alias).join(' ') + ' ')))
      .map(([facet]) => facet));
    const sha = /^[a-f0-9]{40,64}$/i.test(query) ? query.toLowerCase() : '';
    const hits = [];
    for (const row of index.entries) {
      const repoKey = sourceKey(row.repository_url);
      const commitPath = repoKey.startsWith('gitlab.freedesktop.org/') ? '/-/commit/' : '/commit/';
      const exact = Boolean((requestedUrl && [normalized(row.source), repoKey + commitPath + row.revision].includes(requestedUrl))
        || request.toLowerCase() === row.id || (sha && sha === row.revision));
      const topics = row.topics.filter((topic) => active.has(topic));
      const symbols = row.features.symbols.filter((word) => tokens.has(word));
      const title = row.features.title.filter((word) => tokens.has(word));
      const context = row.features.context.filter((word) => tokens.has(word));
      const useful = new Set([...title, ...symbols, ...context]);
      if (!exact && !topics.length && !(symbols.length || (title.length && useful.size >= 2))) continue;
      const score = (exact ? 100 : 0) + 12 * topics.length + 5 * symbols.length + 3 * title.length + context.length
        + (found?.primary === row.id ? 18 : 0);
      const eligible = row.id === recommended && ['reference', 'merged'].includes(row.state) && row.kind !== 'diagnostic';
      hits.push({...row, score, evidence_status: eligible ? 'potentially_applicable' : 'source_found', match: {exact, facets: topics.sort(), symbols: symbols.sort()}});
    }
    const ranked = hits.sort((a, b) => Number(b.match.exact) - Number(a.match.exact) || b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)).slice(0, limit);
    return ranked.concat((index.automatic?.[requestedUrl]?.matches || []).slice(0, limit));
  }

  return {rank, sourceKey};
})();
