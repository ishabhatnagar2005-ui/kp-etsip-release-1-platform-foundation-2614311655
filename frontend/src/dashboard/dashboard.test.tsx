import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Dashboard from './Dashboard';
import App from '../App';

const metrics = {
  enterpriseQualityScore: 81,
  applicationHealthScore: 51,
  automationMaturityScore: 21,
  openCriticalDefects: 5,
  applicationsAtRisk: 1,
  totalApplications: 2,
  totalPortfolios: 1,
  portfolios: [{ id: 'abc', name: 'Alpha', applicationCount: 2, qualityScore: 81, applicationsAtRisk: 1 }],
};
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

function Location() {
  const location = useLocation();
  return <p data-testid="location">{location.search}</p>;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState({}, '', '/');
});

describe('executive dashboard', () => {
  it('renders accessible metrics and portfolio links from the API', async () => {
    sessionStorage.setItem('etsip_token', 'token');
    const fetcher = vi.fn().mockResolvedValue(response(metrics));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByRole('status')).toHaveTextContent('Loading dashboard');
    const region = await screen.findByRole('region', { name: 'Executive metrics' });
    expect(within(region).getByText('81')).toBeVisible();
    expect(within(region).getByText('5')).toBeVisible();
    expect(screen.getByText('81 / 100 · 2 applications')).toBeVisible();
    expect(screen.getByText('Alpha: 1 high-risk applications')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/portfolios/abc');
    expect(fetcher).toHaveBeenCalledWith('/api/dashboard/executive', { headers: { Authorization: 'Bearer token' } });
  });

  it('keeps all filters in the URL and sends them to the API', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(metrics));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Dashboard /><Location /></MemoryRouter>);
    await screen.findByRole('link', { name: 'Alpha' });
    await userEvent.selectOptions(screen.getByLabelText('Portfolio'), 'abc');
    await userEvent.type(screen.getByLabelText('Product area'), 'One');
    await userEvent.selectOptions(screen.getByLabelText('Risk level'), 'High');
    expect(screen.getByTestId('location')).toHaveTextContent('portfolioId=abc&productArea=One&riskLevel=High');
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('portfolioId=abc&productArea=One&riskLevel=High'), expect.anything()));
  });

  it('displays errors, retries and describes an empty result', async () => {
    const empty = { ...metrics, enterpriseQualityScore: null, applicationHealthScore: null, automationMaturityScore: null, totalApplications: 0, totalPortfolios: 0, openCriticalDefects: 0, applicationsAtRisk: 0, portfolios: [] };
    const fetcher = vi.fn().mockResolvedValueOnce(response({ detail: 'Permission denied' }, 403)).mockResolvedValue(response(empty));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Permission denied');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('No applications match the selected filters.')).toBeVisible();
    expect(screen.getByText('No portfolios match the selected filters.')).toBeVisible();
  });
});

describe('landing page routing', () => {
  it.each([
    ['Administrator', null, false, 'Executive Dashboard'],
    ['Executive', null, false, 'Executive Dashboard'],
    ['Engineer', null, false, 'Applications'],
    ['Engineer', 'dashboard', false, 'Executive Dashboard'],
    ['Executive', 'applications', false, 'Applications'],
    ['Administrator', 'dashboard', true, 'My Profile'],
  ])('routes %s with preference %s and forced change %s to %s', async (role, preference, forced, heading) => {
    sessionStorage.setItem('etsip_token', 'token');
    window.history.replaceState({}, '', '/login');
    const user = { id: '1', name: 'Test User', email: 'test@example.com', role, portfolioAccess: [], defaultLandingPage: preference, mustChangePassword: forced };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/api/auth/me')) return Promise.resolve(response(user));
      if (url.includes('/api/dashboard/executive')) return Promise.resolve(response(metrics));
      return Promise.resolve(response({ items: [], total: 0, limit: 25, offset: 0 }));
    }));
    render(<App />);
    expect(await screen.findByRole('heading', { name: heading })).toBeVisible();
  });
});
