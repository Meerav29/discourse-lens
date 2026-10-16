<script lang="ts">
	import * as d3 from 'd3';
	import { buildTimeline, type TimelineBin } from '#lib/corpus.ts';
	import { formatBin, plural } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';

	const ws = $derived(useWorkspace());
	const selected = $derived(ws.selectedCluster);
	// Stack order = key order (largest cluster at the baseline).
	const keys = $derived(ws.clusters.map((c) => c.id));
	const timeline = $derived(buildTimeline(ws.articles, keys));

	let width = $state(0);
	let height = $state(0);
	const M = { top: 16, right: 16, bottom: 32, left: 40 };

	const x = $derived(
		d3
			.scaleBand<string>()
			.domain(timeline.bins.map((b) => b.key))
			.range([M.left, width - M.right])
			.paddingInner(timeline.bins.length > 40 ? 0.15 : 0.3)
	);
	const yMax = $derived(d3.max(timeline.bins, (b) => b.total) ?? 1);
	const y = $derived(
		d3
			.scaleLinear()
			.domain([0, Math.max(yMax, 1)])
			.nice(5)
			.range([height - M.bottom, M.top])
	);

	const segments = $derived.by(() => {
		const out: { bin: TimelineBin; cluster: number; y0: number; y1: number }[] = [];
		for (const bin of timeline.bins) {
			let acc = 0;
			for (const id of keys) {
				const n = bin.counts[id] ?? 0;
				if (n > 0) out.push({ bin, cluster: id, y0: acc, y1: acc + n });
				acc += n;
			}
		}
		return out;
	});

	// Label at most ~10 ticks so they never collide.
	const tickEvery = $derived(Math.max(1, Math.ceil(timeline.bins.length / 10)));
	const yTicks = $derived(y.ticks(Math.min(5, yMax)).filter(Number.isInteger));

	let hover = $state<TimelineBin | null>(null);
</script>

<div class="absolute inset-0 flex flex-col">
	<p class="px-4 py-2 text-sm text-muted sm:px-6">
		{#if timeline.dated === 0}
			None of these articles carry a publish date, so there's no timeline to draw.
		{:else}
			Articles per {timeline.unit} by cluster. {plural(timeline.dated, 'article')} have a publish date{timeline.undated
				? `; ${timeline.undated} don't and are left out`
				: ''}.
		{/if}
	</p>

	{#if timeline.dated > 0}
		<div class="relative min-h-0 flex-1" bind:clientWidth={width} bind:clientHeight={height}>
			{#if width && height}
				<svg
					{width}
					{height}
					role="img"
					aria-label="Articles published per {timeline.unit}, stacked by cluster"
				>
					{#each yTicks as t (t)}
						<line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--rule-soft)" />
						<text x={M.left - 8} y={y(t)} dy="0.32em" text-anchor="end" class="tick">{t}</text>
					{/each}
					<line x1={M.left} x2={width - M.right} y1={y(0)} y2={y(0)} stroke="var(--rule)" />

					{#each segments as s (s.bin.key + ':' + s.cluster)}
						<!-- 2px surface gap between stacked segments -->
						<rect
							x={x(s.bin.key)}
							y={y(s.y1)}
							width={x.bandwidth()}
							height={Math.max(0, y(s.y0) - y(s.y1) - 2)}
							rx="2"
							fill={ws.color(s.cluster)}
							opacity={selected != null && selected !== s.cluster ? 0.15 : 1}
						/>
					{/each}

					{#each timeline.bins as b, i (b.key)}
						{#if i % tickEvery === 0}
							<text
								x={x(b.key)! + x.bandwidth() / 2}
								y={height - M.bottom + 18}
								text-anchor="middle"
								class="tick"
							>
								{formatBin(b.start, timeline.unit)}
							</text>
						{/if}
						<!-- hit target: the whole column -->
						<rect
							x={x(b.key)! - (x.step() - x.bandwidth()) / 2}
							y={M.top}
							width={x.step()}
							height={height - M.top - M.bottom}
							fill={hover?.key === b.key ? 'var(--ink)' : 'transparent'}
							fill-opacity="0.04"
							onmouseenter={() => (hover = b)}
							onmouseleave={() => (hover = null)}
							role="presentation"
						/>
					{/each}
				</svg>

				{#if hover && hover.total > 0}
					{@const left = x(hover.key)! + x.bandwidth() + 10}
					<div
						class="pointer-events-none absolute z-10 w-60 rounded-md border border-rule bg-raised px-3 py-2 text-sm shadow-lg"
						style:left="{left + 240 > width ? left - 260 - x.bandwidth() : left}px"
						style:top="{M.top}px"
					>
						<p class="font-medium">{formatBin(hover.start, timeline.unit)}</p>
						<ul class="mt-1.5 space-y-0.5">
							{#each ws.clusters.filter((c) => hover!.counts[c.id]) as c (c.id)}
								<li class="flex items-center gap-2 text-ink-2">
									<span class="size-2 shrink-0 rounded-full" style:background-color={ws.color(c.id)}
									></span>
									<span class="min-w-0 flex-1 truncate">{c.label}</span>
									<span class="tabular">{hover.counts[c.id]}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>

<style>
	.tick {
		font-size: 12px;
		fill: var(--muted);
		font-variant-numeric: tabular-nums;
	}
</style>
