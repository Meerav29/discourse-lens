import { api } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, depends }) => {
	depends('app:analyses');
	return { analyses: await api.listAnalyses(fetch) };
};
