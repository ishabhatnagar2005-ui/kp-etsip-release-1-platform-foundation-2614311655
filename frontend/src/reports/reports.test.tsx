import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Reports from './Reports';
import { ApplicationList } from '../applications/Applications';
import type { User } from '../types';

const user: User = { id: '1', name: 'Executive', email: 'test@example.com', role: 'Executive', portfolioAccess: [], defaultLandingPage: null, mustChangePassword: false, effectivePermissions: ['view', 'export'] };
const app = { id: 'a', name: 'Ledger', portfolioId: 'p', criticality: 'High', tier: 1, lifecycleStatus: 'Active', applicationHealthScore: 80, automationCoverage: 60, openCriticalDefects: 1, riskLevel: 'High' };
const portfolio = { id: 'p', name: 'Payments', owner: 'Owner', productArea: 'Area', status: 'Active', applicationCount: 1, qualityScore: 90 };
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('reports', () => {
  it('shows both report tables and navigates with URL filters', async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => Promise.resolve(response(page(url.includes('/reports/applications') ? [app] : [portfolio]))));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/reports']}><Reports user={user} /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Ledger' })).toHaveAttribute('href', '/applications/a');
    await userEvent.selectOptions(screen.getByLabelText('Risk level'), 'High');
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('riskLevel=High'), expect.anything()));
    await userEvent.click(screen.getByRole('link', { name: 'Portfolio Report' }));
    expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute('href', '/portfolios/p');
    expect(screen.getByText('90')).toBeVisible();
  });

  it('shows errors and suppresses export for Read Only even if granted', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(url.includes('/reports/') ? response({ detail: 'Permission denied' }, 403) : response(page([])))));
    render(<MemoryRouter><Reports user={{ ...user, role: 'Read Only' }} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
  });

  it('exports filtered CSV and displays server errors', async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.includes('format=csv')) return Promise.resolve(response({ detail: 'Too many rows' }, 422));
      return Promise.resolve(response(page(url.includes('/reports/') ? [app] : [portfolio])));
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/reports?search=Ledger&offset=25']}><Reports user={user} /></MemoryRouter>);
    await screen.findByRole('link', { name: 'Ledger' });
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many rows');
    expect(fetcher).toHaveBeenCalledWith('/api/reports/applications?search=Ledger&format=csv', expect.anything());
  });

  it('downloads CSV and the application list uses the same scoped endpoint', async () => {
    sessionStorage.setItem('etsip_token', 'token');
    const fetcher = vi.fn().mockImplementation((url: string) => Promise.resolve(url.includes('format=csv') ? new Response('name\nLedger\n') : response(page(url.includes('/applications') ? [app] : [portfolio]))));
    vi.stubGlobal('fetch', fetcher);
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<MemoryRouter initialEntries={['/applications?riskLevel=High&offset=25']}><ApplicationList user={user} /></MemoryRouter>);
    await screen.findByRole('link', { name: 'Ledger' });
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith('/api/reports/applications?riskLevel=High&format=csv', { headers: { Authorization: 'Bearer token' } }));
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test'));
  });
});
