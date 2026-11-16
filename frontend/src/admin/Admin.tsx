import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { clearToken, getToken } from '../api';
import type { AdminRole, AdminUser, AuditEvent, Page, Portfolio, User } from '../types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';
const roles = [
  'Administrator',
  'Executive',
  'Portfolio Leader',
  'Engineer',
  'Auditor',
  'Read Only',
];
const permissions = ['view', 'create', 'edit', 'delete', 'export', 'administer'];
const message = (error: unknown) => (error instanceof Error ? error.message : 'Request failed.');

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = getToken();
  const response = await fetch(`${base}/api${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 401) clearToken();
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : 'Request failed. Please check the form and try again.',
    );
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
}

type Fields = Pick<
  AdminUser,
  | 'name'
  | 'email'
  | 'role'
  | 'portfolioAccess'
  | 'status'
  | 'managerName'
  | 'vendorIndicator'
  | 'defaultLandingPage'
>;
const blank: Fields = {
  name: '',
  email: '',
  role: 'Engineer',
  portfolioAccess: [],
  status: 'Active',
  managerName: null,
  vendorIndicator: false,
  defaultLandingPage: null,
};

export default function Admin({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const admin =
    user.role === 'Administrator' && (user.effectivePermissions?.includes('administer') ?? false);
  const audit =
    ['Administrator', 'Auditor'].includes(user.role) &&
    (user.effectivePermissions?.includes('view') ?? false);
  const canExport =
    ['Administrator', 'Auditor'].includes(user.role) &&
    (user.effectivePermissions?.includes('export') ?? false);
  const tab = params.get('tab') ?? (admin ? 'users' : 'audit');
  const [users, setUsers] = useState<Page<AdminUser> | null>(null);
  const [rolePage, setRolePage] = useState<Page<AdminRole> | null>(null);
  const [events, setEvents] = useState<Page<AuditEvent> | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [portfolioStatus, setPortfolioStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [portfolioError, setPortfolioError] = useState('');
  const [portfolioRevision, setPortfolioRevision] = useState(0);
  const [fields, setFields] = useState<Fields>(blank);
  const [password, setPassword] = useState('');
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState<AdminRole | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const query = params.toString();
  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  }
  const auditParams = new URLSearchParams();
  ['userId', 'action', 'from', 'to', 'offset'].forEach((key) => {
    const value = params.get(key);
    if (value) auditParams.set(key, value);
  });
  const auditQuery = auditParams.toString();
  useEffect(() => {
    let active = true;
    if ((!admin && tab !== 'audit') || (tab === 'audit' && !audit)) return;
    setLoading(true);
    setError('');
    const offset = params.get('offset') ?? '0';
    const promise =
      tab === 'users'
        ? request<Page<AdminUser>>(`/users?offset=${offset}`).then((data) => {
            if (active) setUsers(data);
          })
        : tab === 'roles'
          ? request<Page<AdminRole>>(`/roles?offset=${offset}`).then((data) => {
              if (active) setRolePage(data);
            })
          : request<Page<AuditEvent>>(`/audit-logs?${auditQuery}`).then((data) => {
              if (active) setEvents(data);
            });
    promise
      .catch((err) => {
        if (active) setError(message(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, revision, admin, audit, tab, auditQuery]);
  useEffect(() => {
    if (!admin) return;
    let active = true;
    setPortfolioStatus('loading');
    setPortfolioError('');
    async function loadPortfolios() {
      const items: Portfolio[] = [];
      let offset = 0;
      for (;;) {
        const page = await request<Page<Portfolio>>(`/portfolios?limit=100&offset=${offset}`);
        items.push(...page.items);
        offset += page.items.length;
        if (offset >= page.total) break;
        if (!page.items.length) throw new Error('The portfolio list is incomplete. Please retry.');
      }
      if (active) {
        setPortfolios(items);
        setPortfolioStatus('ready');
      }
    }
    loadPortfolios().catch((err) => {
      if (active) {
        setPortfolioError(message(err));
        setPortfolioStatus('error');
      }
    });
    return () => {
      active = false;
    };
  }, [admin, portfolioRevision]);
  async function selectUser(id: string) {
    setError('');
    setLoading(true);
    try {
      const item = await request<AdminUser>(`/users/${id}`);
      setSelected(item);
      setFields({
        name: item.name,
        email: item.email,
        role: item.role,
        portfolioAccess: item.portfolioAccess,
        status: item.status,
        managerName: item.managerName,
        vendorIndicator: item.vendorIndicator,
        defaultLandingPage: item.defaultLandingPage,
      });
      setEditing(false);
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }
  async function saveUser(event: FormEvent) {
    event.preventDefault();
    if (portfolioStatus !== 'ready') return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const item = await request<AdminUser>(
        selected ? `/users/${selected.id}` : '/users',
        selected ? 'PUT' : 'POST',
        selected ? fields : { ...fields, password },
      );
      setSelected(item);
      setPassword('');
      setEditing(false);
      setRevision((value) => value + 1);
      setNotice('User saved.');
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function deactivate() {
    if (!selected || !window.confirm(`Deactivate ${selected.name}?`)) return;
    setBusy(true);
    setError('');
    try {
      await request(`/users/${selected.id}`, 'DELETE');
      await selectUser(selected.id);
      setRevision((value) => value + 1);
      setNotice('User deactivated.');
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function saveRole(event: FormEvent) {
    event.preventDefault();
    if (!role) return;
    setBusy(true);
    setError('');
    try {
      const saved = await request<AdminRole>(`/roles/${role.id}`, 'PUT', {
        name: role.name,
        description: role.description,
        permissions: role.permissions,
      });
      setRole(saved);
      setRevision((value) => value + 1);
      setNotice('Role saved.');
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    setBusy(true);
    setError('');
    try {
      const token = getToken();
      const exportParams = new URLSearchParams(auditQuery);
      exportParams.delete('offset');
      const response = await fetch(`${base}/api/audit-logs/export?${exportParams}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Export failed.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'audit-logs.csv';
      link.click();
      URL.revokeObjectURL(url);
      setNotice('Audit log exported.');
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  const page = tab === 'users' ? users : tab === 'roles' ? rolePage : events;
  return (
    <main className="page">
      <h1>Administration</h1>
      <p>Manage access and review sensitive activity.</p>
      <nav
        className="actions"
        aria-label="Administration sections"
      >
        {admin && (
          <Link
            aria-current={tab === 'users' ? 'page' : undefined}
            to="?tab=users"
          >
            Users
          </Link>
        )}
        {admin && (
          <Link
            aria-current={tab === 'roles' ? 'page' : undefined}
            to="?tab=roles"
          >
            Roles
          </Link>
        )}
        {audit && (
          <Link
            aria-current={tab === 'audit' ? 'page' : undefined}
            to="?tab=audit"
          >
            Audit log
          </Link>
        )}
      </nav>
      {!admin && !audit && (
        <p
          role="alert"
          className="error"
        >
          You do not have administration access.
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="error"
        >
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {loading && <p role="status">Loading…</p>}
      {admin && tab === 'users' && (
        <section>
          <div className="portfolio-heading">
            <h2>Users</h2>
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setFields(blank);
                setEditing(true);
                setNotice('');
              }}
            >
              Create user
            </button>
          </div>
          {portfolioStatus === 'loading' && <p role="status">Loading portfolios…</p>}
          {portfolioStatus === 'error' && (
            <div>
              <p role="alert" className="error">Unable to load portfolios: {portfolioError}</p>
              <button
                type="button"
                onClick={() => {
                  setPortfolioStatus('loading');
                  setPortfolioRevision((value) => value + 1);
                }}
              >
                Retry portfolios
              </button>
            </div>
          )}
          {users && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Email</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <button
                          type="button"
                          onClick={() => selectUser(item.id)}
                        >
                          {item.name}
                        </button>
                      </td>
                      <td>{item.email}</td>
                      <td>{item.role}</td>
                      <td>{item.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!users.items.length && <p>No users found.</p>}
            </div>
          )}
          {selected && !editing && (
            <section>
              <h2>{selected.name}</h2>
              <dl>
                <dt>Email</dt>
                <dd>{selected.email}</dd>
                <dt>Role</dt>
                <dd>{selected.role}</dd>
                <dt>Status</dt>
                <dd>{selected.status}</dd>
                <dt>Portfolio access</dt>
                <dd>{selected.portfolioAccess.join(', ') || 'None assigned'}</dd>
                <dt>Manager</dt>
                <dd>{selected.managerName || '—'}</dd>
                <dt>Vendor</dt>
                <dd>{selected.vendorIndicator ? 'Yes' : 'No'}</dd>
                <dt>Authentication</dt>
                <dd>{selected.authSource}</dd>
                <dt>Last login</dt>
                <dd>{selected.lastLogin || 'Never'}</dd>
                <dt>Created</dt>
                <dd>{selected.createdAt}</dd>
                <dt>Updated</dt>
                <dd>{selected.updatedAt}</dd>
                <dt>Landing page</dt>
                <dd>{selected.defaultLandingPage || 'Default'}</dd>
              </dl>
              <div className="actions">
                <button onClick={() => setEditing(true)}>Edit user</button>
                {selected.status === 'Active' && (
                  <button
                    disabled={busy}
                    onClick={deactivate}
                  >
                    Deactivate user
                  </button>
                )}
              </div>
            </section>
          )}
          {editing && (
            <form
              className="portfolio-form"
              onSubmit={saveUser}
            >
              <h2>{selected ? 'Edit user' : 'Create user'}</h2>
              <label htmlFor="admin-name">Name</label>
              <input
                id="admin-name"
                required
                maxLength={200}
                value={fields.name}
                onChange={(e) => setFields({ ...fields, name: e.target.value })}
              />
              <label htmlFor="admin-email">Email</label>
              <input
                id="admin-email"
                type="email"
                required
                value={fields.email}
                onChange={(e) => setFields({ ...fields, email: e.target.value })}
              />
              {!selected && (
                <>
                  <label htmlFor="admin-password">Initial password</label>
                  <input
                    id="admin-password"
                    type="password"
                    required
                    minLength={12}
                    maxLength={72}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </>
              )}
              <label htmlFor="admin-role">Role</label>
              <select
                id="admin-role"
                value={fields.role}
                onChange={(e) => setFields({ ...fields, role: e.target.value })}
              >
                {roles.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
              <label htmlFor="admin-status">Status</label>
              <select
                id="admin-status"
                value={fields.status}
                onChange={(e) =>
                  setFields({ ...fields, status: e.target.value as Fields['status'] })
                }
              >
                <option>Active</option>
                <option>Inactive</option>
              </select>
              <label htmlFor="admin-manager">Manager name</label>
              <input
                id="admin-manager"
                value={fields.managerName ?? ''}
                onChange={(e) => setFields({ ...fields, managerName: e.target.value || null })}
              />
              <label>
                <input
                  type="checkbox"
                  checked={fields.vendorIndicator}
                  onChange={(e) => setFields({ ...fields, vendorIndicator: e.target.checked })}
                />{' '}
                Vendor
              </label>
              <label htmlFor="admin-landing">Default landing page</label>
              <select
                id="admin-landing"
                value={fields.defaultLandingPage ?? ''}
                onChange={(e) =>
                  setFields({
                    ...fields,
                    defaultLandingPage: (e.target.value || null) as Fields['defaultLandingPage'],
                  })
                }
              >
                <option value="">Default</option>
                <option value="dashboard">Dashboard</option>
                <option value="applications">Applications</option>
              </select>
              <fieldset>
                <legend>Portfolio access</legend>
                {portfolios.map((item) => (
                  <label
                    key={item.id}
                    className="admin-check"
                  >
                    <input
                      type="checkbox"
                      checked={fields.portfolioAccess.includes(item.id)}
                      onChange={(e) =>
                        setFields({
                          ...fields,
                          portfolioAccess: e.target.checked
                            ? [...fields.portfolioAccess, item.id]
                            : fields.portfolioAccess.filter((id) => id !== item.id),
                        })
                      }
                    />{' '}
                    {item.name}
                  </label>
                ))}
              </fieldset>
              <div className="actions">
                <button
                  type="submit"
                  disabled={busy || portfolioStatus !== 'ready'}
                >
                  {busy ? 'Saving…' : 'Save user'}
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </section>
      )}
      {admin && tab === 'roles' && (
        <section>
          <h2>Roles</h2>
          {rolePage && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Role</th>
                    <th scope="col">Permissions</th>
                  </tr>
                </thead>
                <tbody>
                  {rolePage.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <button
                          type="button"
                          onClick={() => setRole(item)}
                        >
                          {item.name}
                        </button>
                      </td>
                      <td>{item.permissions.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {role && (
            <form
              onSubmit={saveRole}
              className="portfolio-form"
            >
              <h2>Edit {role.name}</h2>
              <label htmlFor="role-description">Description</label>
              <input
                id="role-description"
                value={role.description}
                onChange={(e) => setRole({ ...role, description: e.target.value })}
              />
              <fieldset>
                <legend>Permissions</legend>
                {permissions.map((permission) => (
                  <label
                    className="admin-check"
                    key={permission}
                  >
                    <input
                      type="checkbox"
                      checked={role.permissions.includes(permission)}
                      onChange={(e) =>
                        setRole({
                          ...role,
                          permissions: e.target.checked
                            ? [...role.permissions, permission]
                            : role.permissions.filter((p) => p !== permission),
                        })
                      }
                    />{' '}
                    {permission}
                  </label>
                ))}
              </fieldset>
              <p>Fixed role restrictions still apply even when a permission is selected.</p>
              <button
                type="submit"
                disabled={busy}
              >
                Save role
              </button>
            </form>
          )}
        </section>
      )}
      {audit && tab === 'audit' && (
        <section>
          <div className="portfolio-heading">
            <h2>Audit log</h2>
            {canExport && (
              <button
                type="button"
                disabled={busy}
                onClick={download}
              >
                Export CSV
              </button>
            )}
          </div>
          <div className="filters">
            <div>
              <label htmlFor="audit-user">User ID</label>
              <input
                id="audit-user"
                value={params.get('userId') ?? ''}
                onChange={(e) => setParam('userId', e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="audit-action">Action</label>
              <select
                id="audit-action"
                value={params.get('action') ?? ''}
                onChange={(e) => setParam('action', e.target.value)}
              >
                <option value="">All actions</option>
                {[
                  'login',
                  'create',
                  'edit',
                  'delete',
                  'roleChange',
                  'permissionChange',
                  'export',
                ].map((action) => (
                  <option key={action}>{action}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="audit-from">From</label>
              <input
                id="audit-from"
                type="date"
                value={params.get('from') ?? ''}
                onChange={(e) => setParam('from', e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="audit-to">To</label>
              <input
                id="audit-to"
                type="date"
                value={params.get('to') ?? ''}
                onChange={(e) => setParam('to', e.target.value)}
              />
            </div>
          </div>
          {events &&
            (events.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">User</th>
                      <th scope="col">Action</th>
                      <th scope="col">Entity</th>
                      <th scope="col">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.items.map((item) => (
                      <tr key={item.id}>
                        <td>{item.timestamp}</td>
                        <td>{item.userName}</td>
                        <td>{item.action}</td>
                        <td>
                          {item.entityType} {item.entityId}
                        </td>
                        <td>{item.details}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>No audit events found.</p>
            ))}
        </section>
      )}
      {page && page.total > page.limit && (
        <div className="pagination">
          <span>
            {page.offset + 1}–{page.offset + page.items.length} of {page.total}
          </span>
          <button
            disabled={page.offset === 0}
            onClick={() => setParam('offset', String(Math.max(0, page.offset - page.limit)))}
          >
            Previous
          </button>
          <button
            disabled={page.offset + page.limit >= page.total}
            onClick={() => setParam('offset', String(page.offset + page.limit))}
          >
            Next
          </button>
        </div>
      )}
    </main>
  );
}
