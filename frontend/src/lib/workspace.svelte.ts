import { getContext, setContext } from 'svelte';
import { goto } from '$app/navigation';
import { resolve } from '$app/paths';
import { page } from '$app/state';
import type { Analysis, Cluster, MapArticle } from '#lib/api.ts';
import {
	clusterColor,
	summarizeClusters,
	toArticlePoints,
	type ArticlePoint,
	type ClusterInfo
} from '#lib/corpus.ts';

const VIEW_ROUTES = {
	map: '/analysis/[id]',
	timeline: '/analysis/[id]/timeline',
	outliers: '/analysis/[id]/outliers',
	terms: '/analysis/[id]/terms',
	ask: '/analysis/[id]/ask'
} as const;

export type View = keyof typeof VIEW_ROUTES;

/**
 * Everything the result views share for one analysis: article-level points,
 * clusters with their colors, and the selection — which lives in the URL
 * (?cluster=, ?article=) so any view can be linked to and survives reloads.
 */
export class Workspace {
	readonly articles: ArticlePoint[];
	readonly clusters: ClusterInfo[];
	readonly #byId: Map<number, ClusterInfo>;
	readonly #articleByUrl: Map<string, ArticlePoint>;

	constructor(
		readonly analysis: Analysis,
		mapArticles: MapArticle[],
		apiClusters: Cluster[]
	) {
		this.clusters = summarizeClusters(apiClusters, mapArticles);
		this.articles = toArticlePoints(mapArticles, this.clusters);
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- built once per Workspace, never mutated
		this.#byId = new Map(this.clusters.map((c) => [c.id, c]));
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- built once per Workspace, never mutated
		this.#articleByUrl = new Map(this.articles.map((a) => [a.url, a]));
	}

	cluster(id: number): ClusterInfo | undefined {
		return this.#byId.get(id);
	}

	color(clusterId: number): string {
		return clusterColor(this.#byId.get(clusterId)?.slot ?? null);
	}

	articleByUrl(url: string): ArticlePoint | undefined {
		return this.#articleByUrl.get(url);
	}

	get selectedCluster(): number | null {
		const v = page.url.searchParams.get('cluster');
		const id = v == null ? NaN : Number(v);
		return Number.isInteger(id) && this.#byId.has(id) ? id : null;
	}

	get openArticle(): string | null {
		return page.url.searchParams.get('article');
	}

	selectCluster(id: number | null) {
		this.#setParam('cluster', id == null || id === this.selectedCluster ? null : String(id));
	}

	openArticleById(id: string | null) {
		this.#setParam('article', id);
	}

	/** href for another view of this analysis, carrying the cluster selection */
	viewHref(view: View): string {
		const href = resolve(VIEW_ROUTES[view], { id: this.analysis.id });
		const c = this.selectedCluster;
		return c == null ? href : `${href}?cluster=${c}`;
	}

	#setParam(key: string, value: string | null) {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- throwaway, only used to build the next URL
		const url = new URL(page.url.href);
		if (value == null) url.searchParams.delete(key);
		else url.searchParams.set(key, value);
		// Selection is view state: replace the history entry, keep scroll and focus.
		// Same page, new query: page.url's path already includes any base path.
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		goto(url, { replace: true, reset: false });
	}
}

const KEY = Symbol('workspace');

export function setWorkspace(get: () => Workspace) {
	setContext(KEY, get);
}

export function useWorkspace(): Workspace {
	return (getContext(KEY) as () => Workspace)();
}
