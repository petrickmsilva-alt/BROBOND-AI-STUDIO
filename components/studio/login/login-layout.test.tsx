// @vitest-environment jsdom
//
// PR009.6.1 — Pixel Perfect Login: the structural contract of the approved
// mockup. These assertions are deliberately about *composition*, not about
// pixels a jsdom run cannot measure: the two columns exist, the hero uses
// the official photograph with its overlay stack, the five pillar cards are
// siblings in their own footer row (so they can never overlap the copy),
// and the card renders the twelve blocks in the mockup's exact order.
//
// Nothing here touches authentication: LoginCard is presentational and the
// flow stays in LoginScreen, unchanged.

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LOGIN_COPY } from './login-copy';
import { LoginCard } from './login-card';
import { LoginHeroPanel } from './login-hero-panel';

const copy = LOGIN_COPY.pt;

function renderCard(overrides: Partial<React.ComponentProps<typeof LoginCard>> = {}) {
  const noop = vi.fn();
  return render(
    <LoginCard
      copy={copy}
      mode="login"
      user={null}
      rememberedName={null}
      online
      message=""
      notice={null}
      language="pt"
      email=""
      password=""
      name=""
      remember
      onLanguageChange={noop}
      onEmailChange={noop}
      onPasswordChange={noop}
      onNameChange={noop}
      onRememberChange={noop}
      onSubmit={noop}
      onGoogle={noop}
      onForgot={noop}
      onLogout={noop}
      onBackToStudio={noop}
      onModeChange={noop}
      {...overrides}
    />,
  );
}

describe('PR009.6.1 hero column (58%)', () => {
  it('uses the official photograph and the full overlay stack', () => {
    const { container } = render(<LoginHeroPanel copy={copy} />);
    const photo = container.querySelector('.bb-login-hero-photo') as HTMLImageElement;
    expect(photo).toBeInTheDocument();
    expect(photo.getAttribute('src')).toBe('/brand/login-hero.jpg');
    for (const layer of ['tint', 'gold', 'vignette', 'shade']) {
      expect(container.querySelector(`.bb-login-hero-${layer}`), layer).toBeInTheDocument();
    }
    // The brand film of the previous iteration is gone — the mockup is the photo.
    expect(container.querySelector('video')).toBeNull();
  });

  it('carries the top bar on both sides and the 420px logo', () => {
    const { container } = render(<LoginHeroPanel copy={copy} />);
    expect(container.querySelector('.bb-login-hero-topbar-left')).toHaveTextContent(copy.topBar);
    expect(container.querySelector('.bb-login-hero-topbar-right')).toHaveTextContent(copy.topBarRight);
    const logo = container.querySelector('.bb-login-hero-logo') as HTMLImageElement;
    expect(logo.getAttribute('src')).toBe('/brand/brobond-logo-light.png');
    expect(container.querySelector('.bb-login-hero-title')).toHaveTextContent(copy.titleLead);
    expect(container.querySelector('.bb-login-hero-title span')).toHaveTextContent(copy.titleAccent);
    expect(container.querySelector('.bb-login-hero-subtitle')).toHaveTextContent(copy.subtitle);
  });

  it('aligns the five equal cards in their own footer row, below the copy', () => {
    const { container } = render(<LoginHeroPanel copy={copy} />);
    const cards = container.querySelectorAll('.bb-login-features > .bb-login-feature');
    expect(cards).toHaveLength(5);
    // one single row: every card is a direct sibling in the same list
    const list = container.querySelector('.bb-login-features');
    expect(Array.from(cards).every(card => card.parentElement === list)).toBe(true);
    // the cards live in the footer, never inside the copy block
    const footer = container.querySelector('.bb-login-hero-footer');
    expect(footer).toContainElement(list as HTMLElement);
    expect(container.querySelector('.bb-login-hero-content')).not.toContainElement(list as HTMLElement);
    copy.features.forEach((feature, index) => {
      expect(cards[index]).toHaveTextContent(feature.title);
      expect(cards[index]).toHaveTextContent(feature.subtitle);
      // exactly one gold icon per card — no stacked/overlapping marks
      expect(cards[index].querySelectorAll('svg')).toHaveLength(1);
    });
  });
});

describe('PR009.6.1 login column (42%)', () => {
  it('renders the twelve blocks in the mockup order', () => {
    const { container } = renderCard();
    const card = container.querySelector('.bb-login-card') as HTMLElement;
    const order = [
      '.bb-login-lang',
      '.bb-login-card-logo',
      'h2',
      '.bb-login-card-sub',
      'input[type="email"]',
      'input[type="password"]',
      '.bb-login-row',
      '.bb-login-submit',
      '.bb-login-divider',
      '.bb-login-google',
      '.bb-login-switch',
      '.bb-login-footer',
    ].map(selector => {
      const node = card.querySelector(selector);
      expect(node, selector).not.toBeNull();
      return node as Element;
    });
    for (let i = 1; i < order.length; i += 1) {
      // Node.DOCUMENT_POSITION_FOLLOWING === 4
      expect(
        order[i - 1].compareDocumentPosition(order[i]) & 4,
        `block ${i} must follow block ${i - 1}`,
      ).toBeTruthy();
    }
  });

  it('shows the official 220px logo, the PT/EN selector and the honest footer', () => {
    const { container } = renderCard();
    expect((container.querySelector('.bb-login-card-logo') as HTMLImageElement).getAttribute('src'))
      .toBe('/brand/brobond-logo-light.png');
    expect(screen.getByRole('button', { name: 'PT' })).toHaveClass('is-active');
    expect(screen.getByRole('button', { name: 'EN' })).not.toHaveClass('is-active');
    expect(screen.getByText(copy.cardTitle)).toBeInTheDocument();
    expect(screen.getByText(copy.version)).toBeInTheDocument();
    expect(screen.getByText(copy.online)).toBeInTheDocument();
  });

  it('keeps the offline indicator honest', () => {
    renderCard({ online: false });
    expect(screen.getByText(copy.offline)).toBeInTheDocument();
  });
});
