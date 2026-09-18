'use client';

/**
 * PR009.6 — the glassmorphism login card: logo oficial, "Bem-vindo de
 * volta", email/senha, Lembrar de mim (30 dias), Esqueceu sua senha?, the
 * gold "Entrar no Brobond Studio" and "Entrar com Google". Purely
 * presentational — the authentication flow lives in LoginScreen, exactly
 * where the old AuthModal owned it.
 */
import { useState } from 'react';
import { ArrowRight, Eye, EyeOff, Lock, LogOut, Mail, UserRound } from 'lucide-react';
import type { AuthUser } from '../../../lib/api';
import type { LoginCopy } from './login-copy';

export type LoginCardProps = {
  copy: LoginCopy;
  mode: 'login' | 'register';
  user: AuthUser | null;
  /** Display name of a remembered login (30 days), for the returning chip. */
  rememberedName: string | null;
  online: boolean;
  message: string;
  notice: 'google' | 'forgot' | null;
  email: string;
  password: string;
  name: string;
  remember: boolean;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onNameChange: (value: string) => void;
  onRememberChange: (value: boolean) => void;
  onSubmit: () => void;
  onGoogle: () => void;
  onForgot: () => void;
  onLogout: () => void;
  onBackToStudio: () => void;
  onModeChange: () => void;
};

/** The Google "G" brand mark at 18px. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A8.997 8.997 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.42 0 9 0A8.997 8.997 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}

function initialsOf(name: string): string {
  return name.trim().slice(0, 2).toUpperCase() || 'BR';
}

/** Card footer: version + the honest system indicator. */
function CardFooter({ copy, online }: { copy: LoginCopy; online: boolean }) {
  return (
    <footer className="bb-login-footer">
      <span>{copy.version}</span>
      <span className={`bb-login-status${online ? '' : ' is-offline'}`} role="status">
        <i aria-hidden="true" />
        {online ? copy.online : copy.offline}
      </span>
    </footer>
  );
}

export function LoginCard(props: LoginCardProps) {
  const { copy } = props;
  const [passwordVisible, setPasswordVisible] = useState(false);

  // Signed-in view: the account, "Voltar ao studio" and "Sair" — the same
  // sign-out the old modal offered.
  if (props.user) {
    return (
      <div className="bb-login-card">
        <div className="bb-login-account">
          <div className="bb-login-avatar" aria-hidden="true">{initialsOf(props.user.name)}</div>
          <h2 className="bb-login-account-name">{props.user.name}</h2>
          <p className="bb-login-card-sub">{props.user.email}</p>
          <span className="bb-login-session"><i aria-hidden="true" />{copy.signedInSubtitle}</span>
          <div className="bb-login-account-actions">
            <button type="button" className="bb-login-submit" onClick={props.onBackToStudio}>
              {copy.backToStudio}<ArrowRight size={16} aria-hidden="true" />
            </button>
            <button type="button" className="bb-login-ghost" onClick={props.onLogout}>
              <LogOut size={15} aria-hidden="true" />{copy.signOut}
            </button>
          </div>
        </div>
        <CardFooter copy={copy} online={props.online} />
      </div>
    );
  }

  return (
    <div className="bb-login-card">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="bb-login-card-logo" src="/brand/brobond-logo.png" alt="Brobond" />
      <h2>{props.mode === 'login' ? copy.cardTitle : copy.registerTitle}</h2>
      <p className="bb-login-card-sub">{props.mode === 'login' ? copy.cardSubtitle : copy.registerSubtitle}</p>

      {props.mode === 'login' && props.rememberedName && (
        <div className="bb-login-remembered">
          <span className="bb-login-remembered-avatar" aria-hidden="true">{initialsOf(props.rememberedName)}</span>
          <span className="bb-login-remembered-text">
            {copy.continueAs} <strong>{props.rememberedName}</strong>
          </span>
        </div>
      )}

      <form onSubmit={event => { event.preventDefault(); props.onSubmit(); }}>
        {props.mode === 'register' && (
          <label className="bb-login-field">
            <span>{copy.fullName}</span>
            <span className="bb-login-field-box">
              <UserRound size={16} aria-hidden="true" />
              <input
                className="bb-login-input"
                value={props.name}
                onChange={event => props.onNameChange(event.target.value)}
                placeholder={copy.fullNamePlaceholder}
                required
                autoComplete="name"
              />
            </span>
          </label>
        )}
        <label className="bb-login-field">
          <span>{copy.email}</span>
          <span className="bb-login-field-box">
            <Mail size={16} aria-hidden="true" />
            <input
              className="bb-login-input"
              type="email"
              value={props.email}
              onChange={event => props.onEmailChange(event.target.value)}
              placeholder={copy.emailPlaceholder}
              required
              autoComplete="email"
            />
          </span>
        </label>
        <label className="bb-login-field">
          <span>{copy.password}</span>
          <span className="bb-login-field-box">
            <Lock size={16} aria-hidden="true" />
            <input
              className="bb-login-input"
              type={passwordVisible ? 'text' : 'password'}
              value={props.password}
              onChange={event => props.onPasswordChange(event.target.value)}
              placeholder={copy.passwordPlaceholder}
              minLength={8}
              required
              autoComplete={props.mode === 'login' ? 'current-password' : 'new-password'}
            />
            <button
              type="button"
              className="bb-login-eye"
              onClick={() => setPasswordVisible(visible => !visible)}
              aria-label={passwordVisible ? copy.hidePassword : copy.showPassword}
            >
              {passwordVisible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
            </button>
          </span>
        </label>

        <div className="bb-login-row">
          <label className="bb-login-check">
            <input
              type="checkbox"
              checked={props.remember}
              onChange={event => props.onRememberChange(event.target.checked)}
            />
            {copy.remember}
          </label>
          <button type="button" className="bb-login-link" onClick={props.onForgot}>{copy.forgot}</button>
        </div>
        <p className="bb-login-remember-hint">{copy.rememberHint}</p>

        <button className="bb-login-submit" type="submit">
          {props.mode === 'login' ? copy.signIn : copy.registerButton}
          <ArrowRight size={16} aria-hidden="true" />
        </button>

        {props.mode === 'login' && (
          <>
            <div className="bb-login-divider">{copy.orDivider}</div>
            <button type="button" className="bb-login-google" onClick={props.onGoogle}>
              <GoogleMark />
              {copy.google}
            </button>
          </>
        )}
      </form>

      {props.notice && (
        <div className="bb-login-notice" role="status">
          {props.notice === 'google' ? copy.googleNotice : copy.forgotNotice}
        </div>
      )}
      {props.message && <small className="bb-login-message" role="status">{props.message}</small>}

      <div className="bb-login-switch">
        {props.mode === 'login' ? copy.noAccount : copy.hasAccount}{' '}
        <button type="button" className="bb-login-link" onClick={props.onModeChange}>
          {props.mode === 'login' ? copy.createAccount : copy.backToLogin}
        </button>
      </div>

      <CardFooter copy={copy} online={props.online} />
    </div>
  );
}

export default LoginCard;
