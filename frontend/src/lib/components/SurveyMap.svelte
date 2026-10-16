<script lang="ts">
	import * as d3 from 'd3';
	import { UNCLUSTERED, type ArticlePoint } from '#lib/corpus.ts';
	import { formatPublishDate } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import Minus from '@lucide/svelte/icons/minus';
	import Plus from '@lucide/svelte/icons/plus';
	import Scan from '@lucide/svelte/icons/scan';

	const ws = $derived(useWorkspace());
	const selected = $derived(ws.selectedCluster);

	let width = $state(0);
	let height = $state(0);
	let svg = $state<SVGSVGElement>();
	let transform = $state(d3.zoomIdentity);
	let zoom: d3.ZoomBehavior<SVGSVGElement, unknown> | undefined;

	// Room for density contours, which spread about two bandwidths past the outermost articles.
	const PAD = 80;

	// One scale for both axes so UMAP distances aren't stretched.
	const base = $derived.by(() => {
		const xs = ws.articles.map((a) => a.x);
		const ys = ws.articles.map((a) => a.y);
		const [x0, x1] = d3.extent(xs) as [number, number];
		const [y0, y1] = d3.extent(ys) as [number, number];
		const k = Math.min((width - 2 * PAD) / (x1 - x0 || 1), (height - 2 * PAD) / (y1 - y0 || 1));
		const ox = (width - (x1 - x0) * k) / 2;
		const oy = (height - (y1 - y0) * k) / 2;
		return {
			x: (v: number) => ox + (v - x0) * k,
			y: (v: number) => height - (oy + (v - y0) * k)
		};
	});

	// Density contours per topic, from its articles' positions.
	const contours = $derived.by(() => {
		if (!width || !height) return [];
		const bandwidth = Math.max(14, Math.min(width, height) * 0.055);
		const path = d3.geoPath();
		return ws.clusters.flatMap((c) => {
			if (c.id === UNCLUSTERED) return [];
			const pts = ws.articles.filter((a) => a.clusterId === c.id);
			if (pts.length < 3) return [];
			const levels = d3
				.contourDensity<(typeof pts)[number]>()
				.x((p) => base.x(p.x))
				.y((p) => base.y(p.y))
				.size([width, height])
				.bandwidth(bandwidth)
				.thresholds(6)(pts);
			// Outer ring plus every second level inward: a survey chart, not a heatmap.
			const keep = levels.filter((_, i) => i % 2 === 0).slice(0, 3);
			return keep.map((l, i) => ({ cluster: c.id, outer: i === 0, d: path(l) ?? '' }));
		});
	});

	const radius = d3.scaleSqrt().domain([0, 6000]).range([2.5, 6.5]).clamp(true);

	const marks = $derived(
		ws.articles.map((a) => ({
			a,
			sx: transform.applyX(base.x(a.x)),
			sy: transform.applyY(base.y(a.y)),
			r: radius(a.wordCount)
		}))
	);

	// Cluster labels at article centroids, nudged apart where they collide.
	const labels = $derived.by(() => {
		const placed: { id: number; text: string; x: number; y: number; w: number }[] = [];
		const items = ws.clusters
			.filter((c) => c.id !== UNCLUSTERED) // scattered by definition: no centre to label
			.map((c) => {
				const members = ws.articles.filter((a) => a.clusterId === c.id);
				return {
					id: c.id,
					text: c.label,
					x: transform.applyX(base.x(d3.mean(members, (a) => a.x)!)),
					y: transform.applyY(base.y(d3.mean(members, (a) => a.y)!)) - 14,
					w: c.label.length * 7.4 + 16
				};
			})
			.sort((a, b) => a.y - b.y);
		const H = 20;
		for (const item of items) {
			// Keep the whole label on screen.
			item.x = Math.min(Math.max(item.x, item.w / 2 + 4), width - item.w / 2 - 4);
			let guard = 0;
			while (
				guard++ < 12 &&
				placed.some(
					(p) => Math.abs(p.x - item.x) < (p.w + item.w) / 2 && Math.abs(p.y - item.y) < H
				)
			) {
				item.y += H;
			}
			placed.push(item);
		}
		return placed;
	});

	$effect(() => {
		if (!svg) return;
		zoom = d3
			.zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.6, 12])
			.on('zoom', (e) => (transform = e.transform));
		const sel = d3.select(svg).call(zoom).on('dblclick.zoom', null);
		return () => sel.on('.zoom', null);
	});

	function zoomBy(factor: number) {
		if (svg && zoom) d3.select(svg).transition().duration(200).call(zoom.scaleBy, factor);
	}
	function resetZoom() {
		if (svg && zoom)
			d3.select(svg).transition().duration(250).call(zoom.transform, d3.zoomIdentity);
	}

	let hover = $state<{ a: ArticlePoint; x: number; y: number } | null>(null);

	const dim = (clusterId: number) => selected != null && clusterId !== selected;
</script>

<div class="absolute inset-0 overflow-hidden" bind:clientWidth={width} bind:clientHeight={height}>
	{#if width && height}
		<svg
			bind:this={svg}
			{width}
			{height}
			class="cursor-grab touch-none select-none active:cursor-grabbing"
			role="img"
			aria-label="Map of {ws.articles.length} articles in {ws.clusters
				.length} clusters. Use the table view for an accessible list."
		>
			<!-- background click clears the cluster selection -->
			<rect
				{width}
				{height}
				fill="transparent"
				onclick={() => ws.selectCluster(null)}
				role="presentation"
			/>

			<g transform={transform.toString()}>
				{#each contours as c, i (i)}
					<path
						d={c.d}
						fill={c.outer ? ws.color(c.cluster) : 'none'}
						fill-opacity={c.outer ? (dim(c.cluster) ? 0.015 : 0.07) : 0}
						stroke={ws.color(c.cluster)}
						stroke-opacity={dim(c.cluster) ? 0.12 : c.outer ? 0.7 : 0.4}
						stroke-width={c.outer ? 1.25 : 0.9}
						vector-effect="non-scaling-stroke"
						pointer-events="none"
					/>
				{/each}
			</g>

			{#each marks as m (m.a.id)}
				<g
					class="cursor-pointer"
					opacity={dim(m.a.clusterId) ? 0.18 : 1}
					onmouseenter={() => (hover = { a: m.a, x: m.sx, y: m.sy })}
					onmouseleave={() => (hover = null)}
					onclick={(e) => {
						e.stopPropagation();
						ws.openArticleById(m.a.id);
					}}
					role="presentation"
				>
					<circle cx={m.sx} cy={m.sy} r={m.r + 5} fill="transparent" />
					<circle
						cx={m.sx}
						cy={m.sy}
						r={hover?.a.id === m.a.id ? m.r + 1.5 : m.r}
						fill={ws.color(m.a.clusterId)}
						stroke="var(--paper)"
						stroke-width="1.5"
					/>
				</g>
			{/each}

			{#each labels as l (l.id)}
				<g
					class="cursor-pointer"
					opacity={dim(l.id) ? 0.3 : 1}
					onclick={(e) => {
						e.stopPropagation();
						ws.selectCluster(l.id);
					}}
					role="presentation"
				>
					<circle cx={l.x - l.w / 2 + 6} cy={l.y - 4} r="4" fill={ws.color(l.id)} />
					<text
						x={l.x - l.w / 2 + 15}
						y={l.y}
						class="map-label"
						font-weight={selected === l.id ? 700 : 600}
					>
						{l.text}
					</text>
				</g>
			{/each}
		</svg>

		{#if hover}
			<div
				class="pointer-events-none absolute z-10 max-w-72 rounded-md border border-rule bg-raised px-3 py-2 shadow-lg"
				style:left="{Math.min(hover.x + 14, width - 300)}px"
				style:top="{Math.max(hover.y - 12, 8)}px"
			>
				<p class="text-sm leading-snug font-medium">{hover.a.title}</p>
				<p class="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
					<span>{hover.a.domain}</span>
					{#if formatPublishDate(hover.a.date)}<span>{formatPublishDate(hover.a.date)}</span>{/if}
				</p>
				<p class="mt-1.5 flex items-center gap-1.5 text-xs text-ink-2">
					<span class="size-2 rounded-full" style:background-color={ws.color(hover.a.clusterId)}
					></span>
					{hover.a.clusterLabel}
				</p>
			</div>
		{/if}

		<div
			class="absolute right-3 bottom-3 flex flex-col overflow-hidden rounded-md border border-rule bg-raised shadow-sm"
		>
			<button type="button" class="map-btn" onclick={() => zoomBy(1.5)} aria-label="Zoom in"
				><Plus size={16} /></button
			>
			<button
				type="button"
				class="map-btn border-y border-rule"
				onclick={() => zoomBy(1 / 1.5)}
				aria-label="Zoom out"><Minus size={16} /></button
			>
			<button type="button" class="map-btn" onclick={resetZoom} aria-label="Reset view"
				><Scan size={15} /></button
			>
		</div>
	{/if}
</div>

<style>
	.map-label {
		font-size: 12.5px;
		font-stretch: 115%;
		letter-spacing: 0.01em;
		fill: var(--ink);
		paint-order: stroke;
		stroke: var(--paper);
		stroke-width: 4px;
		stroke-linejoin: round;
	}
	.map-btn {
		display: grid;
		place-items: center;
		width: 2.25rem;
		height: 2.25rem;
		color: var(--ink-2);
	}
	.map-btn:hover {
		background: var(--rule-soft);
		color: var(--ink);
	}
</style>
