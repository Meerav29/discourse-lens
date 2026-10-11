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
	const points = analysis.status === 'done' ? await api.getCorpus(params.id, fetch) : [];
	return { analysis, points };
};
