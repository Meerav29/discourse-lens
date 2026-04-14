<script>
  import { onMount, onDestroy } from 'svelte';
  import * as d3 from 'd3';
  import { getClusterColor, getNodeRadius } from '../lib/d3helpers.js';

  export let points = [];
  export let selectedCluster = null;
  export let onSelectCluster = (_id) => {};
  export let onSelectArticle = (_id) => {};

  let container;
  let tooltip = { show: false, x: 0, y: 0, data: null };
  let ro;

  // One point per article — average x/y across all chunks
  $: articles = aggregateArticles(points);
  $: centroids = computeCentroids(articles);

  function aggregateArticles(pts) {
    const map = new Map();
    for (const p of pts) {
      if (!map.has(p.article_id)) {
        map.set(p.article_id, { ...p, _n: 1 });
      } else {
        const e = map.get(p.article_id);
        e.x = (e.x * e._n + p.x) / (e._n + 1);
        e.y = (e.y * e._n + p.y) / (e._n + 1);
        e._n++;
      }
    }
    return [...map.values()];
  }

  function computeCentroids(arts) {
    const groups = d3.group(arts, d => d.cluster_id);
    return [...groups.entries()].map(([id, members]) => ({
      id,
      label: members[0].cluster_label || `cluster ${id}`,
      x: d3.mean(members, d => d.x),
      y: d3.mean(members, d => d.y),
    }));
  }

  function draw() {
    if (!container || !articles.length) return;

    const W = container.clientWidth;
    const H = container.clientHeight;
    if (!W || !H) return;

    const m = { t: 24, r: 24, b: 24, l: 24 };
    const iW = W - m.l - m.r;
    const iH = H - m.t - m.b;

    d3.select(container).select('svg').remove();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', W)
      .attr('height', H)
      .style('cursor', 'grab');

    const xExt = d3.extent(articles, d => d.x);
    const yExt = d3.extent(articles, d => d.y);
    const xPad = Math.max((xExt[1] - xExt[0]) * 0.08, 0.5);
    const yPad = Math.max((yExt[1] - yExt[0]) * 0.08, 0.5);

    const xSc = d3.scaleLinear()
      .domain([xExt[0] - xPad, xExt[1] + xPad])
      .range([0, iW]);
    const ySc = d3.scaleLinear()
      .domain([yExt[0] - yPad, yExt[1] + yPad])
      .range([iH, 0]);

    const g = svg.append('g').attr('transform', `translate(${m.l},${m.t})`);

    // Zoom + pan
    const zoom = d3.zoom()
      .scaleExtent([0.3, 14])
      .on('zoom', (e) => {
        g.attr('transform',
          `translate(${m.l + e.transform.x},${m.t + e.transform.y}) scale(${e.transform.k})`);
        svg.style('cursor', e.sourceEvent?.type === 'mousedown' ? 'grabbing' : 'grab');
      });
    svg.call(zoom);

    // Deselect on background click
    svg.on('click', () => onSelectCluster(null));

    // Nodes
    g.selectAll('circle.node')
      .data(articles)
      .join('circle')
      .attr('class', 'node')
      .attr('cx', d => xSc(d.x))
      .attr('cy', d => ySc(d.y))
      .attr('r', d => getNodeRadius(d.word_count))
      .attr('fill', d => getClusterColor(d.cluster_id))
      .attr('fill-opacity', d =>
        selectedCluster == null || d.cluster_id === selectedCluster ? 0.82 : 0.1)
      .attr('stroke', d =>
        selectedCluster == null || d.cluster_id === selectedCluster
          ? 'rgba(255,255,255,0.2)' : 'none')
      .attr('stroke-width', 1)
      .style('cursor', 'pointer')
      .on('mouseover', (event, d) => {
        tooltip = { show: true, x: event.clientX, y: event.clientY, data: d };
        d3.select(event.currentTarget)
          .attr('stroke', 'rgba(255,255,255,0.7)')
          .attr('stroke-width', 1.5);
      })
      .on('mousemove', (event) => {
        tooltip = { ...tooltip, x: event.clientX, y: event.clientY };
      })
      .on('mouseout', (event, d) => {
        tooltip = { ...tooltip, show: false };
        d3.select(event.currentTarget)
          .attr('stroke', selectedCluster == null || d.cluster_id === selectedCluster
            ? 'rgba(255,255,255,0.2)' : 'none')
          .attr('stroke-width', 1);
      })
      .on('click', (event, d) => {
        event.stopPropagation();
        onSelectArticle(d.article_id);
      });

    // Cluster labels
    centroids.forEach(c => {
      const opacity = selectedCluster == null || c.id === selectedCluster ? 1 : 0.15;
      g.append('text')
        .attr('x', xSc(c.x))
        .attr('y', ySc(c.y) - 14)
        .attr('text-anchor', 'middle')
        .attr('fill', getClusterColor(c.id))
        .attr('fill-opacity', opacity)
        .attr('font-size', '9.5px')
        .attr('font-weight', '700')
        .attr('letter-spacing', '0.06em')
        .style('cursor', 'pointer')
        .style('user-select', 'none')
        .style('text-transform', 'uppercase')
        .text(c.label.toUpperCase())
        .on('click', (event) => {
          event.stopPropagation();
          onSelectCluster(selectedCluster === c.id ? null : c.id);
        });
    });
  }

  // Redraw when data or selection changes
  $: {
    selectedCluster;
    articles;
    if (container) draw();
  }

  onMount(() => {
    ro = new ResizeObserver(() => draw());
    ro.observe(container);
    draw();
  });
  onDestroy(() => ro?.disconnect());
</script>

<div bind:this={container} class="wrap">
  {#if articles.length === 0}
    <div class="empty">No data — run an analysis first</div>
  {/if}
</div>

{#if tooltip.show && tooltip.data}
  <div class="tip" style="left:{tooltip.x + 14}px; top:{tooltip.y - 36}px">
    <div class="tip-title">{tooltip.data.title || 'Untitled'}</div>
    <div class="tip-meta">{tooltip.data.domain || ''}{tooltip.data.publish_date ? ' · ' + tooltip.data.publish_date : ''}</div>
  </div>
{/if}

<style>
  .wrap {
    width: 100%;
    height: 100%;
    position: relative;
  }
  .empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #333;
    font-size: 0.85rem;
  }
  .tip {
    position: fixed;
    background: #1a1a28;
    border: 1px solid #32324a;
    border-radius: 6px;
    padding: 7px 11px;
    pointer-events: none;
    z-index: 500;
    max-width: 260px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }
  .tip-title {
    font-size: 0.82rem;
    font-weight: 500;
    color: #e0e0f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 2px;
  }
  .tip-meta {
    font-size: 0.72rem;
    color: #666;
  }
</style>
