import { useState, type FormEvent } from 'react';
import { changePassword, clearToken, saveProfile } from '../api';
import type { User } from '../types';

export default function Profile({ user, onUpdate, onSignedOut }: { user: User; onUpdate: (user: User) => void; onSignedOut: () => void }) {
  const [landing, setLanding] = useState<User['defaultLandingPage']>(user.defaultLandingPage);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try { onUpdate(await saveProfile(landing)); setMessage('Landing preference saved.'); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to save preference.'); }
    finally { setBusy(false); }
  }
  async function password(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try { await changePassword(current, next); clearToken(); onSignedOut(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to change password.'); }
    finally { setBusy(false); }
  }
  return (
    <main className="page">
      <p className="eyebrow">ACCOUNT SETTINGS</p>
      <h1>My Profile</h1>
      <p>Manage your account and how you start your work.</p>
      {user.mustChangePassword && <p className="notice" role="status">Change your initial administrator password before accessing other features.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <div className="profile-grid">
        <section className="card" aria-labelledby="identity-title">
          <h2 id="identity-title">Your identity</h2>
          <dl>
            <dt>Name</dt><dd>{user.name}</dd>
            <dt>Email</dt><dd>{user.email}</dd>
            <dt>Role</dt><dd>{user.role}</dd>
            <dt>Portfolio access</dt><dd>{user.portfolioAccess.length ? user.portfolioAccess.join(', ') : user.role === 'Portfolio Leader' ? 'No assigned portfolios' : 'All portfolios'}</dd>
          </dl>
        </section>
        <div className="stack">
          <section className="card" aria-labelledby="preference-title">
            <h2 id="preference-title">Landing preference</h2>
            <p>Choose where to start once inventory and dashboard features are available.</p>
            <form onSubmit={save}>
              <label htmlFor="landing">Default landing page</label>
              <select id="landing" value={landing ?? ''} onChange={event => setLanding((event.target.value || null) as User['defaultLandingPage'])}>
                <option value="">Role default</option><option value="dashboard">Executive Dashboard</option><option value="applications">Application Repository</option>
              </select>
              <button type="submit" disabled={busy}>Save preference</button>
            </form>
          </section>
          <section className="card" aria-labelledby="password-title">
            <h2 id="password-title">Change password</h2>
            <p>Use at least 12 characters. You will need to sign in again.</p>
            <form onSubmit={password}>
              <label htmlFor="current">Current password</label>
              <input id="current" type="password" autoComplete="current-password" required aria-required="true" value={current} onChange={event => setCurrent(event.target.value)} />
              <label htmlFor="new">New password</label>
              <input id="new" type="password" autoComplete="new-password" required aria-required="true" minLength={12} maxLength={72} value={next} onChange={event => setNext(event.target.value)} />
              <button type="submit" disabled={busy}>Change password</button>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}
