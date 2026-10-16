<script lang="ts">
	import { mode, toggleMode } from 'mode-watcher';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';

	const dark = $derived(mode.current === 'dark');
</script>

<button
	type="button"
	onclick={toggleMode}
	class="grid size-9 place-items-center rounded-md text-muted transition-colors hover:bg-rule-soft hover:text-ink"
	aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
	title={dark ? 'Light theme' : 'Dark theme'}
>
	{#if dark}<Sun size={17} />{:else}<Moon size={17} />{/if}
</button>
