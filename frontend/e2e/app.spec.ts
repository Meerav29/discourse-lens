import { expect, test, type Page } from '@playwright/test';

// The synthetic map from scripts/seed_demo.py
const DEMO = '/analysis/demo-0000-0000-0000-000000000001';
const TOPIC = 'Demo: urban heat and city design';

async function openDemo(page: Page, view = '') {
	await page.goto(`${DEMO}${view}`);
	await expect(page.getByRole('heading', { level: 1, name: TOPIC })).toBeVisible();
}

test('home lists the demo map and keeps the start button disabled until a topic is typed', async ({
	page
}) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { name: 'Map a conversation.' })).toBeVisible();
	await expect(page.getByRole('link', { name: TOPIC })).toBeVisible();
	await expect(page.getByText('12 articles')).toBeVisible();

	const start = page.getByRole('button', { name: 'Map this topic' });
	await expect(start).toBeDisabled();
	await page.getByRole('button', { name: 'urban heat islands and city design' }).click();
	await expect(page.getByLabel('Topic')).toHaveValue('urban heat islands and city design');
	await expect(start).toBeEnabled();
});

test('map shows every article, topic labels and the cluster key', async ({ page }) => {
	await openDemo(page);
	await expect(page.getByText('12 articles in 4 clusters')).toBeVisible();
	const map = page.getByRole('img', { name: /Map of 12 articles/ });
	await expect(map.locator('circle[stroke="var(--paper)"]')).toHaveCount(12);
	for (const label of ['Reflective surfaces', 'Trees and green space', 'Heat and inequality']) {
		await expect(map.getByText(label)).toBeVisible();
	}
	await expect(
		page.getByRole('complementary', { name: 'Clusters' }).getByText('Unclustered')
	).toBeVisible();
});

test('selecting a topic focuses every view and shows its summary', async ({ page }) => {
	await openDemo(page);
	const key = page.getByRole('complementary', { name: 'Clusters' });
	await key.getByRole('button', { name: /Trees and green space/ }).click();
	await expect(page).toHaveURL(/\?cluster=1/);
	await expect(key.getByText('canopy, parks and the upkeep', { exact: false })).toBeVisible();

	// The selection travels with the view links.
	await page.getByRole('link', { name: 'Outliers' }).click();
	await expect(page).toHaveURL(/\/outliers\?cluster=1/);
	await expect(page.getByRole('main').getByRole('button')).toHaveCount(4);
	await expect(page.getByRole('main').getByText('Watering trees in drought summers')).toBeVisible();

	await key.getByRole('button', { name: 'Show all' }).click();
	await expect(page).not.toHaveURL(/cluster=/);
});

test('table view lists articles and opens the reader, which closes with Escape', async ({
	page
}) => {
	await openDemo(page);
	await page.getByRole('button', { name: 'Table' }).click();
	await page.getByRole('button', { name: 'Measuring albedo on city blocks' }).click();

	const reader = page.getByRole('dialog');
	await expect(
		reader.getByRole('heading', { name: 'Measuring albedo on city blocks' })
	).toBeVisible();
	await expect(reader.getByText(/Abstract only/)).toBeVisible();
	await expect(page).toHaveURL(/article=demo-article-02/);

	await page.keyboard.press('Escape');
	await expect(reader).toBeHidden();
	await expect(page).not.toHaveURL(/article=/);
});

test('timeline draws a bar for each dated year', async ({ page }) => {
	await openDemo(page, '/timeline');
	await expect(page.getByText('12 articles have a publish date')).toBeVisible();
	await expect(page.getByRole('img', { name: /per year/ })).toBeVisible();
});

test('key terms show each topic with its summary and terms', async ({ page }) => {
	await openDemo(page, '/terms');
	const main = page.getByRole('main');
	await expect(main.getByRole('heading', { name: /Heat and inequality/ })).toBeVisible();
	await expect(main.getByText('Who is most exposed', { exact: false })).toBeVisible();
	await expect(main.getByText('redlining')).toBeVisible();
});

test('saved conversation renders with clickable citations', async ({ page }) => {
	await openDemo(page, '/ask');
	await expect(page.getByText('Do cool roofs or trees cool cities more?')).toBeVisible();
	const cite = page.getByRole('button', { name: /Source 2:/ });
	await expect(cite).toBeVisible();
	await expect(page.getByText('Also searched, not cited (1)')).toBeVisible();

	await cite.click();
	await expect(
		page.getByRole('dialog').getByRole('heading', { name: 'Street trees and shade equity' })
	).toBeVisible();
});

test('theme toggle switches to dark and remembers it', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('button', { name: 'Switch to dark theme' }).click();
	await expect(page.locator('html')).toHaveClass(/dark/);
	await page.reload();
	await expect(page.locator('html')).toHaveClass(/dark/);
});

test('an unknown map shows a helpful not-found page', async ({ page }) => {
	await page.goto('/analysis/does-not-exist');
	await expect(page.getByRole('heading', { name: 'Not found' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Back to all maps' })).toBeVisible();
});

test('claims show where articles agree and open the source', async ({ page }) => {
	await openDemo(page, '/claims');
	const main = page.getByRole('main');
	const debated = main.getByRole('button', { name: /Cool roofs are the most effective/ });
	// Most debated first: the contested point leads.
	await expect(main.getByRole('button', { expanded: false }).first()).toHaveAccessibleName(
		/Cool roofs are the most effective/
	);
	await expect(debated).toContainText('3 articles: 1 agree, 1 qualify, 1 dispute');

	await debated.click();
	await expect(main.getByText('Street trees cool pavements and people')).toBeVisible();
	await main.getByRole('button', { name: /Street trees and shade equity/ }).click();
	await expect(
		page.getByRole('dialog').getByRole('heading', { name: 'Street trees and shade equity' })
	).toBeVisible();
});
