/**
 * Thin wrapper over the generated client (./gen, from the backend's OpenAPI
 * schema): every call returns its data or throws an ApiError carrying the
 * backend's `detail` message and HTTP status.
 */
import { client } from './api/gen/client.gen';
import * as sdk from './api/gen/sdk.gen';
import type { Analysis } from './api/gen/types.gen';

export type {
	Analysis,
	AnalysisEvent,
	Article,
	ChatResponse,
	Citation,
	Cluster,
	MapArticle,
	Term
} from './api/gen/types.gen';

// Same origin in production (FastAPI serves the app); Vite proxies /api in dev.
client.setConfig({ baseUrl: '' });

export type Fetch = typeof fetch;

export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ApiError';
	}
}

type Result<T> = { data?: T; error?: unknown; response?: Response };

async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
	let result: Result<T>;
	try {
		result = await call;
	} catch (e) {
		throw new ApiError(
			`Can't reach the Discourse Lens server. Is the backend running? (${(e as Error).message})`,
			0
		);
	}
	const status = result.response?.status ?? 0;
	if (result.error !== undefined || !result.response?.ok) {
		throw new ApiError(detailOf(result.error) ?? `Request failed (HTTP ${status})`, status);
	}
	return result.data as T;
}

function detailOf(error: unknown): string | undefined {
	if (error && typeof error === 'object' && 'detail' in error) {
		const detail = (error as { detail: unknown }).detail;
		if (typeof detail === 'string') return detail;
		// FastAPI validation errors: [{ msg, loc, ... }]
		if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
	}
	return undefined;
}

const path = (analysis_id: string) => ({ path: { analysis_id } });

export const api = {
	listAnalyses: (fetch?: Fetch) => unwrap(sdk.listAnalyses({ fetch })),
	createAnalysis: (topic: string) => unwrap(sdk.createAnalysis({ body: { topic } })),
	getAnalysis: (id: string, fetch?: Fetch) => unwrap(sdk.getAnalysis({ ...path(id), fetch })),
	deleteAnalysis: (id: string) => unwrap(sdk.deleteAnalysis(path(id))),
	cancelAnalysis: (id: string) => unwrap(sdk.cancelAnalysis(path(id))),
	listArticles: (id: string, fetch?: Fetch) => unwrap(sdk.listArticles({ ...path(id), fetch })),
	getClusters: (id: string, fetch?: Fetch) => unwrap(sdk.getClusters({ ...path(id), fetch })),
	getArticle: (id: string, articleId: string) =>
		unwrap(sdk.getArticle({ path: { analysis_id: id, article_id: articleId } })),
	chat: (id: string, query: string) => unwrap(sdk.chat({ ...path(id), body: { query } }))
};

export const RUNNING: ReadonlyArray<Analysis['status']> = [
	'queued',
	'crawling',
	'processing',
	'embedding',
	'projecting'
];

export const isRunning = (a: Pick<Analysis, 'status'>) => RUNNING.includes(a.status);
