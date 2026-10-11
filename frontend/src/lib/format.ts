const dateFmt = new Intl.DateTimeFormat(undefined, {
	day: 'numeric',
	month: 'short',
	year: 'numeric'
});
const monthFmt = new Intl.DateTimeFormat(undefined, {
	month: 'short',
	year: 'numeric',
	timeZone: 'UTC'
});
const yearFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', timeZone: 'UTC' });

/** Unix seconds → "11 Oct 2026" */
export function formatTimestamp(ts: number): string {
	return dateFmt.format(new Date(ts * 1000));
}

/** "2024-03-15" / "2024-03" → "Mar 2024"; null → null */
export function formatPublishDate(date: string | null | undefined): string | null {
	const m = date?.match(/^(\d{4})-(\d{2})/);
	if (!m) return null;
	return monthFmt.format(new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 1)));
}

export function formatBin(start: Date, unit: 'month' | 'year'): string {
	return (unit === 'year' ? yearFmt : monthFmt).format(start);
}

export function plural(n: number, one: string, many = `${one}s`): string {
	return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/** Seconds → "3 min 20 s" / "45 s" */
export function formatDuration(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 60) return `${s} s`;
	return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
}
