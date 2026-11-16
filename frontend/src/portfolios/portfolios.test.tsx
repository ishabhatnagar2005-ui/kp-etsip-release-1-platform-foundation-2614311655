import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PortfolioDetail, PortfolioForm, PortfolioList } from './Portfolios';
import type { User } from '../types';

const admin: User = {
  id: '1',
  name: 'Admin',
  email: 'admin@example.com',
  role: 'Administrator',
  portfolioAccess: [],
  defaultLandingPage: null,
  mustChangePassword: false,
  effectivePermissions: ['view', 'create', 'edit', 'delete'],
};
const item = {
  id: '123',
  name: 'Payments',
  owner: 'Alex',
  productArea: 'Payments',
  description: 'Payments systems',
  status: 'Active',
  applicationCount: 1,
  qualityScore: 80,
  createdAt: 'now',
  updatedAt: 'now',
};
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe('portfolio screens', () => {
  it('renders list and updates URL filters', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response({ items: [item], total: 1, limit: 25, offset: 0 }));
    vi.stubGlobal('fetch', fetcher);
    render(
      <MemoryRouter initialEntries={['/portfolios']}>
        <PortfolioList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('link', { name: 'Payments' })).toHaveAttribute(
      'href',
      '/portfolios/123',
    );
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Archived');
    expect(fetcher).toHaveBeenLastCalledWith(
      expect.stringContaining('status=Archived'),
      expect.anything(),
    );
    expect(screen.getByRole('link', { name: 'Create portfolio' })).toHaveAttribute(
      'href',
      '/portfolios/new',
    );
  });
  it('hides create and denies the direct form when create is revoked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ items: [], total: 0, limit: 25, offset: 0 })),
    );
    const user = { ...admin, effectivePermissions: ['view', 'edit', 'delete'] };
    const list = render(
      <MemoryRouter>
        <PortfolioList user={user} />
      </MemoryRouter>,
    );
    await screen.findByText('No portfolios found.');
    expect(screen.queryByRole('link', { name: 'Create portfolio' })).not.toBeInTheDocument();
    list.unmount();
    render(
      <MemoryRouter>
        <PortfolioForm user={user} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You cannot change this portfolio.');
    expect(screen.queryByRole('button', { name: 'Save portfolio' })).not.toBeInTheDocument();
  });
  it('hides revoked edit and delete controls and denies direct edit', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(
            response(
              url.includes('/applications') ? { items: [], total: 0, limit: 25, offset: 0 } : item,
            ),
          ),
        ),
    );
    const user = { ...admin, effectivePermissions: ['view', 'create'] };
    const detail = render(
      <MemoryRouter initialEntries={['/portfolios/123']}>
        <Routes>
          <Route
            path="/portfolios/:id"
            element={<PortfolioDetail user={user} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Payments' });
    expect(screen.queryByRole('link', { name: 'Edit portfolio' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete portfolio' })).not.toBeInTheDocument();
    detail.unmount();
    render(
      <MemoryRouter initialEntries={['/portfolios/123/edit']}>
        <Routes>
          <Route
            path="/portfolios/:id/edit"
            element={
              <PortfolioForm
                user={user}
                edit
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You cannot change this portfolio.');
  });
  it.each([
    { permission: 'edit', visible: 'Delete portfolio', hidden: 'Edit portfolio' },
    { permission: 'delete', visible: 'Edit portfolio', hidden: 'Delete portfolio' },
  ])(
    'independently honors revoked $permission permission',
    async ({ permission, visible, hidden }) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockImplementation((url: string) =>
            Promise.resolve(
              response(
                url.includes('/applications')
                  ? { items: [], total: 0, limit: 25, offset: 0 }
                  : item,
              ),
            ),
          ),
      );
      const user = {
        ...admin,
        effectivePermissions: admin.effectivePermissions!.filter((p) => p !== permission),
      };
      render(
        <MemoryRouter initialEntries={['/portfolios/123']}>
          <Routes>
            <Route
              path="/portfolios/:id"
              element={<PortfolioDetail user={user} />}
            />
          </Routes>
        </MemoryRouter>,
      );
      await screen.findByRole('heading', { name: 'Payments' });
      expect(screen.getByText(visible)).toBeVisible();
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    },
  );
  it('denies a leader direct edit outside their assigned portfolio', () => {
    const leader = { ...admin, role: 'Portfolio Leader', portfolioAccess: ['other'] };
    render(
      <MemoryRouter initialEntries={['/portfolios/123/edit']}>
        <Routes>
          <Route
            path="/portfolios/:id/edit"
            element={
              <PortfolioForm
                user={leader}
                edit
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You cannot change this portfolio.');
  });
  it('shows list errors instead of results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ detail: 'Permission denied' }, 403)),
    );
    render(
      <MemoryRouter>
        <PortfolioList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
  });
  it('renders detail and linked application', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(
            response(
              url.includes('/applications')
                ? { items: [{ id: 'app1', name: 'Ledger' }], total: 1, limit: 25, offset: 0 }
                : item,
            ),
          ),
        ),
    );
    render(
      <MemoryRouter initialEntries={['/portfolios/123']}>
        <Routes>
          <Route
            path="/portfolios/:id"
            element={<PortfolioDetail user={admin} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Payments' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ledger' })).toHaveAttribute(
      'href',
      '/applications/app1',
    );
  });
  it('cancels portfolio deletion without sending a DELETE', async () => {
    const fetcher = vi.fn().mockImplementation((url: string, _options: RequestInit) =>
      Promise.resolve(response(url.includes('/applications') ? { items: [], total: 0, limit: 25, offset: 0 } : item)),
    );
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/portfolios/123']}>
        <Routes>
          <Route path="/portfolios/:id" element={<PortfolioDetail user={admin} />} />
          <Route path="/portfolios" element={<p>Portfolio list destination</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Payments' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Delete portfolio' }));
    expect(screen.getByText(/Delete this portfolio\?/)).toBeVisible();
    expect(fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE')).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('button', { name: 'Confirm delete' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Payments' })).toBeVisible();
    expect(screen.queryByText('Portfolio list destination')).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE')).toHaveLength(0);
  });
  it('keeps portfolio details on delete failure and navigates after a successful retry', async () => {
    let attempts = 0;
    const fetcher = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (options.method === 'DELETE') {
        attempts += 1;
        return Promise.resolve(attempts === 1
          ? response({ detail: 'Portfolio contains applications' }, 409)
          : new Response(null, { status: 204 }));
      }
      return Promise.resolve(response(url.includes('/applications') ? { items: [], total: 0, limit: 25, offset: 0 } : item));
    });
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/portfolios/123']}>
        <Routes>
          <Route path="/portfolios/:id" element={<PortfolioDetail user={admin} />} />
          <Route path="/portfolios" element={<p>Portfolio list destination</p>} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Payments' });
    await user.click(screen.getByRole('button', { name: 'Delete portfolio' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio contains applications');
    expect(screen.getByRole('heading', { name: 'Payments' })).toBeVisible();
    expect(screen.getByText('Payments systems')).toBeVisible();
    expect(screen.queryByText('Portfolio list destination')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm delete' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    expect(await screen.findByText('Portfolio list destination')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Payments' })).not.toBeInTheDocument();
    const deletes = fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE');
    expect(deletes).toHaveLength(2);
    expect(deletes[0][0]).toMatch(/\/api\/portfolios\/123$/);
    expect(deletes[1][0]).toMatch(/\/api\/portfolios\/123$/);
  });
  it('shows save conflict and preserves entered values', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ detail: 'Portfolio name already exists' }, 409)),
    );
    render(
      <MemoryRouter>
        <PortfolioForm user={admin} />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText('Name'), 'Payments');
    await userEvent.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Portfolio name already exists');
    expect(screen.getByLabelText('Name')).toHaveValue('Payments');
  });
  it('creates a portfolio and navigates to its detail route', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(item, 201)));
    render(
      <MemoryRouter initialEntries={['/portfolios/new']}>
        <Routes>
          <Route
            path="/portfolios/new"
            element={<PortfolioForm user={admin} />}
          />
          <Route
            path="/portfolios/:id"
            element={<p>Saved detail</p>}
          />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText('Name'), 'Payments');
    await userEvent.click(screen.getByRole('button', { name: 'Save portfolio' }));
    expect(await screen.findByText('Saved detail')).toBeVisible();
  });
});
