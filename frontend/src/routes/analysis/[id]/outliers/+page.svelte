<script lang="ts">
	import { useWorkspace } from '#lib/workspace.svelte.ts';

	const ws = $derived(useWorkspace());
	const LIMIT = 40;

	// Same article model as the map, so cluster names agree across views.
	const rows = $derived(
		ws.articles
			.filter((a) => ws.selectedCluster == null || a.clusterId === ws.selectedCluster)
			.toSorted((a, b) => b.distance - a.distance)
			.slice(0, LIMIT)
	);
	const max = $derived(Math.max(...rows.map((r) => r.distance), 1e-6));
</script>

<div class="absolute inset-0 overflow-y-auto">
	<p class="max-w-3xl px-4 py-2 text-sm text-muted sm:px-6">
		Articles furthest from the middle of their cluster{ws.selectedCluster != null
			? ` (${ws.cluster(ws.selectedCluster)?.label})`
			: ''}. They often argue something the rest of their camp doesn't, or don't fit any camp well.
	</p>

	<ol class="pb-6">
		{#each rows as r (r.id)}
			<li class="border-b border-rule-soft">
				<button
					type="button"
					onclick={() => ws.openArticleById(r.id)}
					class="grid w-full grid-cols-[1fr_auto] items-center gap-x-6 gap-y-1 px-4 py-3 text-left hover:bg-rule-soft/60 sm:grid-cols-[minmax(0,1fr)_14rem_10rem] sm:px-6"
				>
					<span class="min-w-0">
						<span class="block truncate font-medium">{r.title}</span>
						<span class="block truncate text-sm text-muted">{r.domain}</span>
					</span>
					<span class="hidden items-center gap-2 truncate text-sm text-ink-2 sm:flex">
						<span
							class="size-2 shrink-0 rounded-full"
							style:background-color={ws.color(r.clusterId)}
							aria-hidden="true"
						></span>
						<span class="truncate">{r.clusterLabel}</span>
					</span>
					<span class="flex items-center gap-2" title="Distance from the cluster's center">
						<span class="h-1.5 flex-1 overflow-hidden rounded-full bg-rule-soft">
							<span
								class="block h-full rounded-full bg-ink-2"
								style:width="{(r.distance / max) * 100}%"
							></span>
						</span>
						<span class="w-10 text-right text-sm text-muted tabular">{r.distance.toFixed(2)}</span>
					</span>
				</button>
			</li>
		{:else}
			<li class="px-4 py-6 text-ink-2 sm:px-6">No articles in this cluster.</li>
		{/each}
	</ol>
</div>
