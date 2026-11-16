import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApplicationDetail, ApplicationForm, ApplicationList } from './Applications';
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
const portfolio = {
  id: 'p1',
  name: 'Payments',
  owner: 'Alex',
  description: '',
  productArea: 'Payments',
  status: 'Active',
  applicationCount: 1,
  qualityScore: 80,
  createdAt: 'now',
  updatedAt: 'now',
};
const app = {
  id: 'a1',
  name: 'Ledger',
  description: 'Ledger application',
  portfolioId: 'p1',
  productArea: 'Payments',
  businessOwner: 'Business',
  technologyOwner: 'Tech',
  etsOwner: 'ETS',
  criticality: 'High',
  tier: 2,
  lifecycleStatus: 'Active',
  technologyStack: 'Python',
  repositoryLink: 'https://example.com/',
  pipelineLink: null,
  applicationHealthScore: 80,
  qualityScore: 90,
  automationCoverage: 60,
  unitTestCoverage: 70,
  openDefects: 4,
  openCriticalDefects: 1,
  riskLevel: 'Medium',
  createdAt: 'now',
  updatedAt: 'now',
};
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe('application screens', () => {
  it('renders data and sends URL filter changes', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(response(url.includes('/portfolios') ? page([portfolio]) : page([app]))),
      );
    vi.stubGlobal('fetch', fetcher);
    render(
      <MemoryRouter>
        <ApplicationList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('link', { name: 'Ledger' })).toHaveAttribute(
      'href',
      '/applications/a1',
    );
    expect(screen.getByRole('cell', { name: 'Payments' })).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Risk level'), 'High');
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('riskLevel=High'),
      expect.anything(),
    );
    expect(screen.getByRole('link', { name: 'Create application' })).toBeVisible();
  });
  it('hides create and denies the direct form when create is revoked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(response(page([])))),
    );
    const user = { ...admin, effectivePermissions: ['view', 'edit', 'delete'] };
    const list = render(
      <MemoryRouter>
        <ApplicationList user={user} />
      </MemoryRouter>,
    );
    await screen.findByText('No applications found.');
    expect(screen.queryByRole('link', { name: 'Create application' })).not.toBeInTheDocument();
    list.unmount();
    render(
      <MemoryRouter>
        <ApplicationForm user={user} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You cannot change applications.');
    expect(screen.queryByRole('button', { name: 'Save application' })).not.toBeInTheDocument();
  });
  it('hides revoked edit and delete controls and denies direct edit', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app)),
        ),
    );
    const user = { ...admin, effectivePermissions: ['view', 'create'] };
    const detail = render(
      <MemoryRouter initialEntries={['/applications/a1']}>
        <Routes>
          <Route
            path="/applications/:id"
            element={<ApplicationDetail user={user} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Ledger' });
    expect(screen.queryByRole('link', { name: 'Edit application' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete application' })).not.toBeInTheDocument();
    detail.unmount();
    render(
      <MemoryRouter initialEntries={['/applications/a1/edit']}>
        <Routes>
          <Route
            path="/applications/:id/edit"
            element={
              <ApplicationForm
                user={user}
                edit
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You cannot change applications.');
  });
  it.each([
    { permission: 'edit', visible: 'Delete application', hidden: 'Edit application' },
    { permission: 'delete', visible: 'Edit application', hidden: 'Delete application' },
  ])(
    'independently honors revoked $permission permission',
    async ({ permission, visible, hidden }) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockImplementation((url: string) =>
            Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app)),
          ),
      );
      const user = {
        ...admin,
        effectivePermissions: admin.effectivePermissions!.filter((p) => p !== permission),
      };
      render(
        <MemoryRouter initialEntries={['/applications/a1']}>
          <Routes>
            <Route
              path="/applications/:id"
              element={<ApplicationDetail user={user} />}
            />
          </Routes>
        </MemoryRouter>,
      );
      await screen.findByRole('heading', { name: 'Ledger' });
      expect(screen.getByText(visible)).toBeVisible();
      expect(screen.queryByText(hidden)).not.toBeInTheDocument();
    },
  );
  it('limits leader form portfolio choices and rejects an out-of-scope edit', async () => {
    const other = { ...portfolio, id: 'p2', name: 'Other' };
    const leader = { ...admin, role: 'Portfolio Leader', portfolioAccess: ['p2'] };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(
            response(url.includes('/applications/a1') ? app : page([portfolio, other])),
          ),
        ),
    );
    const create = render(
      <MemoryRouter>
        <ApplicationForm user={leader} />
      </MemoryRouter>,
    );
    await screen.findByRole('option', { name: 'Other' });
    expect(screen.queryByRole('option', { name: 'Payments' })).not.toBeInTheDocument();
    create.unmount();
    render(
      <MemoryRouter initialEntries={['/applications/a1/edit']}>
        <Routes>
          <Route
            path="/applications/:id/edit"
            element={
              <ApplicationForm
                user={leader}
                edit
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('outside your assigned portfolios');
    expect(screen.queryByRole('button', { name: 'Save application' })).not.toBeInTheDocument();
  });
  it('displays API failures and empty results', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation(() => Promise.resolve(response({ detail: 'Permission denied' }, 403))),
    );
    const view = render(
      <MemoryRouter>
        <ApplicationList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    view.unmount();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => Promise.resolve(response(page([])))),
    );
    render(
      <MemoryRouter>
        <ApplicationList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByText('No applications found.')).toBeVisible();
  });
  it('shows full details and hides edit and delete for read only', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app)),
        ),
    );
    const reader = { ...admin, role: 'Read Only' };
    render(
      <MemoryRouter initialEntries={['/applications/a1']}>
        <Routes>
          <Route
            path="/applications/:id"
            element={<ApplicationDetail user={reader} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Ledger' })).toBeVisible();
    expect(screen.getByText('Business')).toBeVisible();
    expect(screen.getByRole('link', { name: 'https://example.com/' })).toHaveAttribute(
      'href',
      'https://example.com/',
    );
    expect(screen.queryByRole('link', { name: 'Edit application' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete application' })).not.toBeInTheDocument();
  });
  it('cancels application deletion without sending a DELETE', async () => {
    const fetcher = vi.fn().mockImplementation((url: string, _options: RequestInit) =>
      Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app)),
    );
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/applications/a1']}>
        <Routes>
          <Route path="/applications/:id" element={<ApplicationDetail user={admin} />} />
          <Route path="/applications" element={<p>Application list destination</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Ledger' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Delete application' }));
    expect(screen.getByText('Delete this application?')).toBeVisible();
    expect(fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE')).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('button', { name: 'Confirm delete' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ledger' })).toBeVisible();
    expect(screen.queryByText('Application list destination')).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE')).toHaveLength(0);
  });
  it('keeps application details on delete failure and navigates after a successful retry', async () => {
    let attempts = 0;
    const fetcher = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (options.method === 'DELETE') {
        attempts += 1;
        return Promise.resolve(attempts === 1
          ? response({ detail: 'Application cannot be deleted' }, 409)
          : new Response(null, { status: 204 }));
      }
      return Promise.resolve(response(url.includes('/portfolios/') ? portfolio : app));
    });
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/applications/a1']}>
        <Routes>
          <Route path="/applications/:id" element={<ApplicationDetail user={admin} />} />
          <Route path="/applications" element={<p>Application list destination</p>} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Ledger' });
    await user.click(screen.getByRole('button', { name: 'Delete application' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Application cannot be deleted');
    expect(screen.getByRole('heading', { name: 'Ledger' })).toBeVisible();
    expect(screen.getByText('Ledger application')).toBeVisible();
    expect(screen.queryByText('Application list destination')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm delete' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Confirm delete' }));
    expect(await screen.findByText('Application list destination')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Ledger' })).not.toBeInTheDocument();
    const deletes = fetcher.mock.calls.filter(([, options]) => options.method === 'DELETE');
    expect(deletes).toHaveLength(2);
    expect(deletes[0][0]).toMatch(/\/api\/applications\/a1$/);
    expect(deletes[1][0]).toMatch(/\/api\/applications\/a1$/);
  });
  it('renders stored script and event-handler payloads as text in list and detail', async () => {
    const name = '<script>window.xss=1</script>';
    const description = '<img src=x onerror="window.xss=1">';
    const unsafe = { ...app, name, description };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(
            response(
              url.includes('/portfolios/')
                ? portfolio
                : url.includes('/portfolios')
                  ? page([portfolio])
                  : url.includes('/applications/a1')
                    ? unsafe
                    : page([unsafe]),
            ),
          ),
        ),
    );
    const list = render(
      <MemoryRouter>
        <ApplicationList user={admin} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('link', { name })).toHaveTextContent(name);
    expect(list.container.querySelector('script, img, [onerror], [onclick]')).toBeNull();
    list.unmount();
    const detail = render(
      <MemoryRouter initialEntries={['/applications/a1']}>
        <Routes>
          <Route
            path="/applications/:id"
            element={<ApplicationDetail user={admin} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name })).toHaveTextContent(name);
    expect(screen.getByText(description)).toBeVisible();
    expect(detail.container.querySelector('script, img, [onerror], [onclick]')).toBeNull();
    expect((window as unknown as { xss?: number }).xss).toBeUndefined();
  });
  it('creates a record and navigates to detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string, options: RequestInit) =>
          Promise.resolve(
            response(
              options.method === 'POST' ? app : page([portfolio]),
              options.method === 'POST' ? 201 : 200,
            ),
          ),
        ),
    );
    render(
      <MemoryRouter initialEntries={['/applications/new']}>
        <Routes>
          <Route
            path="/applications/new"
            element={<ApplicationForm user={admin} />}
          />
          <Route
            path="/applications/:id"
            element={<p>Saved detail</p>}
          />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByLabelText('Name');
    await userEvent.type(screen.getByLabelText('Name'), 'Ledger');
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p1');
    await userEvent.click(screen.getByRole('button', { name: 'Save application' }));
    expect(await screen.findByText('Saved detail')).toBeVisible();
  });
  it('retains the form and reports a duplicate error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string, options: RequestInit) =>
          Promise.resolve(
            options.method === 'POST'
              ? response({ detail: 'Application name already exists' }, 409)
              : response(page([portfolio])),
          ),
        ),
    );
    render(
      <MemoryRouter>
        <ApplicationForm user={admin} />
      </MemoryRouter>,
    );
    await screen.findByLabelText('Name');
    await userEvent.type(screen.getByLabelText('Name'), 'Ledger');
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'p1');
    await userEvent.click(screen.getByRole('button', { name: 'Save application' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Application name already exists');
    expect(screen.getByLabelText('Name')).toHaveValue('Ledger');
  });
});
