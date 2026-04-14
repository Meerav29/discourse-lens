<script>
  import { onMount, onDestroy } from 'svelte';
  import * as d3 from 'd3';
  import { getClusterColor, formatMonth } from '../lib/d3helpers.js';

  export let points = [];

  let container;
  let sliderVal = 0;
  let playing = false;
  let timer;
  let ro;

  // One point per article
  $: articles = aggregateArticles(points);
  $: monthData = groupByMonth(articles);
  $: months = [...monthData.keys()].sort();
  $: centroids = months.map(m => {
    const pts = monthData.get(m) || [];
    return {
      month: m,
      x: d3.mean(pts, d => d.x),
      y: d3.mean(pts, d => d.y),
      count: pts.length,
    };
  });
  $: activeMonth = months[sliderVal] || null;
  $: sliderMax = Math.max(months.length - 1, 0);

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

  function groupByMonth(arts) {
    const map = new Map();
    for (const a of arts) {
      const m = a.publish_date ? a.publish_date.slice(0, 7) : null;
      if (!m || m === 'null') continue;
      if (!map.has(m)) map.set(m, []);
      map.get(m).push(a);
    }
    return map;
  }

  function draw() {
    if (!container || !articles.length) return;
    const W = container.clientWidth;
    const H = container.clientHeight;
    if (!W || !H || H < 40) return;

    d3.select(container).select('svg').remove();

    const mg = { t: 12, r: 12, b: 12, l: 12 };
    const iW = W - mg.l - mg.r;
    const iH = H - mg.t - mg.b;

    const svg = d3.select(container).append('svg').attr('width', W).attr('height', H);
    const g = svg.append('g').attr('transform', `translate(${mg.l},${mg.t})`);

    const xExt = d3.extent(articles, d => d.x);
    const yExt = d3.extent(articles, d => d.y);
    const xPad = Math.max((xExt[1] - xExt[0]) * 0.08, 0.5);
    const yPad = Math.max((yExt[1] - yExt[0]) * 0.08, 0.5);
    const xSc = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad]).range([0, iW]);
    const ySc = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad]).range([iH, 0]);

    // Background: all articles, very dim
    g.selectAll('circle.bg')
      .data(articles)
      .join('circle')
      .attr('class', 'bg')
      .attr('cx', d => xSc(d.x))
      .attr('cy', d => ySc(d.y))
      .attr('r', 2)
      .attr('fill', d => getClusterColor(d.cluster_id))
      .attr('fill-opacity', 0.1);

    const visibleCentroids = centroids.slice(0, sliderVal + 1);

    // Path connecting centroids
    if (visibleCentroids.length >= 2) {
      const line = d3.line()
        .x(d => xSc(d.x))
        .y(d => ySc(d.y))
        .curve(d3.curveCatmullRom.alpha(0.5));
      g.append('path')
        .datum(visibleCentroids)
        .attr('fill', 'none')
        .attr('stroke', '#5a7fff')
        .attr('stroke-width', 1.5)
        .attr('stroke-opacity', 0.55)
        .attr('d', line);
    }

    // Past centroid dots
    g.selectAll('circle.ctr')
      .data(visibleCentroids.slice(0, -1))
      .join('circle')
      .attr('class', 'ctr')
      .attr('cx', d => xSc(d.x))
      .attr('cy', d => ySc(d.y))
      .attr('r', 3)
      .attr('fill', '#3a5ac8')
      .attr('fill-opacity', 0.5);

    // Active month articles highlighted
    if (activeMonth) {
      const active = monthData.get(activeMonth) || [];
      g.selectAll('circle.active')
        .data(active)
        .join('circle')
        .attr('class', 'active')
        .attr('cx', d => xSc(d.x))
        .attr('cy', d => ySc(d.y))
        .attr('r', 3.5)
        .attr('fill', d => getClusterColor(d.cluster_id))
        .attr('fill-opacity', 0.85)
        .attr('stroke', 'rgba(255,255,255,0.25)')
        .attr('stroke-width', 0.8);
    }

    // Active centroid (current month)
    const cur = visibleCentroids[visibleCentroids.length - 1];
    if (cur) {
      g.append('circle')
        .attr('cx', xSc(cur.x))
        .attr('cy', ySc(cur.y))
        .attr('r', 6)
        .attr('fill', '#5a7fff')
        .attr('fill-opacity', 0.9)
        .attr('stroke', 'rgba(255,255,255,0.4)')
        .attr('stroke-width', 1.5);
    }
  }

  $: { sliderVal; articles; if (container) draw(); }

  onMount(() => {
    ro = new ResizeObserver(() => draw());
    ro.observe(container);
    draw();
  });
  onDestroy(() => { ro?.disconnect(); clearInterval(timer); });

  function togglePlay() {
    if (playing) {
      clearInterval(timer);
      playing = false;
    } else {
      if (sliderVal >= months.length - 1) sliderVal = 0;
      playing = true;
      timer = setInterval(() => {
        if (sliderVal >= months.length - 1) {
          clearInterval(timer);
          playing = false;
        } else {
          sliderVal++;
        }
      }, 700);
    }
  }
</script>

<div class="wrap" bind:this={container}>
  {#if articles.length === 0}
    <div class="empty">No data — run an analysis first</div>
  {:else if months.length === 0}
    <div class="empty">No date information in corpus</div>
  {/if}
</div>

{#if months.length > 0}
  <div class="controls">
    <button class="play-btn" on:click={togglePlay} title={playing ? 'Pause' : 'Play'}>
      {playing ? '⏸' : '▶'}
    </button>
    <input
      type="range"
      min="0"
      max={sliderMax}
      bind:value={sliderVal}
      class="slider"
    />
    <span class="month-label">{formatMonth(activeMonth) || '—'}</span>
  </div>
{/if}

<style>
  .wrap {
    width: 100%;
    flex: 1;
    min-height: 0;
    position: relative;
    overflow: hidden;
  }
  .empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-6);
    font-size: 0.85rem;
  }
  .controls {
    height: 48px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    border-top: 1px solid var(--border);
    flex-shrink: 0;
  }
  .play-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 0.85rem;
    cursor: pointer;
    padding: 4px 6px;
    border-radius: 4px;
    line-height: 1;
  }
  .play-btn:hover { background: var(--surface-2); }
  .slider {
    flex: 1;
    accent-color: var(--accent);
    cursor: pointer;
  }
  .month-label {
    font-size: 0.7rem;
    color: var(--text-3);
    white-space: nowrap;
    width: 72px;
    text-align: right;
  }
</style>
