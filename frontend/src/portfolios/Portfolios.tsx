import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { clearToken, getToken } from '../api';
import type { ApplicationSummary, Page, Portfolio, PortfolioInput, User } from '../types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';

async function request<T>(path: string, method = 'GET', body?: PortfolioInput): Promise<T> {
  const token = getToken();
  const response = await fetch(`${base}/api/portfolios${path}`, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401) clearToken();
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.');
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

const message = (error: unknown) => error instanceof Error ? error.message : 'Request failed. Please try again.';
const blank: PortfolioInput = { name: '', owner: '', description: '', productArea: '', status: 'Active' };

export function PortfolioList({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState<Page<Portfolio> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const search = params.toString();
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    request<Page<Portfolio>>(`?${search}`).then(data => { if (active) setPage(data); }).catch(err => { if (active) setError(message(err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [search]);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete('offset');
    setParams(next);
  }
  function changeOffset(offset: number) {
    const next = new URLSearchParams(params);
    next.set('offset', String(offset));
    setParams(next);
  }
  return (
    <main className="page">
      <div className="portfolio-heading">
        <div><p className="eyebrow">INVENTORY</p><h1>Portfolios</h1><p>Explore ownership and application quality across portfolios.</p></div>
        {user.role === 'Administrator' && <Link className="action-link" to="/portfolios/new">Create portfolio</Link>}
      </div>
      <div className="filters" aria-label="Portfolio filters">
        <div><label htmlFor="search">Search</label><input id="search" value={params.get('search') ?? ''} onChange={event => filter('search', event.target.value)} /></div>
        <div><label htmlFor="status-filter">Status</label><select id="status-filter" value={params.get('status') ?? ''} onChange={event => filter('status', event.target.value)}><option value="">All statuses</option><option>Active</option><option>Archived</option></select></div>
        <div><label htmlFor="area-filter">Product area</label><input id="area-filter" value={params.get('productArea') ?? ''} onChange={event => filter('productArea', event.target.value)} /></div>
      </div>
      {loading && <p role="status">Loading portfolios…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && page && (page.items.length ? <>
        <div className="table-wrap"><table><thead><tr><th scope="col">Name</th><th scope="col">Owner</th><th scope="col">Product Area</th><th scope="col">Applications</th><th scope="col">Quality Score</th><th scope="col">Status</th></tr></thead><tbody>
          {page.items.map(item => <tr key={item.id}><td><Link to={`/portfolios/${item.id}`}>{item.name}</Link></td><td>{item.owner || '—'}</td><td>{item.productArea || '—'}</td><td>{item.applicationCount}</td><td>{item.qualityScore ?? '—'}</td><td>{item.status}</td></tr>)}
        </tbody></table></div>
        <div className="pagination"><span>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span><button type="button" disabled={page.offset === 0} onClick={() => changeOffset(Math.max(0, page.offset - page.limit))}>Previous</button><button type="button" disabled={page.offset + page.limit >= page.total} onClick={() => changeOffset(page.offset + page.limit)}>Next</button></div>
      </> : <p>No portfolios found.</p>)}
    </main>
  );
}

export function PortfolioDetail({ user }: { user: User }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [apps, setApps] = useState<Page<ApplicationSummary> | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    Promise.all([request<Portfolio>(`/${id}`), request<Page<ApplicationSummary>>(`/${id}/applications?offset=${offset}`)])
      .then(([detail, applications]) => { if (active) { setPortfolio(detail); setApps(applications); } })
      .catch(err => { if (active) setError(message(err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, offset]);
  async function remove() {
    setBusy(true); setError('');
    try { await request<void>(`/${id}`, 'DELETE'); navigate('/portfolios'); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  const canEdit = user.role === 'Administrator' || (user.role === 'Portfolio Leader' && user.portfolioAccess.includes(id));
  return (
    <main className="page">
      <Link to="/portfolios">← All portfolios</Link>
      {loading && <p role="status">Loading portfolio…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {!loading && portfolio && <>
        <div className="portfolio-heading"><div><p className="eyebrow">PORTFOLIO</p><h1>{portfolio.name}</h1><p>{portfolio.description || 'No description provided.'}</p></div>
          <div className="actions">{canEdit && <Link className="action-link" to={`/portfolios/${id}/edit`}>Edit portfolio</Link>}{user.role === 'Administrator' && <button type="button" onClick={() => setConfirming(true)}>Delete portfolio</button>}</div>
        </div>
        {confirming && <div className="notice"><p>Delete this portfolio? Portfolios containing applications cannot be deleted.</p><div className="actions"><button type="button" disabled={busy} onClick={remove}>{busy ? 'Deleting…' : 'Confirm delete'}</button><button type="button" onClick={() => setConfirming(false)}>Cancel</button></div></div>}
        <dl><dt>Owner</dt><dd>{portfolio.owner || '—'}</dd><dt>Product area</dt><dd>{portfolio.productArea || '—'}</dd><dt>Status</dt><dd>{portfolio.status}</dd><dt>Applications</dt><dd>{portfolio.applicationCount}</dd><dt>Quality score</dt><dd>{portfolio.qualityScore ?? '—'}</dd></dl>
        <section><h2>Applications</h2>{apps && (apps.items.length ? <><ul className="linked-apps">{apps.items.map(app => <li key={app.id}><Link to={`/applications/${app.id}`}>{app.name}</Link></li>)}</ul><div className="pagination"><span>{apps.offset + 1}–{apps.offset + apps.items.length} of {apps.total}</span><button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - apps.limit))}>Previous</button><button type="button" disabled={offset + apps.limit >= apps.total} onClick={() => setOffset(offset + apps.limit)}>Next</button></div></> : <p>No applications in this portfolio.</p>)}</section>
      </>}
    </main>
  );
}

export function PortfolioForm({ user, edit = false }: { user: User; edit?: boolean }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [fields, setFields] = useState<PortfolioInput>(blank);
  const [loading, setLoading] = useState(edit);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const allowed = edit ? user.role === 'Administrator' || (user.role === 'Portfolio Leader' && user.portfolioAccess.includes(id)) : user.role === 'Administrator';
  useEffect(() => {
    if (!edit || !allowed) { setLoading(false); return; }
    let active = true;
    request<Portfolio>(`/${id}`).then(data => { if (active) setFields({ name: data.name, owner: data.owner, description: data.description, productArea: data.productArea, status: data.status }); }).catch(err => { if (active) setError(message(err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, edit, allowed]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { const saved = await request<Portfolio>(edit ? `/${id}` : '', edit ? 'PUT' : 'POST', fields); navigate(`/portfolios/${saved.id}`); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  return (
    <main className="page">
      <Link to={edit ? `/portfolios/${id}` : '/portfolios'}>← Cancel</Link>
      <h1>{edit ? 'Edit portfolio' : 'Create portfolio'}</h1>
      {!allowed && <p role="alert" className="error">You cannot change this portfolio.</p>}
      {loading && <p role="status">Loading portfolio…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {allowed && !loading && (!edit || fields.name) && <form className="portfolio-form" onSubmit={submit}>
        <label htmlFor="name">Name</label><input id="name" required aria-required="true" maxLength={200} value={fields.name} onChange={event => setFields({ ...fields, name: event.target.value })} />
        <label htmlFor="owner">Owner</label><input id="owner" maxLength={200} value={fields.owner} onChange={event => setFields({ ...fields, owner: event.target.value })} />
        <label htmlFor="product-area">Product area</label><input id="product-area" maxLength={200} value={fields.productArea} onChange={event => setFields({ ...fields, productArea: event.target.value })} />
        <label htmlFor="description">Description</label><textarea id="description" maxLength={4000} rows={4} value={fields.description} onChange={event => setFields({ ...fields, description: event.target.value })} />
        <label htmlFor="portfolio-status">Status</label><select id="portfolio-status" value={fields.status} onChange={event => setFields({ ...fields, status: event.target.value as PortfolioInput['status'] })}><option>Active</option><option>Archived</option></select>
        <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save portfolio'}</button>
      </form>}
    </main>
  );
}
