<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, type Analysis } from '#lib/api.ts';
	import { toast } from 'svelte-sonner';

	let { analysis }: { analysis: Analysis } = $props();
	let starting = $state(false);

	async function runAgain() {
		starting = true;
		try {
			const next = await api.createAnalysis(analysis.topic);
			await goto(resolve('/analysis/[id]', { id: next.id }));
		} catch (e) {
			starting = false;
			toast.error(`Couldn't start a new map: ${(e as Error).message}`);
		}
	}
</script>

<section class="max-w-xl px-4 py-6 sm:px-6">
	{#if analysis.status === 'error'}
		<h2 class="text-lg font-semibold">This map didn't finish</h2>
		<p class="mt-2 text-ink-2">
			{analysis.error_msg ?? 'The pipeline stopped with an unknown error.'}
		</p>
	{:else}
		<h2 class="text-lg font-semibold">This map was cancelled</h2>
		<p class="mt-2 text-ink-2">Nothing it collected was kept.</p>
	{/if}
	<button
		type="button"
		onclick={runAgain}
		disabled={starting}
		class="mt-6 rounded-md bg-accent px-5 py-2.5 font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
	>
		{starting ? 'Starting…' : 'Map this topic again'}
	</button>
</section>
