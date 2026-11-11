import React, { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';
import { ShieldCheck, X, ArrowRight } from 'lucide-react';
import { NAV_ITEMS, isNavItemActive } from './navItems';
import { useRipple } from '@/hooks/useRipple';
import { RippleOverlay } from '@/components/ui/RippleOverlay';
import { cn } from '@/lib/utils';

interface MobileDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Mobile slide-out navigation drawer (< lg screens).
 * Replaced persistent desktop sidebar per approved Option A architecture.
 */
export const Sidebar: React.FC<MobileDrawerProps> = ({ isOpen, onClose }) => {
  const location = useLocation();
  const { ripples, triggerRipple } = useRipple();

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  return (
    <div className="lg:hidden">
      {/* Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-navy-950/75 backdrop-blur-sm"
        />
      )}

      {/* Slide-out Drawer */}
      <aside
        id="mobile-nav-drawer"
        aria-label="Mobile Navigation Drawer"
        aria-hidden={!isOpen}
        className={cn(
          'glass-nav fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r transition-transform duration-300',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-border/70 px-5">
          <Link
            to="/"
            onClick={onClose}
            className="flex items-center gap-2.5 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-[#087BFF] to-[#00C8FF] text-white shadow-glow-cyan">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-1 font-bold tracking-tight text-foreground text-sm">
                <span>FakeNews</span>
                <span className="bg-gradient-to-r from-[#087BFF] to-[#00C8FF] bg-clip-text text-transparent font-extrabold">
                  Blockchain
                </span>
              </div>
              <p className="text-[10px] text-slate-600 dark:text-slate-400 font-mono uppercase tracking-wider">
                Navigation
              </p>
            </div>
          </Link>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close Navigation Drawer"
            className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 hover:bg-cyan-500/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1.5 overflow-y-auto px-4 py-5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isNavItemActive(location.pathname, item);
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={onClose}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'group relative flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-xs font-medium transition-colors duration-150',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
                  active
                    ? 'text-brand-blue dark:text-cyan-300 font-semibold'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-cyan-500/10 hover:text-foreground'
                )}
              >
                {active && (
                  <motion.span
                    layoutId="mobile-drawer-active-indicator"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                    className="absolute inset-0 rounded-xl border border-cyan-500/35 bg-gradient-to-r from-[#087BFF]/15 to-[#00C8FF]/10"
                  />
                )}
                <Icon
                  className={cn(
                    'relative z-10 h-4 w-4 shrink-0 transition-colors',
                    active
                      ? 'text-brand-blue dark:text-cyan-400'
                      : 'group-hover:text-brand-blue dark:group-hover:text-cyan-400'
                  )}
                />
                <span className="relative z-10">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border/70 p-4">
          <Link
            to="/verify"
            onClick={(e) => {
              triggerRipple(e);
              onClose();
            }}
            className="btn-primary-glow relative overflow-hidden flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <RippleOverlay ripples={ripples} />
            <span className="relative z-10">Verify Now</span>
            <ArrowRight className="relative z-10 h-3.5 w-3.5" />
          </Link>
        </div>
      </aside>
    </div>
  );
};
