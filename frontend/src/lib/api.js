const BASE = 'http://localhost:8001';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const e = await res.json(); msg = e.error || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  startJob: (topic) => apiFetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  }),
  getJob: (id) => apiFetch(`/api/jobs/${id}`),
  getCorpus: () => apiFetch('/api/corpus'),
  getClusters: () => apiFetch('/api/clusters'),
  getOutliers: (clusterId = null) => apiFetch(
    `/api/outliers${clusterId != null ? `?cluster_id=${clusterId}` : ''}`
  ),
  getArticle: (id) => apiFetch(`/api/articles/${id}`),
  chat: (query) => apiFetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  }),
  exportZip: () => fetch(`${BASE}/api/export`).then(async res => {
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const e = await res.json(); msg = e.error || msg; } catch {}
      throw new Error(msg);
    }
    return res.blob();
  }),
};
