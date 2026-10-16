import { defineConfig } from '@hey-api/openapi-ts';

// Regenerate after backend API changes:
//   (repo root) uv run python -m scripts.export_openapi
//   (frontend)  npm run gen:api
export default defineConfig({
	input: './openapi.json',
	output: {
		path: 'src/lib/api/gen',
		// tsconfig.json extends SvelteKit's $app/tsconfig, which the generator can't resolve
		tsConfigPath: null
	},
	plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk']
});
