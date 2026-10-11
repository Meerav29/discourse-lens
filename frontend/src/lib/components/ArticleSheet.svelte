<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { api, type Article } from '#lib/api.ts';
	import { formatPublishDate } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import X from '@lucide/svelte/icons/x';

	const ws = $derived(useWorkspace());
	const articleId = $derived(ws.openArticle);
	const point = $derived(ws.articles.find((a) => a.id === articleId));

	let article = $state<Article | null>(null);
	let error = $state<string | null>(null);

	$effect(() => {
		const id = articleId;
		const analysisId = ws.analysis.id;
		article = null;
		error = null;
		if (!id) return;
		let stale = false;
		api.getArticle(analysisId, id).then(
			(a) => !stale && (article = a),
			(e) => !stale && (error = (e as Error).message)
		);
		return () => (stale = true);
	});

	const PARAGRAPHS = 4;
	const paragraphs = $derived(
		(article?.raw_text ?? '')
			.split(/\n+/)
			.map((p) => p.trim())
			.filter((p) => p.length > 40)
	);
</script>

<Dialog.Root open={articleId != null} onOpenChange={(open) => !open && ws.openArticleById(null)}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-ink/25" />
		<Dialog.Content
			class="fixed inset-y-0 right-0 z-50 flex w-[min(34rem,100vw)] flex-col border-l border-rule bg-raised shadow-2xl outline-none"
		>
			<div class="flex items-start gap-3 px-6 pt-5">
				<div class="min-w-0 flex-1">
					{#if point}
						<p class="flex items-center gap-2 text-sm text-ink-2">
							<span
								class="size-2.5 rounded-full"
								style:background-color={ws.color(point.clusterId)}
								aria-hidden="true"
							></span>
							{point.clusterLabel}
						</p>
					{/if}
				</div>
				<Dialog.Close
					class="-mr-2 grid size-9 place-items-center rounded-md text-muted hover:bg-rule-soft hover:text-ink"
					aria-label="Close article"
				>
					<X size={18} />
				</Dialog.Close>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto px-6 pb-8">
				<Dialog.Title class="mt-2 text-[1.4rem] leading-snug display">
					{article?.title ?? point?.title ?? 'Article'}
				</Dialog.Title>
				<Dialog.Description class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted tabular">
					{#if article}
						<span>{article.domain}</span>
						{#if formatPublishDate(article.publish_date)}<span
								>{formatPublishDate(article.publish_date)}</span
							>{/if}
						{#if article.word_count}<span>{article.word_count.toLocaleString()} words</span>{/if}
					{/if}
				</Dialog.Description>

				{#if error}
					<p class="mt-6 text-danger" role="alert">Couldn't load this article: {error}</p>
				{:else if !article}
					<div class="mt-6 space-y-3" aria-busy="true" aria-label="Loading article">
						{#each [92, 100, 84, 96, 60] as w, i (i)}
							<div class="h-3.5 animate-pulse rounded bg-rule-soft" style:width="{w}%"></div>
						{/each}
					</div>
				{:else}
					<div class="mt-6 space-y-4 text-[0.98rem] leading-relaxed text-ink-2">
						{#each paragraphs.slice(0, PARAGRAPHS) as p, i (i)}
							<p>{p}</p>
						{/each}
					</div>
					{#if paragraphs.length > PARAGRAPHS}
						<p class="mt-4 text-sm text-muted">
							Showing the opening of {paragraphs.length} paragraphs.
						</p>
					{/if}
					<!-- eslint-disable svelte/no-navigation-without-resolve -- external article URL -->
					<a
						href={article.url}
						target="_blank"
						rel="noopener noreferrer"
						class="mt-6 inline-flex items-center gap-2 rounded-md border border-rule px-4 py-2 text-sm font-medium hover:border-ink-2"
					>
						Open the original <ExternalLink size={14} aria-hidden="true" />
					</a>
					<!-- eslint-enable svelte/no-navigation-without-resolve -->
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
