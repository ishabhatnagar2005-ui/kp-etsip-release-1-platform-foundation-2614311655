import { useEffect, useState } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import Login from './auth/Login';
import Profile from './auth/Profile';
import { PortfolioDetail, PortfolioForm, PortfolioList } from './portfolios/Portfolios';
import { ApplicationDetail, ApplicationForm, ApplicationList } from './applications/Applications';
import Dashboard from './dashboard/Dashboard';
import Admin from './admin/Admin';
import { getMe, getToken, signOut } from './api';
import type { User } from './types';

function landingPage(user: User): string {
  if (user.mustChangePassword) return '/profile';
  const preference = user.defaultLandingPage ?? (['Administrator', 'Executive'].includes(user.role) ? 'dashboard' : 'applications');
  return `/${preference}`;
}

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
        {user && !user.mustChangePassword && <nav className="main-nav" aria-label="Main navigation"><Link to="/dashboard">Dashboard</Link><Link to="/portfolios">Portfolios</Link><Link to="/applications">Applications</Link>{((user.role === 'Administrator' && user.effectivePermissions?.includes('administer')) || (['Administrator', 'Auditor'].includes(user.role) && user.effectivePermissions?.includes('view'))) && <Link to="/admin">Administration</Link>}<Link to="/profile">My Profile</Link></nav>}
      </header>
      {notice && <p className="page" role="status">{notice}</p>}
      <Routes>
        <Route path="/login" element={user ? <Navigate to={landingPage(user)} replace /> : <Login onLogin={setUser} />} />
        <Route path="/profile" element={user ? <Profile user={user} onUpdate={setUser} onSignedOut={() => { setUser(null); setNotice('Password changed. Please sign in again.'); }} /> : <Navigate to="/login" replace />} />
        <Route path="/dashboard" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <Dashboard />} />
        <Route path="/portfolios" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <PortfolioList user={user} />} />
        <Route path="/portfolios/new" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <PortfolioForm user={user} />} />
        <Route path="/portfolios/:id" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <PortfolioDetail user={user} />} />
        <Route path="/portfolios/:id/edit" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <PortfolioForm user={user} edit />} />
        <Route path="/applications" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationList user={user} />} />
        <Route path="/applications/new" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationForm user={user} />} />
        <Route path="/applications/:id" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationDetail user={user} />} />
        <Route path="/applications/:id/edit" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <ApplicationForm user={user} edit />} />
        <Route path="/admin" element={!user ? <Navigate to="/login" replace /> : user.mustChangePassword ? <Navigate to="/profile" replace /> : <Admin user={user} />} />
        <Route path="*" element={<Navigate to={user ? landingPage(user) : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
