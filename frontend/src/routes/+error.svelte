<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
</script>

<main class="mx-auto max-w-xl px-4 py-24 sm:px-8">
	<h1 class="text-3xl display">{page.status === 404 ? 'Not found' : 'Something went wrong'}</h1>
	<p class="mt-3 text-ink-2">{page.error?.message ?? 'An unexpected error occurred.'}</p>
	<a href={resolve('/')} class="mt-8 inline-block font-medium underline underline-offset-4"
		>Back to all maps</a
	>
</main>
