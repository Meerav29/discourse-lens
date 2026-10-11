<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { isRunning } from '#lib/api.ts';
	import ArticleSheet from '#lib/components/ArticleSheet.svelte';
	import ClusterKey from '#lib/components/ClusterKey.svelte';
	import EndedView from '#lib/components/EndedView.svelte';
	import ProgressView from '#lib/components/ProgressView.svelte';
	import ThemeToggle from '#lib/components/ThemeToggle.svelte';
	import { formatTimestamp, plural } from '#lib/format.ts';
	import { setWorkspace, Workspace, type View } from '#lib/workspace.svelte.ts';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import Download from '@lucide/svelte/icons/download';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const ws = $derived(new Workspace(data.analysis, data.points));
	setWorkspace(() => ws);

	const VIEWS: { view: View; slug: string; label: string }[] = [
		{ view: 'map', slug: '', label: 'Map' },
		{ view: 'timeline', slug: 'timeline', label: 'Timeline' },
		{ view: 'outliers', slug: 'outliers', label: 'Outliers' },
		{ view: 'terms', slug: 'terms', label: 'Key terms' },
		{ view: 'ask', slug: 'ask', label: 'Ask' }
	];

	const base = $derived(resolve('/analysis/[id]', { id: data.analysis.id }));
	const current = $derived(page.url.pathname.slice(base.length).replace(/^\//, ''));
</script>

<svelte:head>
	<title>{data.analysis.topic} · Discourse Lens</title>
</svelte:head>

<div class="flex min-h-dvh flex-col lg:h-dvh">
	<header class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pt-4 sm:px-6">
		<a
			href={resolve('/')}
			class="-ml-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:text-ink"
		>
			<ArrowLeft size={15} aria-hidden="true" /> All maps
		</a>
		<div class="ml-auto flex items-center gap-1">
			{#if data.analysis.status === 'done'}
				<!-- eslint-disable svelte/no-navigation-without-resolve -- API download, not an app route -->
				<a
					href="/api/analyses/{data.analysis.id}/export"
					download
					class="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-ink-2 hover:bg-rule-soft hover:text-ink"
					title="Download an Obsidian vault: one note per article plus a canvas of the map"
				>
					<Download size={15} aria-hidden="true" /> Export to Obsidian
				</a>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{/if}
			<ThemeToggle />
		</div>
	</header>

	<div class="px-4 pt-2 pb-4 sm:px-6">
		<h1 class="max-w-4xl text-[1.65rem] leading-tight display sm:text-[2rem]">
			{data.analysis.topic}
		</h1>
		{#if data.analysis.status === 'done'}
			<p class="mt-1 text-sm text-muted tabular">
				{plural(ws.articles.length, 'article')} in {plural(ws.clusters.length, 'cluster')}, mapped
				{formatTimestamp(data.analysis.updated_ts)}
			</p>
		{/if}
	</div>

	{#if isRunning(data.analysis)}
		<ProgressView analysis={data.analysis} />
	{:else if data.analysis.status !== 'done'}
		<EndedView analysis={data.analysis} />
	{:else}
		{#if data.analysis.warning}
			<p
				class="mx-4 mb-3 flex items-start gap-2 rounded-md border border-rule bg-raised px-3 py-2 text-sm text-ink-2 sm:mx-6"
			>
				<TriangleAlert size={16} class="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
				{data.analysis.warning}
			</p>
		{/if}

		<nav aria-label="Views" class="border-b border-rule px-4 sm:px-6">
			<ul class="-mb-px flex gap-5 overflow-x-auto">
				{#each VIEWS as v (v.slug)}
					<li>
						<!-- eslint-disable svelte/no-navigation-without-resolve -- viewHref() resolves -->
						<a
							href={ws.viewHref(v.view)}
							aria-current={current === v.slug ? 'page' : undefined}
							class="block border-b-2 py-2.5 text-[0.95rem] whitespace-nowrap transition-colors
								{current === v.slug
								? 'border-ink font-semibold text-ink'
								: 'border-transparent text-muted hover:text-ink'}"
						>
							{v.label}
						</a>
						<!-- eslint-enable svelte/no-navigation-without-resolve -->
					</li>
				{/each}
			</ul>
		</nav>

		<div class="flex min-h-0 flex-1 flex-col lg:flex-row">
			<main class="relative min-h-[28rem] min-w-0 flex-1 lg:min-h-0">
				{@render children()}
			</main>
			<aside
				class="border-t border-rule lg:w-72 lg:shrink-0 lg:overflow-y-auto lg:border-t-0 lg:border-l"
				aria-label="Clusters"
			>
				<ClusterKey />
			</aside>
		</div>

		<ArticleSheet />
	{/if}
</div>
