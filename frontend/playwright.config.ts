import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

/**
 * End-to-end tests against the real backend serving the built app, seeded with
 * the synthetic demo map (scripts/seed_demo.py) in a throwaway directory —
 * no crawling, no API keys. Run `npm run build` first.
 */
const ROOT = path.resolve(import.meta.dirname, '..');
const DATA = path.join(ROOT, '.e2e');
const PYTHON = path.join(
	ROOT,
	'.venv',
	process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
);
const PORT = 8011;

export default defineConfig({
	testDir: 'e2e',
	fullyParallel: false, // one shared database
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? [['github'], ['list']] : 'list',
	use: {
		baseURL: `http://localhost:${PORT}`,
		trace: 'retain-on-failure'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: {
		command: `"${PYTHON}" -m scripts.seed_demo --reset && "${PYTHON}" -m uvicorn backend.api.main:app --port ${PORT}`,
		cwd: ROOT,
		url: `http://localhost:${PORT}/api/health`,
		reuseExistingServer: false,
		timeout: 120_000,
		env: {
			DB_PATH: path.join(DATA, 'e2e.db'),
			LANCE_PATH: path.join(DATA, 'vectors'),
			// Nothing in these tests may reach the network.
			RECOVER_ACADEMIC: 'false',
			BRAVE_API_KEY: '',
			ANTHROPIC_API_KEY: 'e2e-not-a-real-key',
			OPENAI_API_KEY: 'e2e-not-a-real-key'
		}
	}
});
