<script lang="ts">
	import { AlertDialog } from 'bits-ui';

	let {
		open = $bindable(false),
		title,
		description,
		confirmLabel,
		onconfirm
	}: {
		open?: boolean;
		title: string;
		description: string;
		confirmLabel: string;
		onconfirm: () => void;
	} = $props();
</script>

<AlertDialog.Root bind:open>
	<AlertDialog.Portal>
		<AlertDialog.Overlay class="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[1px]" />
		<AlertDialog.Content
			class="fixed top-1/2 left-1/2 z-50 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-raised p-6 shadow-xl"
		>
			<AlertDialog.Title class="text-lg font-semibold">{title}</AlertDialog.Title>
			<AlertDialog.Description class="mt-2 text-ink-2">{description}</AlertDialog.Description>
			<div class="mt-6 flex justify-end gap-2">
				<AlertDialog.Cancel
					class="rounded-md px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-rule-soft"
				>
					Keep it
				</AlertDialog.Cancel>
				<AlertDialog.Action
					class="rounded-md bg-danger px-3.5 py-2 text-sm font-medium text-paper hover:opacity-90"
					onclick={() => {
						open = false;
						onconfirm();
					}}
				>
					{confirmLabel}
				</AlertDialog.Action>
			</div>
		</AlertDialog.Content>
	</AlertDialog.Portal>
</AlertDialog.Root>
