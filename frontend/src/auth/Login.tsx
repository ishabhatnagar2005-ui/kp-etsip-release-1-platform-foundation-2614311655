import { useState, type FormEvent } from 'react';
import { signIn } from '../api';
import type { User } from '../types';

export default function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try { onLogin(await signIn(email, password)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  return (
    <main className="login-layout">
      <section className="intro">
        <p className="eyebrow">KP ETSIP · PLATFORM FOUNDATION</p>
        <h1>Quality, in perspective.</h1>
        <p>One foundation for trusted application and portfolio insight.</p>
      </section>
      <section className="card login-card" aria-labelledby="login-title">
        <p className="eyebrow">LOCAL ACCOUNT</p>
        <h2 id="login-title">Sign in</h2>
        <p>Use the credentials provided by your administrator.</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="username" required aria-required="true" value={email} onChange={event => setEmail(event.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required aria-required="true" value={password} onChange={event => setPassword(event.target.value)} />
          {error && <p role="alert" className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  );
}
