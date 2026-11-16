import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PortfolioDetail, PortfolioForm, PortfolioList } from './Portfolios';
import type { User } from '../types';

const admin: User = { id: '1', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], defaultLandingPage: null, mustChangePassword: false };
const item = { id: '123', name: 'Payments', owner: 'Alex', productArea: 'Payments', description: 'Payments systems', status: 'Active', applicationCount: 1, qualityScore: 80, createdAt: 'now', updatedAt: 'now' };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

describe('portfolio screens', () => {
  it('renders list and updates URL filters', async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ items: [item], total: 1, limit: 25, offset: 0 }));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/portfolios']}><PortfolioList user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/portfolios/123');
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Archived');
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining('status=Archived'), expect.anything());
    expect(screen.getByRole('link', { name: 'Create portfolio' })).toHaveAttribute('href', '/portfolios/new');
  });
  it('shows list errors instead of results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Permission denied' }, 403)));
    render(<MemoryRouter><PortfolioList user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
  });
  it('renders detail and linked application', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(response(url.includes('/applications') ? { items: [{ id: 'app1', name: 'Ledger' }], total: 1, limit: 25, offset: 0 } : item))));
    render(<MemoryRouter initialEntries={['/portfolios/123']}><Routes><Route path="/portfolios/:id" element={<PortfolioDetail user={admin} />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Payments' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ledger' })).toHaveAttribute('href', '/applications/app1');
  });
  it('shows save conflict and preserves entered values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Portfolio name already exists' }, 409)));
    render(<MemoryRouter><PortfolioForm user={admin} /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Name'), 'Payments');
    await userEvent.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio name already exists');
    expect(screen.getByLabelText('Name')).toHaveValue('Payments');
  });
  it('creates a portfolio and navigates to its detail route', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(item, 201)));
    render(<MemoryRouter initialEntries={['/portfolios/new']}><Routes><Route path="/portfolios/new" element={<PortfolioForm user={admin} />} /><Route path="/portfolios/:id" element={<p>Saved detail</p>} /></Routes></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Name'), 'Payments');
    await userEvent.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(await screen.findByText('Saved detail')).toBeVisible();
  });
});
