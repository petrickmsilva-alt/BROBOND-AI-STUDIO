'use client';

/**
 * PR009.6 — Premium Login Experience.
 * PR009.6.1 — Pixel Perfect Login.
 *
 * A fullscreen 100vw × 100vh surface split by a fixed grid: the founder
 * hero (the official photograph) at 58% and the glass login card at 42%,
 * with no outer margins. The PT/EN switch now lives inside the card, where
 * the approved mockup puts it. The authentication logic
 * below is the logic the modal owned, unchanged: the same `authenticate()`
 * call against the same endpoints, the same local-session fallback when
 * the API is unreachable, the same sign-out. Nothing in lib/api's auth
 * surface, lib/network, the backend or the routes changed to render this
 * screen — the only addition is "Lembrar de mim" (30 days), a cookie that
 * remembers who signed in while the JWT remains the only credential.
 */
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { authenticate, type AuthUser } from '../../../lib/api';
import { clearAuthToken, setAuthToken } from '../../../lib/memory/project_memory';
import { failureMessage } from '../../../lib/network/status';
import {
  clearRememberedLogin,
  getRememberedLogin,
  setRememberedLogin,
} from '../../../lib/memory/remembered_login';
import { LOGIN_COPY, type LoginLanguage } from './login-copy';
import { LoginHeroPanel } from './login-hero-panel';
import { LoginCard } from './login-card';

export type LoginScreenProps = {
  user: AuthUser | null;
  /** Home's honest readiness read — drives the footer's status dot. */
  online: boolean;
  onAuthenticated: (user: AuthUser | null) => void;
  onClose: () => void;
};

export function LoginScreen({ user, online, onAuthenticated, onClose }: LoginScreenProps) {
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('oauth_token');
    if (token) { setAuthToken(token); window.history.replaceState({}, '', window.location.pathname); window.location.reload(); }
  }, []);

  const [language, setLanguage] = useState<LoginLanguage>('pt');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState<'google' | 'forgot' | null>(null);
  const [rememberedName, setRememberedName] = useState<string | null>(null);
  const copy = LOGIN_COPY[language];

  // "Lembrar de mim": greet the returning creator whose session Home may
  // have just restored (or let expire). Pure read of the convenience
  // record — the credential is the JWT, untouched.
  useEffect(() => {
    const remembered = getRememberedLogin();
    if (!remembered) return;
    setEmail(remembered.email);
    setRememberedName(remembered.name);
  }, []);

  // The fullscreen surface has no backdrop to click away — Escape keeps
  // the dismissal affordance the modal had.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  /** Authentication flow — unchanged from the AuthModal it replaces. */
  const submit = async () => {
    setNotice(null);
    setMessage(copy.connecting);
    const result = await authenticate(
      mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register',
      mode === 'login' ? { email, password } : { email, name, password },
    );
    if (result.remote) {
      if (remember) setRememberedLogin(result.data.user.email, result.data.user.name);
      else clearRememberedLogin();
      onAuthenticated(result.data.user);
      onClose();
      return;
    }
    // A rejected login must not be reported as "offline": those are different
    // problems and only one of them is fixed by starting the server.
    if (result.status) {
      setMessage(result.error ?? `Request failed (${result.status})`);
      return;
    }
    if (mode === 'login') {
      // Local fallback (API unreachable): the same session shape as before,
      // and "Lembrar de mim" keeps it restorable for 30 days.
      const local = { id: 'local', email: email || 'local@brobond.ai', name: name || 'Local session' };
      if (remember) setRememberedLogin(local.email, local.name);
      else clearRememberedLogin();
      onAuthenticated(local);
      onClose();
    } else {
      setMessage(failureMessage(result, 'API offline. Start FastAPI to create a persistent account.'));
    }
  };

  const logout = () => {
    clearAuthToken();
    clearRememberedLogin();
    onAuthenticated(null);
    onClose();
  };

  const switchMode = () => {
    setMode(current => (current === 'login' ? 'register' : 'login'));
    setMessage('');
    setNotice(null);
  };

  return (
    <div className="bb-login-overlay" role="dialog" aria-modal="true" aria-label={copy.cardTitle}>
      <LoginHeroPanel copy={copy} />
      <section className="bb-login-side">
        <button type="button" className="bb-login-close" onClick={onClose} aria-label={copy.closeLabel}>
          <X size={18} />
        </button>
        <LoginCard
          copy={copy}
          mode={mode}
          user={user}
          rememberedName={rememberedName}
          online={online}
          message={message}
          notice={notice}
          language={language}
          email={email}
          password={password}
          name={name}
          remember={remember}
          onLanguageChange={setLanguage}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onNameChange={setName}
          onRememberChange={setRemember}
          onSubmit={submit}
          onGoogle={() => { window.location.href = '/api/v1/auth/google/login'; }}
          onForgot={() => { setNotice('forgot'); setMessage(''); }}
          onLogout={logout}
          onBackToStudio={onClose}
          onModeChange={switchMode}
        />
      </section>
    </div>
  );
}

export default LoginScreen;
