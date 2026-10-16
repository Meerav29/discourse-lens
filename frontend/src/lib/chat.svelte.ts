import { api, ApiError, type ChatMessage, type ChatSource } from '#lib/api.ts';

export interface Draft {
	question: string;
	text: string;
	sources: ChatSource[];
}

interface Conversation {
	loaded: boolean;
	loadError: string | null;
	/** Saved turns, oldest first */
	messages: ChatMessage[];
	/** The answer being streamed right now */
	draft: Draft | null;
	error: string | null;
	failedQuestion: string | null;
	controller: AbortController | null;
}

/**
 * One conversation per analysis, kept at module level so switching views
 * (which unmounts the Ask page) doesn't lose it — an answer keeps streaming
 * in the background. Saved history comes from the server.
 */
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- registry only grows; each conversation is reactive
const conversations = new Map<string, Conversation>();

export function conversation(analysisId: string): Conversation {
	const existing = conversations.get(analysisId);
	if (existing) return existing;
	const fresh: Conversation = $state({
		loaded: false,
		loadError: null,
		messages: [],
		draft: null,
		error: null,
		failedQuestion: null,
		controller: null
	});
	conversations.set(analysisId, fresh);
	return fresh;
}

export async function loadHistory(analysisId: string): Promise<void> {
	const c = conversation(analysisId);
	if (c.loaded) return;
	try {
		c.messages = await api.getChat(analysisId);
		c.loaded = true;
		c.loadError = null;
	} catch (e) {
		c.loadError = (e as Error).message;
	}
}

export async function ask(analysisId: string, question: string): Promise<void> {
	const c = conversation(analysisId);
	const q = question.trim();
	if (!q || c.draft) return;
	c.error = null;
	c.failedQuestion = null;
	c.draft = { question: q, text: '', sources: [] };
	c.controller = new AbortController();
	try {
		const saved = await api.ask(
			analysisId,
			q,
			{
				onSources: (sources) => c.draft && (c.draft.sources = sources),
				onText: (piece) => c.draft && (c.draft.text += piece)
			},
			c.controller.signal
		);
		c.messages.push(
			{ id: -saved.id, role: 'user', text: q, sources: null, created_ts: saved.created_ts },
			saved
		);
	} catch (e) {
		if ((e as Error).name !== 'AbortError') {
			c.error = e instanceof ApiError ? e.message : `Something went wrong: ${(e as Error).message}`;
			c.failedQuestion = q;
		}
	} finally {
		c.draft = null;
		c.controller = null;
	}
}

/** Stop the answer being written; nothing from it is saved. */
export function stop(analysisId: string): void {
	conversation(analysisId).controller?.abort();
}

export async function retry(analysisId: string): Promise<void> {
	const c = conversation(analysisId);
	if (c.failedQuestion) await ask(analysisId, c.failedQuestion);
}

export async function clear(analysisId: string): Promise<void> {
	const c = conversation(analysisId);
	stop(analysisId);
	await api.clearChat(analysisId);
	c.messages = [];
	c.error = null;
	c.failedQuestion = null;
}
