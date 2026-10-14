<script lang="ts">
	import { api, type Plan, type PlanResult } from '#lib/api.ts';
	import { plural } from '#lib/format.ts';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import Plus from '@lucide/svelte/icons/plus';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import { toast } from 'svelte-sonner';
	import { SvelteSet } from 'svelte/reactivity';

	let { analysisId, oncancel }: { analysisId: string; oncancel: () => void } = $props();

	let plan = $state<Plan | null>(null);
	let loadError = $state<string | null>(null);
	let queries = $state<string[]>([]);
	const chosen = new SvelteSet<string>();
	let extraUrls = $state('');
	let searching = $state(false);
	let approving = $state(false);

	function adopt(p: Plan) {
		plan = p;
		queries = [...p.queries];
		chosen.clear();
		for (const r of p.results) chosen.add(r.url);
	}

	$effect(() => {
		api.getPlan(analysisId).then(adopt, (e) => (loadError = (e as Error).message));
	});

	const groups = $derived.by(() => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- throwaway grouping, rebuilt on change
		const by = new Map<string, PlanResult[]>();
		for (const r of plan?.results ?? []) {
			const list = by.get(r.query);
			if (list) list.push(r);
			else by.set(r.query, [r]);
		}
		return [...by.entries()];
	});

	const extra = $derived(
		extraUrls
			.split(/\s+/)
			.map((u) => u.trim())
			.filter(Boolean)
	);
	const invalidExtra = $derived(extra.filter((u) => !/^https?:\/\/[^/\s]+/.test(u)));
	const total = $derived(chosen.size + extra.filter((u) => !chosen.has(u)).length);
	const queriesChanged = $derived(
		JSON.stringify(queries.map((q) => q.trim()).filter(Boolean)) !== JSON.stringify(plan?.queries)
	);

	function host(url: string) {
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return url;
		}
	}

	function toggleGroup(results: PlanResult[], on: boolean) {
		for (const r of results) {
			if (on) chosen.add(r.url);
			else chosen.delete(r.url);
		}
	}

	async function searchAgain() {
		const qs = queries.map((q) => q.trim()).filter(Boolean);
		if (!qs.length) return;
		searching = true;
		try {
			adopt(await api.searchPlan(analysisId, qs));
		} catch (e) {
			toast.error(`Search failed: ${(e as Error).message}`);
		} finally {
			searching = false;
		}
	}

	async function approve() {
		const urls = [...chosen, ...extra.filter((u) => !chosen.has(u))];
		approving = true;
		try {
			await api.approvePlan(analysisId, urls);
			// The progress stream takes over from here.
		} catch (e) {
			approving = false;
			toast.error((e as Error).message);
		}
	}
</script>

<section class="flex min-h-0 flex-1 flex-col px-4 sm:px-6">
	{#if loadError}
		<p class="text-danger" role="alert">Couldn't load the search results: {loadError}</p>
	{:else if !plan}
		<p class="text-muted" aria-busy="true">Loading the search results…</p>
	{:else}
		<div class="grid min-h-0 flex-1 gap-8 lg:grid-cols-[minmax(0,22rem)_1fr] lg:overflow-hidden">
			<div>
				<h2 class="text-lg font-semibold">Check the sources before reading</h2>
				<p class="mt-1 text-sm text-ink-2">
					Untick pages you don't want, add your own, or edit the searches and run them again.
				</p>

				<h3 class="mt-6 text-sm font-semibold">Searches</h3>
				<ul class="mt-2 space-y-2">
					{#each queries as query, i (i)}
						<li class="flex gap-1.5">
							<label class="sr-only" for="query-{i}">Search {i + 1}</label>
							<input
								id="query-{i}"
								bind:value={queries[i]}
								class="h-9 min-w-0 flex-1 rounded-md border border-rule bg-raised px-2.5 text-sm focus:border-accent focus:outline-none"
							/>
							<button
								type="button"
								class="grid size-9 shrink-0 place-items-center rounded-md text-muted hover:bg-rule-soft hover:text-ink"
								aria-label={`Remove search “${query || i + 1}”`}
								onclick={() => (queries = queries.filter((__, j) => j !== i))}
							>
								<X size={15} />
							</button>
						</li>
					{/each}
				</ul>
				<div class="mt-2 flex gap-2">
					<button
						type="button"
						class="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm text-ink-2 hover:bg-rule-soft hover:text-ink"
						onclick={() => (queries = [...queries, ''])}
						disabled={queries.length >= 12}
					>
						<Plus size={15} aria-hidden="true" /> Add a search
					</button>
					<button
						type="button"
						class="inline-flex h-9 items-center gap-1.5 rounded-md border border-rule px-3 text-sm font-medium hover:border-ink-2 disabled:opacity-40"
						onclick={searchAgain}
						disabled={searching || !queriesChanged}
					>
						<Search size={15} aria-hidden="true" />
						{searching ? 'Searching…' : 'Search again'}
					</button>
				</div>

				<h3 class="mt-6 text-sm font-semibold">
					<label for="extra-urls">Add your own pages</label>
				</h3>
				<textarea
					id="extra-urls"
					bind:value={extraUrls}
					rows="3"
					placeholder="One web address per line"
					class="mt-2 w-full resize-y rounded-md border border-rule bg-raised px-2.5 py-2 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
				></textarea>
				{#if invalidExtra.length}
					<p class="mt-1 text-sm text-danger">Not a web address: {invalidExtra[0]}</p>
				{/if}

				<div class="mt-6 flex flex-wrap items-center gap-3">
					<button
						type="button"
						onclick={approve}
						disabled={approving || total === 0 || invalidExtra.length > 0}
						class="rounded-md bg-accent px-5 py-2.5 font-semibold text-accent-ink hover:opacity-90 disabled:opacity-40"
					>
						{approving ? 'Starting…' : `Read ${plural(total, 'page')}`}
					</button>
					<button
						type="button"
						onclick={oncancel}
						class="rounded-md px-3 py-2 text-sm text-ink-2 hover:text-danger"
					>
						Cancel this map
					</button>
				</div>
			</div>

			<div class="min-h-0 overflow-y-auto pb-8" aria-label="Search results">
				{#each groups as [query, results] (query)}
					{@const allOn = results.every((r) => chosen.has(r.url))}
					<section class="mb-6">
						<div class="flex items-baseline justify-between gap-4 border-b border-rule pb-2">
							<h3 class="text-sm font-semibold">{query}</h3>
							<button
								type="button"
								class="shrink-0 text-sm text-muted hover:text-ink"
								onclick={() => toggleGroup(results, !allOn)}
							>
								{allOn ? 'Untick all' : 'Tick all'}
							</button>
						</div>
						<ul>
							{#each results as r (r.url)}
								<li class="flex gap-3 border-b border-rule-soft py-2.5">
									<input
										id="pick-{r.url}"
										type="checkbox"
										class="mt-1 size-4 shrink-0 accent-[var(--accent)]"
										checked={chosen.has(r.url)}
										onchange={(e) =>
											e.currentTarget.checked ? chosen.add(r.url) : chosen.delete(r.url)}
									/>
									<div class="min-w-0">
										<label
											for="pick-{r.url}"
											class="block font-medium {chosen.has(r.url) ? '' : 'text-muted line-through'}"
										>
											{r.title || host(r.url)}
										</label>
										<p class="text-sm text-muted">
											<!-- eslint-disable svelte/no-navigation-without-resolve -- external search result -->
											<a
												href={r.url}
												target="_blank"
												rel="noopener noreferrer"
												class="inline-flex items-center gap-1 hover:text-ink hover:underline"
											>
												{host(r.url)}
												<ExternalLink size={11} aria-hidden="true" />
											</a>
											<!-- eslint-enable svelte/no-navigation-without-resolve -->
										</p>
										{#if r.snippet}<p class="mt-0.5 line-clamp-2 text-sm text-ink-2">
												{r.snippet}
											</p>{/if}
									</div>
								</li>
							{/each}
						</ul>
					</section>
				{:else}
					<p class="text-ink-2">The searches found nothing. Edit them and search again.</p>
				{/each}
			</div>
		</div>
	{/if}
</section>
