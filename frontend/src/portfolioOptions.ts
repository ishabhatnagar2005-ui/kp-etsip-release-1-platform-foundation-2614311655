import type { Page, Portfolio } from './types';

/** Collect all visible portfolios, rejecting incomplete or invalid pagination. */
export async function fetchPortfolioOptions(
  request: (path: string) => Promise<Page<Portfolio>>,
): Promise<Portfolio[]> {
  const portfolios: Portfolio[] = [];
  let offset = 0;

  while (true) {
    const page = await request(`/portfolios?limit=100${offset ? `&offset=${offset}` : ''}`);
    if (
      !Array.isArray(page.items) ||
      !Number.isSafeInteger(page.total) || page.total < 0 ||
      !Number.isSafeInteger(page.limit) || page.limit <= 0 ||
      page.offset !== offset || page.items.length > page.limit
    ) {
      throw new Error('Invalid portfolio pagination response.');
    }
    portfolios.push(...page.items);
    if (offset + page.items.length >= page.total) return portfolios;
    if (page.items.length === 0) throw new Error('Incomplete portfolio pagination response.');
    offset += page.items.length;
  }
}
