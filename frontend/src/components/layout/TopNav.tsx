import React from 'react';
import { Menu, Sun, Moon, ShieldCheck, ArrowRight } from 'lucide-react';
import { useLocation, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { useRipple } from '@/hooks/useRipple';
import { RippleOverlay } from '@/components/ui/RippleOverlay';
import { NAV_ITEMS, isNavItemActive } from './navItems';
import { cn } from '@/lib/utils';

interface TopNavProps {
  onToggleMobileDrawer: () => void;
  isMobileDrawerOpen: boolean;
  isDark: boolean;
  onToggleTheme: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({
  onToggleMobileDrawer,
  isMobileDrawerOpen,
  isDark,
  onToggleTheme,
}) => {
  const location = useLocation();
  const { ripples, triggerRipple } = useRipple();

  return (
    <header className="glass-nav sticky top-0 z-30 w-full border-b">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        {/* Left: Mobile Menu Trigger + Brand Mark */}
        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={onToggleMobileDrawer}
            aria-expanded={isMobileDrawerOpen}
            aria-controls="mobile-nav-drawer"
            aria-label="Open Navigation Drawer"
            className="rounded-xl p-2 text-slate-600 dark:text-slate-300 hover:bg-cyan-500/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 lg:hidden transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link
            to="/"
            className="flex items-center gap-2.5 group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-[#087BFF] to-[#00C8FF] text-white shadow-glow-cyan transition-transform duration-200 group-hover:scale-105">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <div className="flex items-center gap-1 text-sm font-bold tracking-tight text-foreground">
                <span>FakeNews</span>
                <span className="bg-gradient-to-r from-[#087BFF] to-[#00C8FF] bg-clip-text text-transparent font-extrabold">
                  Blockchain
                </span>
              </div>
              <p className="hidden sm:block text-[10px] font-mono uppercase tracking-wider text-slate-600 dark:text-slate-400">
                Evidence &middot; NLI &middot; Sepolia
              </p>
            </div>
          </Link>
        </div>

        {/* Center: Desktop Option-A Top Navigation Links */}
        <nav
          aria-label="Primary Navigation"
          className="hidden lg:flex items-center gap-1 rounded-2xl p-1"
        >
          {NAV_ITEMS.map((item) => {
            const active = isNavItemActive(location.pathname, item);
            return (
              <Link
                key={item.to}
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative whitespace-nowrap rounded-xl px-2.5 xl:px-3 py-1.5 text-xs font-medium transition-colors duration-150',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
                  active
                    ? 'text-brand-blue dark:text-cyan-300 font-semibold'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-cyan-500/10 hover:text-foreground'
                )}
              >
                {active && (
                  <motion.span
                    layoutId="topnav-active-indicator"
                    transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                    className="absolute inset-0 rounded-xl border border-cyan-500/35 bg-gradient-to-r from-[#087BFF]/15 to-[#00C8FF]/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
                  />
                )}
                <span
                  className="nav-link-underline relative z-10"
                  data-active={active ? 'true' : undefined}
                >
                  {item.shortLabel ? (
                    <>
                      <span className="hidden xl:inline">{item.label}</span>
                      <span className="xl:hidden">{item.shortLabel}</span>
                    </>
                  ) : (
                    item.label
                  )}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* Right: Theme Toggle + Verify Now Primary CTA */}
        <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
          <button
            type="button"
            onClick={onToggleTheme}
            className="glass-surface rounded-xl p-2 text-slate-600 dark:text-slate-300 hover:border-cyan-400/45 hover:text-foreground transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            title={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}
            aria-label={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}
          >
            {isDark ? (
              <Sun className="h-4 w-4 text-amber-400" />
            ) : (
              <Moon className="h-4 w-4 text-slate-700" />
            )}
          </button>

          <Link
            to="/verify"
            onClick={triggerRipple}
            className="btn-primary-glow relative overflow-hidden inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background whitespace-nowrap"
          >
            <RippleOverlay ripples={ripples} />
            <span className="relative z-10">Verify Now</span>
            <ArrowRight className="relative z-10 h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </header>
  );
};
