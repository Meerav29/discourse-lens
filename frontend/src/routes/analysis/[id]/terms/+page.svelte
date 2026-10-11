<script lang="ts">
	import { distinctiveTerms } from '#lib/corpus.ts';
	import { plural } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';

	const ws = $derived(useWorkspace());
	const terms = $derived(distinctiveTerms(ws.points));
	const selected = $derived(ws.selectedCluster);
	// The selected cluster moves to the top so it's never below the fold.
	const ordered = $derived(
		selected == null
			? ws.clusters
			: [...ws.clusters].sort((a, b) => Number(b.id === selected) - Number(a.id === selected))
	);
</script>

<div class="absolute inset-0 overflow-y-auto">
	<p class="max-w-3xl px-4 py-2 text-sm text-muted sm:px-6">
		Words each cluster uses far more than the rest of the corpus does. Bars are relative to the
		cluster's strongest word.
	</p>
	<div class="grid gap-x-10 px-4 pb-8 sm:px-6 md:grid-cols-2 2xl:grid-cols-3">
		{#each ordered as c (c.id)}
			<section
				class="border-t border-rule py-4 transition-opacity {selected != null && selected !== c.id
					? 'opacity-35'
					: ''}"
				aria-labelledby="terms-{c.id}"
			>
				<h2 id="terms-{c.id}">
					<button
						type="button"
						onclick={() => ws.selectCluster(c.id)}
						aria-pressed={selected === c.id}
						class="flex w-full items-center gap-2 text-left hover:underline"
					>
						<span
							class="size-2.5 shrink-0 rounded-full"
							style:background-color={ws.color(c.id)}
							aria-hidden="true"
						></span>
						<span class="flex-1 font-semibold">{c.label}</span>
						<span class="text-sm font-normal text-muted tabular"
							>{plural(c.articles, 'article')}</span
						>
					</button>
				</h2>
				<ul class="mt-3 space-y-1.5">
					{#each terms.get(c.id) ?? [] as t (t.term)}
						<li class="grid grid-cols-[8.5rem_1fr] items-center gap-3 text-sm">
							<span class="truncate text-ink-2">{t.term}</span>
							<span class="h-1.5 overflow-hidden rounded-full bg-rule-soft">
								<span
									class="block h-full rounded-full"
									style:width="{t.share * 100}%"
									style:background-color={ws.color(c.id)}
								></span>
							</span>
						</li>
					{:else}
						<li class="text-sm text-muted">Too little text to find distinctive words.</li>
					{/each}
				</ul>
			</section>
		{/each}
	</div>
</div>
