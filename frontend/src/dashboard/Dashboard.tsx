import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { clearToken, getToken } from '../api';
import type { DashboardMetrics, DashboardPortfolio } from '../types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';

async function loadDashboard(query: string): Promise<DashboardMetrics> {
  const token = getToken();
  const response = await fetch(`${base}/api/dashboard/executive${query ? `?${query}` : ''}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    if (response.status === 401) clearToken();
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to load dashboard.');
  }
  return response.json() as Promise<DashboardMetrics>;
}

export default function Dashboard() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [options, setOptions] = useState<DashboardPortfolio[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const query = params.toString();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([loadDashboard(query), query ? loadDashboard('') : Promise.resolve(null)])
      .then(([result, unfiltered]) => {
        if (active) {
          setData(result);
          setOptions((unfiltered ?? result).portfolios);
        }
      })
      .catch(err => {
        if (active) setError(err instanceof Error ? err.message : 'Unable to load dashboard.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [query, retry]);

  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  const cards = data ? [
    ['Enterprise Quality Score', data.enterpriseQualityScore],
    ['Application Health Score', data.applicationHealthScore],
    ['Automation Maturity Score', data.automationMaturityScore],
    ['Open Critical Defects', data.openCriticalDefects],
    ['Applications at Risk', data.applicationsAtRisk],
    ['Total Applications', data.totalApplications],
    ['Total Portfolios', data.totalPortfolios],
  ] as const : [];

  return (
    <main className="page">
      <p className="eyebrow">QUALITY INSIGHT</p>
      <h1>Executive Dashboard</h1>
      <p>Quality and risk across your visible application inventory.</p>
      <div className="filters" aria-label="Dashboard filters">
        <div>
          <label htmlFor="dashboard-portfolio">Portfolio</label>
          <select id="dashboard-portfolio" value={params.get('portfolioId') ?? ''} onChange={event => filter('portfolioId', event.target.value)}>
            <option value="">All portfolios</option>
            {options.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="dashboard-area">Product area</label>
          <input id="dashboard-area" value={params.get('productArea') ?? ''} onChange={event => filter('productArea', event.target.value)} />
        </div>
        <div>
          <label htmlFor="dashboard-risk">Risk level</label>
          <select id="dashboard-risk" value={params.get('riskLevel') ?? ''} onChange={event => filter('riskLevel', event.target.value)}>
            <option value="">All risk levels</option>
            <option value="Low">Low</option>
            <option value="Medium">Medium</option>
            <option value="High">High</option>
          </select>
        </div>
      </div>
      {loading && <p role="status">Loading dashboard…</p>}
      {!loading && error && (
        <div role="alert">
          <p className="error">{error}</p>
          <button type="button" onClick={() => setRetry(value => value + 1)}>Retry</button>
        </div>
      )}
      {!loading && !error && data && (
        <>
          {data.totalApplications === 0 && <p role="status">No applications match the selected filters.</p>}
          <section className="dashboard-cards" aria-label="Executive metrics">
            {cards.map(([label, value]) => (
              <div className="dashboard-card" key={label}>
                <h2>{label}</h2>
                <p>{value ?? '—'}</p>
              </div>
            ))}
          </section>
          <section className="dashboard-breakdown" aria-labelledby="portfolio-quality-title">
            <h2 id="portfolio-quality-title">Portfolio Quality Score</h2>
            {data.portfolios.length === 0 && <p>No portfolios match the selected filters.</p>}
            <ul>
              {data.portfolios.map(item => (
                <li key={item.id}>
                  <Link to={`/portfolios/${item.id}`}>{item.name}</Link>
                  <span>{item.qualityScore === null ? 'No score' : `${item.qualityScore} / 100`} · {item.applicationCount} applications</span>
                  <div className="dashboard-bar" aria-hidden="true"><span style={{ width: `${item.qualityScore ?? 0}%` }} /></div>
                </li>
              ))}
            </ul>
          </section>
          <section className="dashboard-breakdown" aria-labelledby="portfolio-risk-title">
            <h2 id="portfolio-risk-title">Applications at Risk by Portfolio</h2>
            <ul>
              {data.portfolios.map(item => (
                <li key={item.id}>
                  <span>{item.name}: {item.applicationsAtRisk} high-risk applications</span>
                  <div className="dashboard-bar" aria-hidden="true"><span style={{ width: `${item.applicationCount ? 100 * item.applicationsAtRisk / item.applicationCount : 0}%` }} /></div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
