<script lang="ts">
	import type { Analysis } from '#lib/api.ts';
	import { isRunning } from '#lib/api.ts';
	import { plural } from '#lib/format.ts';
	import CircleCheck from '@lucide/svelte/icons/circle-check';
	import CircleX from '@lucide/svelte/icons/circle-x';
	import CircleSlash from '@lucide/svelte/icons/circle-slash';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';

	let { analysis }: { analysis: Analysis } = $props();
</script>

<span class="inline-flex items-center gap-1.5 text-sm text-ink-2 tabular">
	{#if analysis.status === 'done'}
		<CircleCheck size={15} class="text-muted" aria-hidden="true" />
		{plural(analysis.article_count, 'article')}
	{:else if analysis.status === 'error'}
		<CircleX size={15} class="text-danger" aria-hidden="true" />
		Failed
	{:else if analysis.status === 'cancelled'}
		<CircleSlash size={15} class="text-muted" aria-hidden="true" />
		Cancelled
	{:else if isRunning(analysis)}
		<LoaderCircle size={15} class="animate-spin text-accent" aria-hidden="true" />
		Mapping, {analysis.progress}%
	{/if}
</span>
