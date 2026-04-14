<script>
  import { getClusterColor } from '../lib/d3helpers.js';

  export let outliers = [];
  export let onSelectArticle = (_id) => {};

  $: items = outliers.slice(0, 30);
  $: maxDist = Math.max(...items.map(d => d.distance_from_centroid || 0), 0.001);
</script>

<div class="list">
  {#if items.length === 0}
    <div class="empty">No articles yet — run an analysis first</div>
  {:else}
    {#each items as item (item.chunk_id)}
      <button class="row" on:click={() => onSelectArticle(item.article_id)}>
        <div class="top">
          <span class="title">{item.title || 'Untitled'}</span>
          <span class="domain">{item.domain || ''}</span>
        </div>
        <div class="bottom">
          <span class="badge" style="color:{getClusterColor(item.cluster_id)}">
            {item.cluster_label || `cluster ${item.cluster_id}`}
          </span>
          <div class="bar-track">
            <div
              class="bar-fill"
              style="width:{(item.distance_from_centroid / maxDist) * 100}%; background:{getClusterColor(item.cluster_id)}"
            ></div>
          </div>
          <span class="score">{(item.distance_from_centroid || 0).toFixed(2)}</span>
        </div>
      </button>
    {/each}
  {/if}
</div>

<style>
  .list {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .empty {
    padding: 2rem;
    color: var(--text-6);
    text-align: center;
    font-size: 0.85rem;
  }
  .row {
    background: none;
    border: none;
    border-bottom: 1px solid var(--border);
    padding: 9px 14px;
    text-align: left;
    cursor: pointer;
    color: inherit;
    width: 100%;
    transition: background 0.1s;
  }
  .row:hover { background: var(--surface-2); }
  .top {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 5px;
  }
  .title {
    font-size: 0.8rem;
    color: var(--text-2);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .domain {
    font-size: 0.7rem;
    color: var(--text-5);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .bottom {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .badge {
    font-size: 0.68rem;
    font-weight: 600;
    white-space: nowrap;
    width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
  }
  .bar-track {
    flex: 1;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 2px;
    opacity: 0.65;
  }
  .score {
    font-size: 0.68rem;
    color: var(--text-5);
    width: 32px;
    text-align: right;
    flex-shrink: 0;
  }
</style>
