import type { Analysis, AnalysisEvent } from '#lib/api.ts';

export interface StreamHandlers {
	onAnalysis: (analysis: Analysis) => void;
	onEvent: (event: AnalysisEvent) => void;
	onGone?: () => void;
}

/**
 * Follow an analysis over server-sent events. Analysis updates arrive as
 * default messages, log rows as `log` events with ids (EventSource resends
 * Last-Event-ID on reconnect, so nothing is duplicated or lost).
 * The server closes the stream once the analysis stops running; we close the
 * EventSource then too, instead of letting it reconnect forever.
 * Returns a function that stops listening.
 */
export function followAnalysis(id: string, handlers: StreamHandlers): () => void {
	const source = new EventSource(`/api/analyses/${encodeURIComponent(id)}/stream`);
	let finished = false;

	source.onmessage = (e) => {
		const analysis = JSON.parse(e.data) as Analysis;
		handlers.onAnalysis(analysis);
		if (
			!['queued', 'crawling', 'reviewing', 'processing', 'embedding', 'projecting'].includes(
				analysis.status
			)
		) {
			finished = true;
			source.close();
		}
	};
	source.addEventListener('log', (e) => {
		handlers.onEvent(JSON.parse((e as MessageEvent).data) as AnalysisEvent);
	});
	// Server-sent `event: error` carries a body (the analysis was deleted).
	source.addEventListener('error', (e) => {
		if ((e as MessageEvent).data) {
			finished = true;
			source.close();
			handlers.onGone?.();
		} else if (finished) {
			source.close();
		}
		// Otherwise: a dropped connection — EventSource retries on its own.
	});

	return () => source.close();
}
