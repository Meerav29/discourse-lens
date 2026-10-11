<script lang="ts">
	import { clusterColor, MAX_HUES } from '#lib/corpus.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';

	const ws = $derived(useWorkspace());
	const selected = $derived(ws.selectedCluster);
	const folded = $derived(ws.clusters.some((c) => c.slot === null));
</script>

<div class="p-4 sm:px-6 lg:px-5 lg:py-5">
	<div class="flex items-baseline justify-between">
		<h2 class="font-semibold">Clusters</h2>
		{#if selected != null}
			<button
				type="button"
				class="text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
				onclick={() => ws.selectCluster(null)}
			>
				Show all
			</button>
		{/if}
	</div>
	<p class="mt-1 text-sm text-muted">Pick one to focus every view on it.</p>

	<ul class="mt-3 grid gap-0.5 sm:grid-cols-2 lg:grid-cols-1">
		{#each ws.clusters as c (c.id)}
			<li>
				<button
					type="button"
					aria-pressed={selected === c.id}
					onclick={() => ws.selectCluster(c.id)}
					class="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-[background-color,opacity] hover:bg-rule-soft
						{selected === c.id ? 'bg-rule-soft' : ''}
						{selected != null && selected !== c.id ? 'opacity-45' : ''}"
				>
					<span
						class="size-2.5 shrink-0 rounded-full"
						style:background-color={clusterColor(c.slot)}
						aria-hidden="true"
					></span>
					<span
						class="min-w-0 flex-1 truncate text-[0.95rem] {selected === c.id
							? 'font-semibold'
							: ''}"
					>
						{c.label}
					</span>
					<span class="text-sm text-muted tabular">{c.articles}</span>
				</button>
			</li>
		{/each}
	</ul>

	{#if folded}
		<p class="mt-3 text-xs leading-relaxed text-muted">
			Only the {MAX_HUES} largest clusters get their own color. The rest share grey; their labels still
			name them on the map.
		</p>
	{/if}
</div>
