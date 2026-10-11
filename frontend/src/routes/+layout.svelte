<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Discourse Lens</title>
</svelte:head>

<ModeWatcher />
<Toaster position="bottom-right" toastOptions={{ class: 'font-sans' }} />

{@render children()}
