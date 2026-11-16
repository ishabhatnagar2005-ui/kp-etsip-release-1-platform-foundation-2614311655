import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { clearToken, getToken } from '../api';
import type { Application, Page, Portfolio, User } from '../types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';
type Kind = 'applications' | 'portfolios';

async function reportRequest(path: string): Promise<Response> {
  const token = getToken();
  const response = await fetch(`${base}/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    if (response.status === 401) clearToken();
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Report request failed.');
  }
  return response;
}

export function canExport(user: User): boolean {
  return user.role !== 'Read Only' && Boolean(user.effectivePermissions?.includes('export'));
}

export async function downloadReport(kind: Kind, params: URLSearchParams): Promise<void> {
  const query = new URLSearchParams(params);
  query.delete('tab');
  query.delete('offset');
  query.delete('limit');
  query.set('format', 'csv');
  const response = await reportRequest(`/reports/${kind}?${query}`);
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${kind}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function Reports({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get('tab') === 'portfolios' ? 'portfolios' : 'applications';
  const [page, setPage] = useState<Page<Application | Portfolio> | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const query = new URLSearchParams(params);
  query.delete('tab');
  const search = query.toString();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    reportRequest(`/reports/${kind}?${search}`)
      .then(response => response.json() as Promise<Page<Application | Portfolio>>)
      .then(result => { if (active) setPage(result); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Report request failed.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [kind, search]);

  useEffect(() => {
    let active = true;
    reportRequest('/portfolios?limit=100')
      .then(response => response.json() as Promise<Page<Portfolio>>)
      .then(result => { if (active) setPortfolios(result.items); })
      .catch(() => { if (active) setPortfolios([]); });
    return () => { active = false; };
  }, []);

  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'offset') next.delete('offset');
    setParams(next);
  }

  async function download() {
    setBusy(true);
    setExportError('');
    try { await downloadReport(kind, query); }
    catch (err) { setExportError(err instanceof Error ? err.message : 'Export failed.'); }
    finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="portfolio-heading">
        <div>
          <p className="eyebrow">INSIGHT</p>
          <h1>Reports</h1>
          <p>Review and export visible inventory.</p>
        </div>
        {canExport(user) && (
          <button type="button" disabled={busy} onClick={download}>
            {busy ? 'Exporting…' : 'Export CSV'}
          </button>
        )}
      </div>
      <nav className="actions" aria-label="Report types">
        <Link to="/reports?tab=applications" aria-current={kind === 'applications' ? 'page' : undefined}>Application Report</Link>
        <Link to="/reports?tab=portfolios" aria-current={kind === 'portfolios' ? 'page' : undefined}>Portfolio Report</Link>
      </nav>
      <h2>{kind === 'applications' ? 'Application Report' : 'Portfolio Report'}</h2>
      <div className="filters" aria-label="Report filters">
        <div>
          <label htmlFor="report-search">Search</label>
          <input id="report-search" value={params.get('search') ?? ''} onChange={event => change('search', event.target.value)} />
        </div>
        {kind === 'applications' ? (
          <>
            <div>
              <label htmlFor="report-portfolio">Portfolio</label>
              <select id="report-portfolio" value={params.get('portfolioId') ?? ''} onChange={event => change('portfolioId', event.target.value)}>
                <option value="">All portfolios</option>
                {portfolios.map(portfolio => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
              </select>
            </div>
            {([
              ['criticality', 'Criticality', ['Low', 'Medium', 'High', 'Critical']],
              ['riskLevel', 'Risk level', ['Low', 'Medium', 'High']],
              ['lifecycleStatus', 'Lifecycle status', ['Active', 'Deprecated', 'Retired']],
            ] as const).map(([key, label, options]) => (
              <div key={key}>
                <label htmlFor={`report-${key}`}>{label}</label>
                <select id={`report-${key}`} value={params.get(key) ?? ''} onChange={event => change(key, event.target.value)}>
                  <option value="">All</option>
                  {options.map(option => <option key={option}>{option}</option>)}
                </select>
              </div>
            ))}
          </>
        ) : (
          <>
            <div>
              <label htmlFor="report-status">Status</label>
              <select id="report-status" value={params.get('status') ?? ''} onChange={event => change('status', event.target.value)}>
                <option value="">All</option>
                <option>Active</option>
                <option>Archived</option>
              </select>
            </div>
            <div>
              <label htmlFor="report-product">Product area</label>
              <input id="report-product" value={params.get('productArea') ?? ''} onChange={event => change('productArea', event.target.value)} />
            </div>
          </>
        )}
      </div>
      {loading && <p role="status">Loading report…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {exportError && <p className="error" role="alert">{exportError}</p>}
      {!loading && !error && page && (page.items.length ? (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {(kind === 'applications' ? ['Name', 'Portfolio', 'Criticality', 'Tier', 'Lifecycle status', 'Health score', 'Automation coverage %', 'Open critical defects', 'Risk level'] : ['Name', 'Owner', 'Product area', 'Applications', 'Quality score', 'Status']).map(label => <th key={label} scope="col">{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {page.items.map(item => kind === 'applications' ? (
                  <tr key={item.id}>
                    <td><Link to={`/applications/${item.id}`}>{item.name}</Link></td>
                    <td>{portfolios.find(portfolio => portfolio.id === (item as Application).portfolioId)?.name ?? (item as Application).portfolioId}</td>
                    <td>{(item as Application).criticality}</td>
                    <td>{(item as Application).tier}</td>
                    <td>{(item as Application).lifecycleStatus}</td>
                    <td>{(item as Application).applicationHealthScore}</td>
                    <td>{(item as Application).automationCoverage}%</td>
                    <td>{(item as Application).openCriticalDefects}</td>
                    <td>{(item as Application).riskLevel}</td>
                  </tr>
                ) : (
                  <tr key={item.id}>
                    <td><Link to={`/portfolios/${item.id}`}>{item.name}</Link></td>
                    <td>{(item as Portfolio).owner}</td>
                    <td>{item.productArea}</td>
                    <td>{(item as Portfolio).applicationCount}</td>
                    <td>{(item as Portfolio).qualityScore ?? '—'}</td>
                    <td>{(item as Portfolio).status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>{page.offset + 1}–{page.offset + page.items.length} of {page.total}</span>
            <button type="button" disabled={page.offset === 0} onClick={() => change('offset', String(Math.max(0, page.offset - page.limit)))}>Previous</button>
            <button type="button" disabled={page.offset + page.limit >= page.total} onClick={() => change('offset', String(page.offset + page.limit))}>Next</button>
          </div>
        </>
      ) : <p>No report results found.</p>)}
    </main>
  );
}
