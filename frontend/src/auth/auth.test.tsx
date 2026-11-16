import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Login from './Login';
import Profile from './Profile';
import type { User } from '../types';
import * as api from '../api';

vi.mock('../api', () => ({ signIn: vi.fn(), saveProfile: vi.fn(), changePassword: vi.fn(), clearToken: vi.fn() }));
const user: User = { id: '1', name: 'Example', email: 'engineer@ketsip.local', role: 'Engineer', portfolioAccess: [], defaultLandingPage: null, mustChangePassword: false };
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('identity forms', () => {
  it('shows a rejected login and accepts valid credentials', async () => {
    const onLogin = vi.fn();
    vi.mocked(api.signIn).mockRejectedValueOnce(new Error('Invalid email or password')).mockResolvedValueOnce(user);
    const input = userEvent.setup();
    render(<Login onLogin={onLogin} />);
    await input.type(screen.getByLabelText('Email address'), user.email);
    await input.type(screen.getByLabelText('Password'), 'secret-password');
    await input.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
    await input.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(onLogin).toHaveBeenCalledWith(user);
  });
  it('shows identity and saves a landing preference', async () => {
    const onUpdate = vi.fn();
    vi.mocked(api.saveProfile).mockResolvedValue({ ...user, defaultLandingPage: 'dashboard' });
    const input = userEvent.setup();
    render(<Profile user={user} onUpdate={onUpdate} onSignedOut={vi.fn()} />);
    expect(screen.getByText(user.email)).toBeInTheDocument();
    await input.selectOptions(screen.getByLabelText('Default landing page'), 'dashboard');
    await input.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Landing preference saved');
    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ defaultLandingPage: 'dashboard' }));
  });
  it('shows a preference error without updating the profile', async () => {
    const onUpdate = vi.fn();
    vi.mocked(api.saveProfile).mockRejectedValueOnce(new Error('Preference could not be saved'));
    const input = userEvent.setup();
    render(<Profile user={user} onUpdate={onUpdate} onSignedOut={vi.fn()} />);
    await input.selectOptions(screen.getByLabelText('Default landing page'), 'applications');
    await input.click(screen.getByRole('button', { name: 'Save preference' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Preference could not be saved');
    expect(api.saveProfile).toHaveBeenCalledWith('applications');
    expect(onUpdate).not.toHaveBeenCalled();
  });
  it('displays password errors without signing out', async () => {
    const onSignedOut = vi.fn();
    vi.mocked(api.changePassword).mockRejectedValueOnce(new Error('Current password is incorrect'));
    const input = userEvent.setup();
    render(<Profile user={user} onUpdate={vi.fn()} onSignedOut={onSignedOut} />);
    await input.type(screen.getByLabelText('Current password'), 'wrong-password');
    await input.type(screen.getByLabelText('New password'), 'Replacement-password-456');
    await input.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Current password is incorrect');
    expect(api.changePassword).toHaveBeenCalledWith('wrong-password', 'Replacement-password-456');
    expect(api.clearToken).not.toHaveBeenCalled();
    expect(onSignedOut).not.toHaveBeenCalled();
  });
  it('clears the session and signs out after a successful password change', async () => {
    const onSignedOut = vi.fn();
    vi.mocked(api.changePassword).mockResolvedValueOnce(undefined);
    const input = userEvent.setup();
    render(<Profile user={{ ...user, mustChangePassword: true }} onUpdate={vi.fn()} onSignedOut={onSignedOut} />);
    expect(screen.getByRole('status')).toHaveTextContent('Change your initial administrator password');
    await input.type(screen.getByLabelText('Current password'), 'Original-password-123');
    await input.type(screen.getByLabelText('New password'), 'Replacement-password-456');
    await input.click(screen.getByRole('button', { name: 'Change password' }));
    expect(api.changePassword).toHaveBeenCalledWith('Original-password-123', 'Replacement-password-456');
    expect(api.clearToken).toHaveBeenCalledOnce();
    expect(onSignedOut).toHaveBeenCalledOnce();
  });
});
