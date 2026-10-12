/**
 * Minimal server-sent-events parser for fetch() response bodies
 * (EventSource only does GET; asking a question is a POST).
 */

export interface SseEvent {
	event: string;
	data: string;
}

/** Feed decoded text chunks in; complete events come out. Keeps partial events buffered. */
export class SseParser {
	#buffer = '';

	push(chunk: string): SseEvent[] {
		this.#buffer += chunk.replace(/\r\n?/g, '\n');
		const events: SseEvent[] = [];
		let end: number;
		while ((end = this.#buffer.indexOf('\n\n')) !== -1) {
			const block = this.#buffer.slice(0, end);
			this.#buffer = this.#buffer.slice(end + 2);
			const parsed = parseBlock(block);
			if (parsed) events.push(parsed);
		}
		return events;
	}
}

function parseBlock(block: string): SseEvent | null {
	let event = 'message';
	const data: string[] = [];
	for (const line of block.split('\n')) {
		if (!line || line.startsWith(':')) continue;
		const colon = line.indexOf(':');
		const field = colon === -1 ? line : line.slice(0, colon);
		const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '');
		if (field === 'event') event = value;
		else if (field === 'data') data.push(value);
	}
	return data.length ? { event, data: data.join('\n') } : null;
}

export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
	const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
	const parser = new SseParser();
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			yield* parser.push(value);
		}
	} finally {
		reader.releaseLock();
	}
}
