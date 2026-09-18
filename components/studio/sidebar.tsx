'use client';

/**
 * PR012 — BROBOND UI 4.0: the cinematic Sidebar.
 *
 * Pure presentational component (no fetch, no router, no backend contract):
 * it renders whatever groups/items it is given and calls back on
 * navigation. `app/page.tsx` owns the actual routing decision (view switch
 * vs. `router.push`) exactly as it did before this PR — only the visual
 * organization changes.
 *
 * ETAPA 3 rules enforced here:
 *  - exactly three groups are expected: CREATE, STUDIO, LIBRARY (the
 *    component does not hardcode them so it stays testable, but the badge
 *    allow-list below is enforced regardless of what the caller passes);
 *  - fixed width — 248px — never fluid;
 *  - badges are shown only for GPU / SQL / AI (`isAllowedBadge`), every
 *    other badge is silently dropped so the sidebar cannot regress back
 *    into "a badge on every row".
 */
import type { LucideIcon } from 'lucide-react';
import { ChevronDown } from 'lucide-react';
import { isAllowedBadge, layout } from '../../lib/theme/tokens';

export type SidebarNavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Only 'GPU' | 'SQL' | 'AI' ever render — anything else is dropped. */
  badge?: string;
};

export type SidebarGroup = {
  id: string;
  label: string;
  items: SidebarNavItem[];
};

export type SidebarBrand = {
  name: string;
  sub?: string;
};

export type SidebarProps = {
  groups: SidebarGroup[];
  activeId: string;
  onNavigate: (id: string) => void;
  brand?: SidebarBrand;
  onBrandClick?: () => void;
  collapsed?: boolean;
  /** Rendered under the nav, above where the removed readiness list used
   * to live — e.g. the auth/profile row. The Status Dock (ETAPA 6) now
   * owns system health; this sidebar no longer shows a readiness list. */
  footer?: React.ReactNode;
};

export function Sidebar({ groups, activeId, onNavigate, brand, onBrandClick, collapsed = false, footer }: SidebarProps) {
  return (
    <aside
      className={`bb-sidebar ${collapsed ? 'bb-sidebar-collapsed' : ''}`}
      style={{ width: collapsed ? 0 : layout.sidebarWidth }}
      data-testid="bb-sidebar"
    >
      {brand && (
        <button type="button" className="bb-sidebar-brand" onClick={onBrandClick} aria-label={`${brand.name} — go to overview`}>
          <span className="bb-sidebar-brand-mark" aria-hidden="true" />
          <span className="bb-sidebar-brand-name">{brand.name}</span>
          {brand.sub && <span className="bb-sidebar-brand-sub">{brand.sub}</span>}
          <ChevronDown size={14} className="bb-sidebar-brand-chevron" aria-hidden="true" />
        </button>
      )}

      <nav className="bb-sidebar-nav" aria-label="Main navigation">
        {groups.map(group => (
          <div className="bb-nav-group" key={group.id}>
            <div className="bb-nav-label" id={`bb-nav-label-${group.id}`}>{group.label}</div>
            <ul className="bb-nav-list" aria-labelledby={`bb-nav-label-${group.id}`}>
              {group.items.map(item => {
                const Icon = item.icon;
                const active = item.id === activeId;
                const badge = item.badge && isAllowedBadge(item.badge) ? item.badge : undefined;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`bb-nav-item ${active ? 'bb-nav-item-active' : ''}`}
                      onClick={() => onNavigate(item.id)}
                      aria-current={active ? 'page' : undefined}
                    >
                      <Icon size={18} strokeWidth={active ? 2.1 : 1.7} aria-hidden="true" />
                      <span>{item.label}</span>
                      {badge && <em className="bb-badge" data-badge={badge}>{badge}</em>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {footer && <div className="bb-sidebar-footer">{footer}</div>}
    </aside>
  );
}

export default Sidebar;
