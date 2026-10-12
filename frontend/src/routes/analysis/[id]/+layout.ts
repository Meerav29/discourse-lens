import { error } from '@sveltejs/kit';
import { api, ApiError } from '#lib/api.ts';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ params, fetch, depends }) => {
	depends('app:analysis');
	let analysis;
	try {
		analysis = await api.getAnalysis(params.id, fetch);
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) {
			error(404, 'There is no map with this address. It may have been deleted.');
		}
		throw e;
	}
	if (analysis.status !== 'done') return { analysis, articles: [], clusters: [] };
	const [articles, clusters] = await Promise.all([
		api.listArticles(params.id, fetch),
		api.getClusters(params.id, fetch)
	]);
	return { analysis, articles, clusters };
};
