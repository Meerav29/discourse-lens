import { api, type Citation } from '#lib/api.ts';

export interface ChatMessage {
	role: 'user' | 'assistant';
	text: string;
	citations?: Citation[];
}

interface Conversation {
	messages: ChatMessage[];
	pending: boolean;
	error: string | null;
	lastQuestion: string | null;
}

/**
 * Conversations live at module level, keyed by analysis, so switching views
 * (which unmounts the Ask page) doesn't throw away the history.
 */
// The registry itself needn't be reactive (it's only ever added to, and is read
// from inside $derived); each conversation is its own reactive object.
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- intentionally not reactive, see above
const conversations = new Map<string, Conversation>();

export function conversation(analysisId: string): Conversation {
	const existing = conversations.get(analysisId);
	if (existing) return existing;
	const fresh: Conversation = $state({
		messages: [],
		pending: false,
		error: null,
		lastQuestion: null
	});
	conversations.set(analysisId, fresh);
	return fresh;
}

export async function ask(analysisId: string, question: string): Promise<void> {
	const c = conversation(analysisId);
	const q = question.trim();
	if (!q || c.pending) return;
	c.lastQuestion = q;
	c.error = null;
	c.messages.push({ role: 'user', text: q });
	c.pending = true;
	try {
		const res = await api.chat(analysisId, q);
		c.messages.push({ role: 'assistant', text: res.answer, citations: res.citations });
	} catch (e) {
		c.error = (e as Error).message;
	} finally {
		c.pending = false;
	}
}

/** Retry the last question after an error, without repeating it in the history. */
export async function retry(analysisId: string): Promise<void> {
	const c = conversation(analysisId);
	if (!c.lastQuestion || c.pending) return;
	if (c.messages.at(-1)?.role === 'user') c.messages.pop();
	await ask(analysisId, c.lastQuestion);
}
