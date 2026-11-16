import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { clearToken, getToken } from '../api';
import type { Application, ApplicationInput, Page, Portfolio, User } from '../types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';

async function request<T>(path: string, method = 'GET', body?: ApplicationInput): Promise<T> {
  const token = getToken();
  const response = await fetch(`${base}/api${path}`, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401) clearToken();
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please check the fields and try again.');
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

const message = (error: unknown) => error instanceof Error ? error.message : 'Request failed. Please try again.';
const canWrite = (user: User) => ['Administrator', 'Portfolio Leader', 'Engineer'].includes(user.role);
const blank: ApplicationInput = {
  name: '', description: '', portfolioId: '', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '',
  criticality: 'Medium', tier: 1, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null,
  applicationHealthScore: 0, qualityScore: 0, automationCoverage: 0, unitTestCoverage: 0, openDefects: 0, openCriticalDefects: 0, riskLevel: 'Low',
};

const textFields = [
  ['name', 'Name'], ['description', 'Description'], ['productArea', 'Product area'], ['businessOwner', 'Business owner'],
  ['technologyOwner', 'Technology owner'], ['etsOwner', 'ETS owner'], ['technologyStack', 'Technology stack'],
  ['repositoryLink', 'Repository link'], ['pipelineLink', 'Pipeline link'],
] as const;
const numberFields = [
  ['tier', 'Tier', 1, 4], ['applicationHealthScore', 'Application health score', 0, 100],
  ['qualityScore', 'Quality score', 0, 100], ['automationCoverage', 'Automation coverage %', 0, 100],
  ['unitTestCoverage', 'Unit-test coverage %', 0, 100], ['openDefects', 'Open defects', 0, undefined],
  ['openCriticalDefects', 'Open critical defects', 0, undefined],
] as const;
const selects = [
  ['criticality', 'Criticality', ['Low', 'Medium', 'High', 'Critical']],
  ['lifecycleStatus', 'Lifecycle status', ['Active', 'Deprecated', 'Retired']],
  ['riskLevel', 'Risk level', ['Low', 'Medium', 'High']],
] as const;

export function ApplicationList({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState<Page<Application> | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const search = params.toString();
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([request<Page<Application>>(`/applications?${search}`), request<Page<Portfolio>>('/portfolios?limit=100')])
      .then(([result, portfolioPage]) => { if (active) { setPage(result); setPortfolios(portfolioPage.items); } })
      .catch(err => { if (active) setError(message(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [search]);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  }
  return (
    <main className="page">
      <div className="portfolio-heading">
        <div>
          <p className="eyebrow">INVENTORY</p>
          <h1>Applications</h1>
          <p>Explore application quality and risk across portfolios.</p>
        </div>
        {canWrite(user) && <Link className="action-link" to="/applications/new">Create application</Link>}
      </div>
      <div className="filters" aria-label="Application filters">
        <div>
          <label htmlFor="app-search">Search</label>
          <input id="app-search" value={params.get('search') ?? ''} onChange={event => filter('search', event.target.value)} />
        </div>
        <div>
          <label htmlFor="portfolio-filter">Portfolio</label>
          <select id="portfolio-filter" value={params.get('portfolioId') ?? ''} onChange={event => filter('portfolioId', event.target.value)}>
            <option value="">All portfolios</option>
            {portfolios.map(portfolio => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
          </select>
        </div>
        {selects.map(([key, label, options]) => (
          <div key={key}>
            <label htmlFor={`filter-${key}`}>{label}</label>
            <select id={`filter-${key}`} value={params.get(key) ?? ''} onChange={event => filter(key, event.target.value)}>
              <option value="">All</option>
              {options.map(option => <option key={option}>{option}</option>)}
            </select>
          </div>
        ))}
      </div>
      {loading && <p role="status">Loading applications…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && page && (page.items.length ? (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {['Name', 'Portfolio', 'Criticality', 'Tier', 'Lifecycle status', 'Health score', 'Automation coverage %', 'Open critical defects', 'Risk level'].map(label => <th key={label} scope="col">{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {page.items.map(item => (
                  <tr key={item.id}>
                    <td><Link to={`/applications/${item.id}`}>{item.name}</Link></td>
                    <td>{portfolios.find(portfolio => portfolio.id === item.portfolioId)?.name ?? item.portfolioId}</td>
                    <td>{item.criticality}</td>
                    <td>{item.tier}</td>
                    <td>{item.lifecycleStatus}</td>
                    <td>{item.applicationHealthScore}</td>
                    <td>{item.automationCoverage}%</td>
                    <td>{item.openCriticalDefects}</td>
                    <td>{item.riskLevel}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
            <button type="button" disabled={page.offset === 0} onClick={() => filter('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button>
            <button type="button" disabled={page.offset + page.limit >= page.total} onClick={() => filter('offset', String(page.offset + page.limit))}>Next</button>
          </div>
        </>
      ) : <p>No applications found.</p>)}
    </main>
  );
}

export function ApplicationDetail({ user }: { user: User }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState<Application | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    request<Application>(`/applications/${id}`)
      .then(async data => { const related = await request<Portfolio>(`/portfolios/${data.portfolioId}`); if (active) { setItem(data); setPortfolio(related); } })
      .catch(err => { if (active) setError(message(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);
  async function remove() {
    setBusy(true);
    setError('');
    try { await request<void>(`/applications/${id}`, 'DELETE'); navigate('/applications'); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  const allowed = item && canWrite(user) && (user.role !== 'Portfolio Leader' || user.portfolioAccess.includes(item.portfolioId));
  return (
    <main className="page">
      <Link to="/applications">← All applications</Link>
      {loading && <p role="status">Loading application…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {!loading && item && (
        <>
          <div className="portfolio-heading">
            <div>
              <p className="eyebrow">APPLICATION</p>
              <h1>{item.name}</h1>
              <p>{item.description || 'No description provided.'}</p>
            </div>
            <div className="actions">
              {allowed && <Link className="action-link" to={`/applications/${id}/edit`}>Edit application</Link>}
              {user.role === 'Administrator' && <button type="button" onClick={() => setConfirming(true)}>Delete application</button>}
            </div>
          </div>
          {confirming && (
            <div className="notice">
              <p>Delete this application?</p>
              <div className="actions">
                <button type="button" disabled={busy} onClick={remove}>{busy ? 'Deleting…' : 'Confirm delete'}</button>
                <button type="button" onClick={() => setConfirming(false)}>Cancel</button>
              </div>
            </div>
          )}
          <dl>
            <dt>Portfolio</dt>
            <dd><Link to={`/portfolios/${item.portfolioId}`}>{portfolio?.name ?? item.portfolioId}</Link></dd>
            {textFields.filter(([key]) => key !== 'name' && key !== 'description').map(([key, label]) => (
              <div key={key} className="application-detail-row">
                <dt>{label}</dt>
                <dd>{(key === 'repositoryLink' || key === 'pipelineLink') && item[key] ? <a href={item[key] ?? undefined} target="_blank" rel="noreferrer">{item[key]}</a> : item[key] || '—'}</dd>
              </div>
            ))}
            {selects.map(([key, label]) => <div key={key} className="application-detail-row"><dt>{label}</dt><dd>{item[key]}</dd></div>)}
            {numberFields.map(([key, label]) => <div key={key} className="application-detail-row"><dt>{label}</dt><dd>{item[key]}</dd></div>)}
          </dl>
        </>
      )}
    </main>
  );
}

export function ApplicationForm({ user, edit = false }: { user: User; edit?: boolean }) {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [fields, setFields] = useState<ApplicationInput>(blank);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const allowed = canWrite(user);
  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    let active = true;
    Promise.all([request<Page<Portfolio>>('/portfolios?limit=100'), edit ? request<Application>(`/applications/${id}`) : Promise.resolve(null)])
      .then(([list, item]) => {
        if (active) {
          setPortfolios(list.items);
          if (item) {
            const { id: _id, createdAt: _created, updatedAt: _updated, ...input } = item;
            setFields(input);
          }
        }
      })
      .catch(err => { if (active) setError(message(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed, edit, id]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const saved = await request<Application>(edit ? `/applications/${id}` : '/applications', edit ? 'PUT' : 'POST', fields);
      navigate(`/applications/${saved.id}`);
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  return (
    <main className="page">
      <Link to={edit ? `/applications/${id}` : '/applications'}>← Cancel</Link>
      <h1>{edit ? 'Edit application' : 'Create application'}</h1>
      {!allowed && <p role="alert" className="error">You cannot change applications.</p>}
      {loading && <p role="status">Loading application form…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {allowed && !loading && (!edit || fields.name) && (
        <form className="portfolio-form" onSubmit={submit}>
          {textFields.map(([key, label]) => (
            <div className="application-field" key={key}>
              <label htmlFor={`field-${key}`}>{label}</label>
              {key === 'description' || key === 'technologyStack' ? (
                <textarea id={`field-${key}`} maxLength={4000} value={fields[key]} onChange={event => setFields({ ...fields, [key]: event.target.value })} />
              ) : (
                <input id={`field-${key}`} type={key === 'repositoryLink' || key === 'pipelineLink' ? 'url' : 'text'} required={key === 'name'} maxLength={key.endsWith('Link') ? 2048 : 200} value={fields[key] ?? ''} onChange={event => setFields({ ...fields, [key]: key.endsWith('Link') ? event.target.value || null : event.target.value })} />
              )}
            </div>
          ))}
          <div className="application-field">
            <label htmlFor="field-portfolio">Portfolio</label>
            <select id="field-portfolio" required value={fields.portfolioId} onChange={event => setFields({ ...fields, portfolioId: event.target.value })}>
              <option value="">Select a portfolio</option>
              {portfolios.map(portfolio => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
            </select>
          </div>
          {selects.map(([key, label, options]) => (
            <div className="application-field" key={key}>
              <label htmlFor={`field-${key}`}>{label}</label>
              <select id={`field-${key}`} value={fields[key]} onChange={event => setFields({ ...fields, [key]: event.target.value })}>
                {options.map(option => <option key={option}>{option}</option>)}
              </select>
            </div>
          ))}
          {numberFields.map(([key, label, min, max]) => (
            <div className="application-field" key={key}>
              <label htmlFor={`field-${key}`}>{label}</label>
              <input id={`field-${key}`} type="number" required min={min} max={max} step={1} value={fields[key]} onChange={event => setFields({ ...fields, [key]: event.target.valueAsNumber })} />
            </div>
          ))}
          <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save application'}</button>
        </form>
      )}
    </main>
  );
}
