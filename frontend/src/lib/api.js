const BASE = 'http://localhost:8001';

async function errorMessage(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
  } catch { /* not JSON */ }
  return `HTTP ${res.status}`;
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

const a = (id) => `/api/analyses/${encodeURIComponent(id)}`;

export const api = {
  createAnalysis: (topic) => apiFetch('/api/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  }),
  getAnalysis: (id) => apiFetch(a(id)),
  streamAnalysis: (id, onUpdate, onError) => {
    const source = new EventSource(`${BASE}${a(id)}/stream`);
    source.onmessage = (e) => onUpdate(JSON.parse(e.data));
    source.addEventListener('error', (e) => {
      if (e.data) {
        try { onError?.(JSON.parse(e.data)); } catch { /* ignore parse errors */ }
      }
    });
    source.onerror = () => { /* connection dropped or stream closed by server */ };
    return source;
  },
  getCorpus: (id) => apiFetch(`${a(id)}/corpus`),
  getClusters: (id) => apiFetch(`${a(id)}/clusters`),
  getOutliers: (id, clusterId = null) => apiFetch(
    `${a(id)}/outliers${clusterId != null ? `?cluster_id=${clusterId}` : ''}`
  ),
  getArticle: (id, articleId) => apiFetch(`${a(id)}/articles/${encodeURIComponent(articleId)}`),
  chat: (id, query) => apiFetch(`${a(id)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  }),
  exportZip: async (id) => {
    const res = await fetch(`${BASE}${a(id)}/export`);
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.blob();
  },
};
