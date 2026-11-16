import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApplicationDetail, ApplicationForm, ApplicationList } from './Applications';
import type { User } from '../types';

const admin: User = { id: '1', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], defaultLandingPage: null, mustChangePassword: false };
const portfolio = { id: 'p1', name: 'Payments', owner: 'Alex', description: '', productArea: 'Payments', status: 'Active', applicationCount: 1, qualityScore: 80, createdAt: 'now', updatedAt: 'now' };
const app = { id: 'a1', name: 'Ledger', description: 'Ledger application', portfolioId: 'p1', productArea: 'Payments', businessOwner: 'Business', technologyOwner: 'Tech', etsOwner: 'ETS', criticality: 'High', tier: 2, lifecycleStatus: 'Active', technologyStack: 'Python', repositoryLink: 'https://example.com/', pipelineLink: null, applicationHealthScore: 80, qualityScore: 90, automationCoverage: 60, unitTestCoverage: 70, openDefects: 4, openCriticalDefects: 1, riskLevel: 'Medium', createdAt: 'now', updatedAt: 'now' };
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

describe('application screens', () => {
  it('renders data and sends URL filter changes', async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => Promise.resolve(response(url.includes('/portfolios') ? page([portfolio]) : page([app]))));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><ApplicationList user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('link', { name: 'Ledger' })).toHaveAttribute('href', '/applications/a1');
    expect(screen.getByRole('cell', { name: 'Payments' })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Risk level'), 'High');
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('riskLevel=High'), expect.anything());
    expect(screen.getByRole('link', { name: 'Create application' })).toBeVisible();
  });
  it('displays API failures and empty results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(response({ detail: 'Permission denied' }, 403))));
    const view = render(<MemoryRouter><ApplicationList user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    view.unmount();
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(response(page([])))));
    render(<MemoryRouter><ApplicationList user={admin} /></MemoryRouter>);
    expect(await screen.findByText('No applications found.')).toBeVisible();
  });
  it('shows full details and hides edit and delete for read only', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app))));
    const reader = { ...admin, role: 'Read Only' };
    render(<MemoryRouter initialEntries={['/applications/a1']}><Routes><Route path="/applications/:id" element={<ApplicationDetail user={reader} />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Ledger' })).toBeVisible();
    expect(screen.getByText('Business')).toBeVisible();
    expect(screen.getByRole('link', { name: 'https://example.com/' })).toHaveAttribute('href', 'https://example.com/');
    expect(screen.queryByRole('link', { name: 'Edit application' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete application' })).not.toBeInTheDocument();
  });
  it('creates a record and navigates to detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options: RequestInit) => Promise.resolve(response(options.method === 'POST' ? app : page([portfolio]), options.method === 'POST' ? 201 : 200))));
    render(<MemoryRouter initialEntries={['/applications/new']}><Routes><Route path="/applications/new" element={<ApplicationForm user={admin} />} /><Route path="/applications/:id" element={<p>Saved detail</p>} /></Routes></MemoryRouter>);
    await screen.findByLabelText('Name');
    await userEvent.type(screen.getByLabelText('Name'), 'Ledger');
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p1');
    await userEvent.click(screen.getByRole('button', { name: 'Save application' }));
    expect(await screen.findByText('Saved detail')).toBeVisible();
  });
  it('retains the form and reports a duplicate error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options: RequestInit) => Promise.resolve(options.method === 'POST' ? response({ detail: 'Application name already exists' }, 409) : response(page([portfolio])))));
    render(<MemoryRouter><ApplicationForm user={admin} /></MemoryRouter>);
    await screen.findByLabelText('Name');
    await userEvent.type(screen.getByLabelText('Name'), 'Ledger');
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p1');
    await userEvent.click(screen.getByRole('button', { name: 'Save application' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Application name already exists');
    expect(screen.getByLabelText('Name')).toHaveValue('Ledger');
  });
});
