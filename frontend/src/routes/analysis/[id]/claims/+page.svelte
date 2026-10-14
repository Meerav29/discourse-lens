<script lang="ts">
	import { api, type Claims, type Proposition } from '#lib/api.ts';
	import { estimate, ordered, STANCES, tally, type Order } from '#lib/claims.ts';
	import { plural } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import { toast } from 'svelte-sonner';
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';

	const ws = $derived(useWorkspace());
	const analysisId = $derived(ws.analysis.id);

	let claims = $state<Claims | null>(null);
	let loadError = $state<string | null>(null);
	let starting = $state(false);
	let order = $state<Order>('debated');
	const open = new SvelteSet<number>();

	const articleById = $derived(new Map(ws.articles.map((a) => [a.id, a])));
	const running = $derived(claims?.status === 'running' || starting);
	const rows = $derived(ordered(claims?.propositions ?? [], order));
	// Bars share one scale: a point five articles take up is drawn longer than one two do.
	const most = $derived(Math.max(1, ...rows.map((p) => p.claims.length)));

	// Poll every 2 s while claims are being found, until the view closes.
	let timer: ReturnType<typeof setTimeout> | undefined;
	let alive = true;

	function schedule() {
		clearTimeout(timer);
		if (alive && claims?.status === 'running') timer = setTimeout(refresh, 2000);
	}

	async function refresh() {
		try {
			claims = await api.getClaims(analysisId);
			loadError = null;
		} catch (e) {
			// Keep the last result on screen; only a first load failing is an error.
			if (!claims) loadError = (e as Error).message;
		}
		schedule();
	}

	$effect(() => {
		untrack(refresh);
		return () => {
			alive = false;
			clearTimeout(timer);
		};
	});

	async function find() {
		starting = true;
		try {
			claims = await api.findClaims(analysisId);
			open.clear();
			schedule();
		} catch (e) {
			toast.error((e as Error).message);
		} finally {
			starting = false;
		}
	}

	function involvesSelected(p: Proposition): boolean {
		const sel = ws.selectedCluster;
		return sel == null || p.claims.some((c) => articleById.get(c.article_id)?.clusterId === sel);
	}

	function toggle(id: number) {
		if (open.has(id)) open.delete(id);
		else open.add(id);
	}
</script>

<div class="absolute inset-0 overflow-y-auto">
	{#if loadError}
		<p class="px-4 py-6 text-danger sm:px-6" role="alert">Couldn't load claims: {loadError}</p>
	{:else if !claims}
		<p class="px-4 py-6 text-muted sm:px-6" aria-busy="true">Loading claims…</p>
	{:else if running}
		<div class="max-w-xl px-4 py-8 sm:px-6" aria-live="polite">
			<p class="flex items-center gap-2 font-medium">
				<LoaderCircle size={16} class="animate-spin text-accent" aria-hidden="true" />
				Finding claims
			</p>
			<p class="mt-1 text-sm text-muted tabular">{claims.detail ?? 'Starting'}</p>
			<p class="mt-3 text-sm text-ink-2">
				Claude reads the opening of each article, then compares what they say. This takes about a
				minute. You can use the other views meanwhile.
			</p>
		</div>
	{:else if claims.status == null || claims.status === 'error'}
		<div class="max-w-xl px-4 py-8 sm:px-6">
			<h2 class="text-lg font-semibold">Where do the sources agree?</h2>
			<p class="mt-2 text-ink-2">
				Claude reads the opening of each article and notes its main claims, then finds the points
				that two or more articles take a position on, and whether each agrees, qualifies or disputes
				them.
			</p>
			{#if claims.status === 'error'}
				<p class="mt-4 text-sm text-danger" role="alert">
					Finding claims failed: {claims.detail}
				</p>
			{/if}
			<button
				type="button"
				onclick={find}
				class="mt-5 rounded-md bg-accent px-5 py-2.5 font-semibold text-accent-ink hover:opacity-90"
			>
				{claims.status === 'error' ? 'Try again' : 'Find claims'}
			</button>
			<p class="mt-2 text-sm text-muted">
				Uses Claude: {estimate(ws.articles.length)} for {plural(ws.articles.length, 'article')}.
			</p>
		</div>
	{:else}
		<div
			class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2 text-sm sm:px-6"
		>
			<p class="max-w-2xl text-muted">
				Points two or more articles take a position on{ws.selectedCluster != null
					? `; faded ones don't involve ${ws.cluster(ws.selectedCluster)?.label}`
					: ''}.
			</p>
			<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
				<ul class="flex gap-3 text-ink-2" aria-label="Key">
					{#each STANCES as s (s.stance)}
						<li class="flex items-center gap-1.5">
							<span class="size-2.5 rounded-sm" style:background-color={s.color} aria-hidden="true"
							></span>
							{s.label}
						</li>
					{/each}
				</ul>
				<label class="flex items-center gap-1.5 text-muted">
					Order
					<select
						bind:value={order}
						class="h-8 rounded-md border border-rule bg-raised px-2 text-ink focus:border-accent focus:outline-none"
					>
						<option value="debated">Most debated first</option>
						<option value="sources">Most articles first</option>
					</select>
				</label>
			</div>
		</div>

		<ol class="border-t border-rule">
			{#each rows as p (p.id)}
				{@const t = tally(p)}
				{@const expanded = open.has(p.id)}
				<li
					class="border-b border-rule-soft transition-opacity {involvesSelected(p)
						? ''
						: 'opacity-35'}"
				>
					<button
						type="button"
						onclick={() => toggle(p.id)}
						aria-expanded={expanded}
						aria-controls="prop-{p.id}"
						class="grid w-full grid-cols-[1fr_auto] items-start gap-x-6 gap-y-2 px-4 py-3 text-left hover:bg-rule-soft/60 sm:grid-cols-[minmax(0,1fr)_15rem_auto] sm:px-6"
					>
						<span class="min-w-0 font-medium sm:col-start-1">{p.statement}</span>
						<span
							class="col-span-2 row-start-2 sm:col-span-1 sm:col-start-2 sm:row-start-1 sm:pt-1.5"
						>
							<span
								class="flex h-2 gap-0.5"
								style:width="{(p.claims.length / most) * 100}%"
								aria-hidden="true"
							>
								{#each STANCES as s (s.stance)}
									{#if t[s.stance]}
										<span
											class="h-full basis-0 first:rounded-l-sm last:rounded-r-sm"
											style:flex-grow={t[s.stance]}
											style:background-color={s.color}
										></span>
									{/if}
								{/each}
							</span>
							<span class="mt-1 block text-xs text-muted tabular">
								{plural(p.claims.length, 'article')}: {STANCES.filter((s) => t[s.stance])
									.map((s) => `${t[s.stance]} ${s.verb}`)
									.join(', ')}
							</span>
						</span>
						<ChevronDown
							size={16}
							class="col-start-2 row-start-1 mt-1 text-muted transition-transform sm:col-start-3 {expanded
								? 'rotate-180'
								: ''}"
							aria-hidden="true"
						/>
					</button>

					{#if expanded}
						<div id="prop-{p.id}" class="grid gap-5 px-4 pb-4 sm:px-6 lg:grid-cols-3">
							{#each STANCES as s (s.stance)}
								{@const members = p.claims.filter((c) => c.stance === s.stance)}
								{#if members.length}
									<section>
										<h3 class="flex items-center gap-1.5 text-sm font-semibold">
											<span
												class="size-2.5 rounded-sm"
												style:background-color={s.color}
												aria-hidden="true"
											></span>
											{s.label}
											<span class="font-normal text-muted tabular">{members.length}</span>
										</h3>
										<ul class="mt-2 space-y-3">
											{#each members as c (c.claim_id)}
												{@const a = articleById.get(c.article_id)}
												<li class="text-sm">
													<p class="text-ink-2">{c.text}</p>
													{#if a}
														<button
															type="button"
															onclick={() => ws.openArticleById(a.id)}
															class="mt-0.5 flex max-w-full items-center gap-1.5 text-muted hover:text-ink hover:underline"
														>
															<span
																class="size-2 shrink-0 rounded-full"
																style:background-color={ws.color(a.clusterId)}
																aria-hidden="true"
															></span>
															<span class="truncate">{a.title}</span>
															{#if a.title !== a.domain}<span class="shrink-0">({a.domain})</span
																>{/if}
														</button>
													{/if}
												</li>
											{/each}
										</ul>
									</section>
								{/if}
							{/each}
						</div>
					{/if}
				</li>
			{:else}
				<li class="px-4 py-6 text-ink-2 sm:px-6">
					No point came up in two or more articles. The sources may be too varied to compare.
				</li>
			{/each}
		</ol>

		<p class="px-4 py-4 text-sm text-muted sm:px-6">
			From {plural(claims.claim_count, 'claim')} in the articles' openings.
			<button type="button" onclick={find} class="ml-1 underline hover:text-ink">
				Find again
			</button>
			({estimate(ws.articles.length)})
		</p>
	{/if}
</div>
