<script lang="ts">
	import ArticleTable from '#lib/components/ArticleTable.svelte';
	import SurveyMap from '#lib/components/SurveyMap.svelte';

	let view = $state<'map' | 'table'>('map');
</script>

<div class="absolute inset-0 flex flex-col">
	<div class="flex items-center justify-between gap-4 px-4 py-2 sm:px-6">
		<p class="hidden text-sm text-muted md:block">
			Articles that make similar arguments sit close together. Drag to pan, scroll to zoom, click a
			dot to read it.
		</p>
		<div
			class="ml-auto flex rounded-md border border-rule p-0.5 text-sm"
			role="group"
			aria-label="Display"
		>
			{#each [['map', 'Map'], ['table', 'Table']] as const as [v, label] (v)}
				<button
					type="button"
					aria-pressed={view === v}
					onclick={() => (view = v)}
					class="rounded px-3 py-1 {view === v ? 'bg-ink text-paper' : 'text-ink-2 hover:text-ink'}"
				>
					{label}
				</button>
			{/each}
		</div>
	</div>
	<div class="relative min-h-0 flex-1">
		{#if view === 'map'}<SurveyMap />{:else}<ArticleTable />{/if}
	</div>
</div>
