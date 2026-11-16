import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
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
