import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Login from './auth/Login';
import Profile from './auth/Profile';
import { getMe, getToken, signOut } from './api';
import type { User } from './types';

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(getToken()));
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (!getToken()) return;
    getMe().then(setUser).catch(() => setNotice('Your session could not be restored. Please sign in again.')).finally(() => setLoading(false));
  }, []);
  async function logout() {
    try { await signOut(); } catch { setNotice('Sign-out could not be confirmed by the server. Your local session was cleared.'); }
    setUser(null);
  }
  if (loading) return <main className="page" role="status">Loading your profile…</main>;
  return (
    <BrowserRouter>
      <header className="header">
        <div className="header-inner"><span className="brand">KP ETSIP <span>Platform Foundation</span></span>{user && <button className="header-button" onClick={logout}>Sign out</button>}</div>
      </header>
      {notice && <p className="page" role="status">{notice}</p>}
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/profile" replace /> : <Login onLogin={setUser} />} />
        <Route path="/profile" element={user ? <Profile user={user} onUpdate={setUser} onSignedOut={() => { setUser(null); setNotice('Password changed. Please sign in again.'); }} /> : <Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to={user ? '/profile' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
