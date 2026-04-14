<script>
  import { getClusterColor } from '../lib/d3helpers.js';

  export let points = [];
  export let selectedCluster = null;
  export let onSelectCluster = (_id) => {};

  const STOP_WORDS = new Set([
    'the','a','an','and','or','but','in','on','at','to','for','of','with',
    'by','from','as','is','was','are','were','be','been','being','have','has',
    'had','do','does','did','will','would','could','should','may','might','can',
    'this','that','these','those','it','its','how','why','what','when','where',
    'who','which','not','no','new','more','most','all','also','into','than',
    'their','there','they','we','our','your','his','her','its','up','out','if',
  ]);

  $: clusters = computeClusters(points);

  function computeClusters(pts) {
    // Group all chunk points by cluster — each point carries its own child_text
    const byCluster = new Map();
    for (const p of pts) {
      const cid = p.cluster_id;
      if (!byCluster.has(cid)) {
        byCluster.set(cid, { id: cid, label: p.cluster_label || `cluster ${cid}`, texts: [] });
      }
      if (p.child_text) byCluster.get(cid).texts.push(p.child_text.toLowerCase());
    }

    const totalChunks = pts.length || 1;

    // Global document frequency (one "doc" = one chunk)
    const globalDF = new Map();
    for (const p of pts) {
      if (!p.child_text) continue;
      const terms = tokenize(p.child_text.toLowerCase());
      for (const t of new Set(terms)) {
        globalDF.set(t, (globalDF.get(t) || 0) + 1);
      }
    }

    return [...byCluster.values()].map(c => {
      const tf = new Map();
      const clusterChunks = c.texts.length || 1;
      for (const text of c.texts) {
        for (const t of tokenize(text)) {
          tf.set(t, (tf.get(t) || 0) + 1);
        }
      }

      const scored = [...tf.entries()]
        .map(([term, count]) => {
          const idf = Math.log(totalChunks / ((globalDF.get(term) || 1)));
          return { term, score: (count / clusterChunks) * idf };
        })
        .filter(d => d.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 6);

      const maxScore = scored[0]?.score || 1;
      return {
        id: c.id,
        label: c.label,
        terms: scored.map(d => ({ ...d, pct: d.score / maxScore })),
      };
    }).sort((a, b) => a.id - b.id);
  }

  function tokenize(str) {
    return str
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter(w => w.length > 3 && !STOP_WORDS.has(w));
  }
</script>

<div class="wrap">
  {#if clusters.length === 0}
    <div class="empty">No data — run an analysis first</div>
  {:else}
    <div class="list">
      {#each clusters as cluster (cluster.id)}
        {@const active = selectedCluster == null || selectedCluster === cluster.id}
        <div
          class="cluster"
          class:dim={!active}
          role="button"
          tabindex="0"
          on:click={() => onSelectCluster(selectedCluster === cluster.id ? null : cluster.id)}
          on:keydown={(e) => e.key === 'Enter' && onSelectCluster(selectedCluster === cluster.id ? null : cluster.id)}
        >
          <div class="cluster-label" style="color:{getClusterColor(cluster.id)}">
            {cluster.label.toUpperCase()}
          </div>
          <div class="bars">
            {#each cluster.terms as t (t.term)}
              <div class="bar-row">
                <span class="term">{t.term}</span>
                <div class="track">
                  <div
                    class="fill"
                    style="width:{t.pct * 100}%; background:{getClusterColor(cluster.id)}"
                  ></div>
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap {
    width: 100%;
    height: 100%;
    overflow-y: auto;
  }
  .empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-6);
    font-size: 0.85rem;
  }
  .list {
    padding: 8px 0;
  }
  .cluster {
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.1s, opacity 0.15s;
  }
  .cluster:hover { background: var(--surface-2); }
  .cluster.dim { opacity: 0.25; }
  .cluster-label {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    margin-bottom: 5px;
  }
  .bars {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .bar-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .term {
    font-size: 0.68rem;
    color: var(--text-3);
    width: 80px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .track {
    flex: 1;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    border-radius: 2px;
    opacity: 0.6;
    transition: width 0.3s;
  }
</style>
