import React from 'react';
import { useRipple } from '@/hooks/useRipple';
import { RippleOverlay } from '@/components/ui/RippleOverlay';
import { cn } from '@/lib/utils';

interface RippleButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'glass';
}

/**
 * Interactive action button with optional primary cyan-blue gradient glow
 * and restrained pointer-centered click ripple feedback.
 */
export const RippleButton: React.FC<RippleButtonProps> = ({
  variant = 'primary',
  className,
  onClick,
  children,
  type = 'button',
  ...rest
}) => {
  const { ripples, triggerRipple } = useRipple();

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    triggerRipple(event);
    onClick?.(event);
  };

  return (
    <button
      type={type}
      onClick={handleClick}
      className={cn(
        'relative overflow-hidden inline-flex items-center justify-center gap-2 font-semibold',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variant === 'primary'
          ? 'btn-primary-glow text-white'
          : 'glass-surface text-foreground hover:border-cyan-400/45 transition-colors',
        className
      )}
      {...rest}
    >
      <RippleOverlay ripples={ripples} />
      <span className="relative z-10 inline-flex items-center justify-center gap-2">{children}</span>
    </button>
  );
};
