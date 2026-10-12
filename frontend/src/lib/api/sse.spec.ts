import { describe, expect, it } from 'vitest';
import { SseParser } from './sse';

describe('SseParser', () => {
	it('parses named events with JSON data', () => {
		const events = new SseParser().push(
			'event: delta\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n'
		);
		expect(events).toEqual([
			{ event: 'delta', data: '{"text":"Hi"}' },
			{ event: 'done', data: '{}' }
		]);
	});

	it('buffers events split across chunks', () => {
		const p = new SseParser();
		expect(p.push('event: delta\nda')).toEqual([]);
		expect(p.push('ta: {"text":"a"}\n')).toEqual([]);
		expect(p.push('\nevent: done\ndata: 1\n\n')).toEqual([
			{ event: 'delta', data: '{"text":"a"}' },
			{ event: 'done', data: '1' }
		]);
	});

	it('handles CRLF, comments, default event names and multi-line data', () => {
		const events = new SseParser().push(': keep-alive\r\n\r\ndata: one\r\ndata: two\r\n\r\n');
		expect(events).toEqual([{ event: 'message', data: 'one\ntwo' }]);
	});
});
