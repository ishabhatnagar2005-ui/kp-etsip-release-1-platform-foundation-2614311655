import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import Reports from './Reports';
import { ApplicationForm, ApplicationList } from '../applications/Applications';
import { fetchPortfolioOptions } from '../portfolioOptions';
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

  it('loads later portfolio pages for report and application filters and resolves names', async () => {
    const all = Array.from({ length: 105 }, (_, i) => ({ ...portfolio, id: `p${i}`, name: `Portfolio ${i}` }));
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/portfolios?')) {
        const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset') || 0);
        return Promise.resolve(response({ items: all.slice(offset, offset + 100), total: 105, limit: 100, offset }));
      }
      return Promise.resolve(response(page([{ ...app, portfolioId: 'p104' }])));
    });
    vi.stubGlobal('fetch', fetcher);
    const view = render(<MemoryRouter><Reports user={user} /></MemoryRouter>);
    await screen.findByRole('option', { name: 'Portfolio 104' });
    expect(screen.getByRole('cell', { name: 'Portfolio 104' })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p104');
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('portfolioId=p104'), expect.anything()));
    view.unmount();
    render(<MemoryRouter><ApplicationList user={user} /></MemoryRouter>);
    await screen.findByRole('option', { name: 'Portfolio 104' });
    expect(screen.getByRole('cell', { name: 'Portfolio 104' })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p104');
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/applications?portfolioId=p104'), expect.anything()));
  });

  it('offers later in-scope portfolios in create and edit forms', async () => {
    const all = Array.from({ length: 105 }, (_, i) => ({ ...portfolio, id: `p${i}`, name: `Portfolio ${i}` }));
    const leader: User = { ...user, role: 'Portfolio Leader', portfolioAccess: ['p104'], effectivePermissions: ['view', 'create', 'edit'] };
    const item = { ...app, portfolioId: 'p104', description: '', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '', technologyStack: '', repositoryLink: null, pipelineLink: null, qualityScore: 0, unitTestCoverage: 0, openDefects: 0, createdAt: 'now', updatedAt: 'now' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/portfolios?')) {
        const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset') || 0);
        return Promise.resolve(response({ items: all.slice(offset, offset + 100), total: 105, limit: 100, offset }));
      }
      return Promise.resolve(response(item));
    }));
    const view = render(<MemoryRouter><ApplicationForm user={leader} /></MemoryRouter>);
    await screen.findByRole('option', { name: 'Portfolio 104' });
    expect(screen.queryByRole('option', { name: 'Portfolio 0' })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p104');
    expect(screen.getByLabelText('Portfolio')).toHaveValue('p104');
    view.unmount();
    render(<MemoryRouter initialEntries={['/applications/a/edit']}><Routes><Route path="/applications/:id/edit" element={<ApplicationForm user={leader} edit />} /></Routes></MemoryRouter>);
    await screen.findByRole('option', { name: 'Portfolio 104' });
    expect(screen.getByLabelText('Portfolio')).toHaveValue('p104');
  });

  it('shows later-page failures without offering incomplete choices or an editable form', async () => {
    const first = Array.from({ length: 100 }, (_, i) => ({ ...portfolio, id: `p${i}` }));
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/portfolios?')) {
        return Promise.resolve(url.includes('offset=100')
          ? response({ detail: 'Portfolio service unavailable' }, 503)
          : response({ items: first, total: 101, limit: 100, offset: 0 }));
      }
      return Promise.resolve(response(page([app])));
    }));
    const view = render(<MemoryRouter><Reports user={user} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio service unavailable');
    expect(screen.getByLabelText('Portfolio')).toBeDisabled();
    expect(screen.queryByRole('option', { name: 'Payments' })).not.toBeInTheDocument();
    view.unmount();
    render(<MemoryRouter><ApplicationForm user={{ ...user, role: 'Administrator', effectivePermissions: ['create'] }} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio service unavailable');
    expect(screen.queryByRole('button', { name: 'Save application' })).not.toBeInTheDocument();
  });

  it('does not let an older form request overwrite a newer edit', async () => {
    let resolveOld!: (response: Response) => void;
    const item = { ...app, description: '', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '', technologyStack: '', repositoryLink: null, pipelineLink: null, qualityScore: 0, unitTestCoverage: 0, openDefects: 0, createdAt: 'now', updatedAt: 'now' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/portfolios?')) return Promise.resolve(response(page([portfolio])));
      if (url.includes('/applications/old')) return new Promise<Response>(resolve => { resolveOld = resolve; });
      return Promise.resolve(response({ ...item, id: 'new', name: 'New application' }));
    }));
    const editor = { ...user, role: 'Administrator', effectivePermissions: ['edit'] };
    render(<MemoryRouter initialEntries={['/applications/old/edit']}><Link to="/applications/new/edit">Switch</Link><Routes><Route path="/applications/:id/edit" element={<ApplicationForm user={editor} edit />} /></Routes></MemoryRouter>);
    await userEvent.click(screen.getByRole('link', { name: 'Switch' }));
    expect(await screen.findByDisplayValue('New application')).toBeVisible();
    await act(async () => resolveOld(response({ ...item, id: 'old', name: 'Old application' })));
    expect(screen.getByLabelText('Name')).toHaveValue('New application');
  });

  it('discards stale portfolio choices when report user scope changes', async () => {
    let resolveOld!: (response: Response) => void;
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/portfolios?')) {
        calls += 1;
        if (calls === 1) return new Promise<Response>(resolve => { resolveOld = resolve; });
        return Promise.resolve(response(page([{ ...portfolio, id: 'new', name: 'New scope' }])));
      }
      return Promise.resolve(response(page([])));
    }));
    const view = render(<MemoryRouter><Reports user={user} /></MemoryRouter>);
    view.rerender(<MemoryRouter><Reports user={{ ...user, id: 'other' }} /></MemoryRouter>);
    await screen.findByRole('option', { name: 'New scope' });
    await act(async () => resolveOld(response(page([{ ...portfolio, name: 'Old scope' }]))));
    expect(screen.queryByRole('option', { name: 'Old scope' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'New scope' })).toBeVisible();
  });

  it('rejects pagination that cannot make progress rather than returning partial options', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], total: 1, limit: 100, offset: 0 });
    await expect(fetchPortfolioOptions(request)).rejects.toThrow('Incomplete portfolio pagination');
    expect(request).toHaveBeenCalledTimes(1);
    await expect(fetchPortfolioOptions(vi.fn().mockResolvedValue({ items: [], total: 0, limit: 0, offset: 0 }))).rejects.toThrow('Invalid portfolio pagination');
  });
});
