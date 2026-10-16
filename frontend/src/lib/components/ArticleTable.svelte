<script lang="ts">
	import { formatPublishDate } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';

	const ws = $derived(useWorkspace());
	const rows = $derived(
		ws.articles
			.filter((a) => ws.selectedCluster == null || a.clusterId === ws.selectedCluster)
			.toSorted(
				(a, b) =>
					(ws.cluster(a.clusterId)?.slot ?? 99) - (ws.cluster(b.clusterId)?.slot ?? 99) ||
					a.title.localeCompare(b.title)
			)
	);
</script>

<div class="absolute inset-0 overflow-auto">
	<table class="w-full text-sm">
		<caption class="sr-only">Articles in this map, grouped by cluster</caption>
		<thead class="sticky top-0 bg-paper text-left text-muted">
			<tr class="border-b border-rule">
				<th scope="col" class="py-2 pr-4 pl-4 font-medium sm:pl-6">Article</th>
				<th scope="col" class="py-2 pr-4 font-medium">Cluster</th>
				<th scope="col" class="hidden py-2 pr-4 font-medium md:table-cell">Source</th>
				<th scope="col" class="hidden py-2 pr-6 font-medium sm:table-cell">Published</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as a (a.id)}
				<tr class="border-b border-rule-soft hover:bg-rule-soft/60">
					<td class="py-2 pr-4 pl-4 sm:pl-6">
						<button
							type="button"
							class="text-left font-medium hover:underline"
							onclick={() => ws.openArticleById(a.id)}
						>
							{a.title}
						</button>
					</td>
					<td class="py-2 pr-4 whitespace-nowrap text-ink-2">
						<span class="inline-flex items-center gap-1.5">
							<span
								class="size-2 rounded-full"
								style:background-color={ws.color(a.clusterId)}
								aria-hidden="true"
							></span>
							{a.clusterLabel}
						</span>
					</td>
					<td class="hidden py-2 pr-4 text-muted md:table-cell">{a.domain}</td>
					<td class="hidden py-2 pr-6 whitespace-nowrap text-muted tabular sm:table-cell">
						{formatPublishDate(a.date) ?? 'No date'}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
