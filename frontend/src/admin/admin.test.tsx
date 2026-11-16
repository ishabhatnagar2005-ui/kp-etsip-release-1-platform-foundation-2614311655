import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Admin from './Admin';
import type { User } from '../types';

const admin: User = { id: '1', name: 'Admin', email: 'admin@example.com', role: 'Administrator', portfolioAccess: [], defaultLandingPage: null, mustChangePassword: false, effectivePermissions: ['administer', 'view', 'export'] };
const auditor: User = { ...admin, role: 'Auditor', effectivePermissions: ['view', 'export'] };
const page = (items: unknown[]) => ({ items, total: items.length, offset: 0, limit: 25 });
const result = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

describe('administration', () => {
  it('waits for every portfolio page before saving an existing user and preserves assignments', async () => {
    const person = { id: 'p1', name: 'Existing Person', email: 'person@example.com', role: 'Engineer', portfolioAccess: ['port2'], status: 'Active', managerName: null, vendorIndicator: false, defaultLandingPage: null, authSource: 'local', lastLogin: null, createdAt: 'now', updatedAt: 'now' };
    let resolveSecondPage!: (response: Response) => void;
    const secondPage = new Promise<Response>((resolve) => { resolveSecondPage = resolve; });
    const fetcher = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (url.includes('/portfolios') && url.includes('offset=0')) return Promise.resolve(result({ items: [{ id: 'port1', name: 'Payments' }], total: 2, offset: 0, limit: 100 }));
      if (url.includes('/portfolios')) return secondPage;
      if (options.method === 'PUT') return Promise.resolve(result(person));
      if (url.includes('/users/p1')) return Promise.resolve(result(person));
      return Promise.resolve(result(page([person])));
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: 'Existing Person' }));
    await userEvent.click(screen.getByRole('button', { name: 'Edit user' }));
    expect(screen.getByText(/loading portfolios/i)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Save user' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('button', { name: 'Save user' }).closest('form')!);
    expect(fetcher.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false);
    await act(async () => { resolveSecondPage(result({ items: [{ id: 'port2', name: 'Operations' }], total: 2, offset: 1, limit: 100 })); });
    expect(await screen.findByLabelText('Operations')).toBeChecked();
    expect(screen.getByRole('button', { name: 'Save user' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByText('User saved.')).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/api/users/p1'), expect.objectContaining({ method: 'PUT', body: expect.stringContaining('"portfolioAccess":["port2"]') }));
  });
  it('keeps portfolio errors separate, blocks saving, and retries without losing form values', async () => {
    let portfolioAttempts = 0;
    const fetcher = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (url.includes('/portfolios')) {
        portfolioAttempts += 1;
        return Promise.resolve(portfolioAttempts === 1 ? result({ detail: 'Portfolio service unavailable' }, 503) : result(page([{ id: 'port1', name: 'Payments' }])));
      }
      if (options.method === 'POST') return Promise.resolve(result({ id: 'new', name: 'Draft', email: 'draft@example.com', role: 'Engineer', portfolioAccess: ['port1'], status: 'Active' }, 201));
      return Promise.resolve(result(page([])));
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio service unavailable');
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Draft');
    await userEvent.type(screen.getByLabelText('Email'), 'draft@example.com');
    await userEvent.type(screen.getByLabelText('Initial password'), 'Strong-password-123');
    expect(screen.getByRole('alert')).toHaveTextContent('Portfolio service unavailable');
    expect(screen.getByRole('button', { name: 'Save user' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /retry portfolios/i }));
    await userEvent.click(await screen.findByLabelText('Payments'));
    expect(screen.getByLabelText('Name')).toHaveValue('Draft');
    expect(screen.getByRole('button', { name: 'Save user' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByText('User saved.')).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/api/users'), expect.objectContaining({ method: 'POST', body: expect.stringContaining('"portfolioAccess":["port1"]') }));
  });
  it('creates a user with role and portfolio assignments and displays the result', async () => {
    const person = { id: 'p1', name: 'New Person', email: 'person@example.com', role: 'Engineer', portfolioAccess: ['port1'], status: 'Active', managerName: null, vendorIndicator: false, defaultLandingPage: null, authSource: 'local', lastLogin: null, createdAt: 'now', updatedAt: 'now' };
    const fetcher = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (url.includes('/portfolios')) return Promise.resolve(result(page([{ id: 'port1', name: 'Payments' }])));
      if (options.method === 'POST') return Promise.resolve(result(person, 201));
      return Promise.resolve(result(page([])));
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/admin?tab=users']}><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }));
    await userEvent.type(screen.getByLabelText('Name'), 'New Person');
    await userEvent.type(screen.getByLabelText('Email'), 'person@example.com');
    await userEvent.type(screen.getByLabelText('Initial password'), 'Strong-password-123');
    await userEvent.click(await screen.findByLabelText('Payments'));
    await userEvent.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByRole('heading', { name: 'New Person' })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/api/users'), expect.objectContaining({ method: 'POST', body: expect.stringContaining('port1') }));
  });
  it('shows save errors and retains the form values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options: RequestInit) => Promise.resolve(options.method === 'POST' ? result({ detail: 'Email already exists' }, 409) : result(page([])))));
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Duplicate');
    await userEvent.type(screen.getByLabelText('Email'), 'duplicate@example.com');
    await userEvent.type(screen.getByLabelText('Initial password'), 'Strong-password-123');
    await userEvent.click(screen.getByRole('button', { name: 'Save user' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already exists');
    expect(screen.getByLabelText('Name')).toHaveValue('Duplicate');
  });
  it('shows list failures and empty results without inventing users', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(url.includes('/portfolios') ? result(page([])) : result({ detail: 'Users unavailable' }, 503))));
    const view = render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Users unavailable');
    expect(screen.queryByText('No users found.')).not.toBeInTheDocument();
    view.unmount();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(result(page([]))));
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    expect(await screen.findByText('No users found.')).toBeVisible();
  });
  it('reports missing user detail and does not open an edit form', async () => {
    const person = { id: 'gone', name: 'Removed User', email: 'gone@example.com', role: 'Engineer', status: 'Active' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(url.includes('/portfolios') ? result(page([])) : url.includes('/users/gone') ? result({ detail: 'User not found' }, 404) : result(page([person])))));
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: 'Removed User' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('User not found');
    expect(screen.queryByRole('button', { name: 'Edit user' })).not.toBeInTheDocument();
  });
  it('prevents an empty create form from submitting', async () => {
    const fetcher = vi.fn().mockResolvedValue(result(page([])));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save user' }));
    expect(screen.getByLabelText('Name')).toBeInvalid();
    expect(fetcher.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false);
  });
  it('lets auditors filter audit events but hides management', async () => {
    const fetcher = vi.fn().mockResolvedValue(result(page([{ id: 'log', timestamp: 'now', userId: '1', userName: 'Admin', action: 'edit', entityType: 'user', entityId: '2', details: 'User updated' }])));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/admin?tab=audit']}><Admin user={auditor} /></MemoryRouter>);
    expect(await screen.findByText('User updated')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Action'), 'edit');
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining('action=edit'), expect.anything());
  });
  it('edits role permissions and reports success', async () => {
    const role = { id: 'r1', name: 'Engineer', description: 'Engineering', permissions: ['view'], createdAt: 'now', updatedAt: 'now' };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options: RequestInit) => Promise.resolve(url.includes('/portfolios') ? result(page([])) : options.method === 'PUT' ? result({ ...role, permissions: ['view', 'create'] }) : result(page([role])))));
    render(<MemoryRouter initialEntries={['/admin?tab=roles']}><Admin user={admin} /></MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: 'Engineer' }));
    await userEvent.click(screen.getByLabelText('create'));
    await userEvent.click(screen.getByRole('button', { name: 'Save role' }));
    expect(await screen.findByText('Role saved.')).toBeVisible();
  });
});
