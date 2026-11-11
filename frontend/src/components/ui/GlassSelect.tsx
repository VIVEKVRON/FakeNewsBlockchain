import React, { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { cn } from '@/lib/utils';

export interface GlassSelectOption {
  value: string;
  label: string;
}

interface GlassSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: GlassSelectOption[];
  ariaLabel: string;
  className?: string;
}

/**
 * Accessible frosted-glass dropdown select supporting Arrow/Home/End/Enter/Escape
 * keyboard navigation and click-outside dismissal.
 */
export const GlassSelect: React.FC<GlassSelectProps> = ({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}) => {
  const [open, setOpen] = useState(false);
  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value)
  );
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();

  useEffect(() => {
    if (!open) return;

    const handleOutsideClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleWindowKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleWindowKey);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleWindowKey);
    };
  }, [open]);

  const currentOption = options[selectedIndex] || options[0];

  const openMenu = (startIdx?: number) => {
    setActiveIndex(startIdx ?? selectedIndex);
    setOpen(true);
  };

  const commitIndex = (idx: number) => {
    const opt = options[idx];
    if (!opt) return;
    onChange(opt.value);
    setOpen(false);
    buttonRef.current?.focus();
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (options.length === 0) return;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) {
          openMenu((selectedIndex + 1) % options.length);
        } else {
          setActiveIndex((prev) => (prev + 1) % options.length);
        }
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (!open) {
          openMenu((selectedIndex - 1 + options.length) % options.length);
        } else {
          setActiveIndex((prev) => (prev - 1 + options.length) % options.length);
        }
        break;
      case 'Home':
        if (open) {
          event.preventDefault();
          setActiveIndex(0);
        }
        break;
      case 'End':
        if (open) {
          event.preventDefault();
          setActiveIndex(options.length - 1);
        }
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (!open) {
          openMenu();
        } else {
          commitIndex(activeIndex);
        }
        break;
      case 'Tab':
        if (open) {
          setOpen(false);
        }
        break;
      default:
        break;
    }
  };

  return (
    <div ref={containerRef} className={cn('relative inline-block', className)}>
      <button
        ref={buttonRef}
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open ? `${listboxId}-opt-${activeIndex}` : undefined}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={handleKeyDown}
        className={cn(
          'glass-surface flex items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-xs font-medium text-foreground',
          'transition-colors hover:border-cyan-400/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
          open && 'border-cyan-400/60 ring-1 ring-cyan-400/40'
        )}
      >
        <span className="truncate">{currentOption?.label}</span>
        <ChevronDown
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400 transition-transform duration-150',
            open && 'rotate-180 text-cyan-500 dark:text-cyan-400'
          )}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.ul
            id={listboxId}
            role="listbox"
            aria-label={ariaLabel}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.14, ease: 'easeOut' }}
            className="glass-dropdown absolute left-0 z-50 mt-1.5 min-w-[11.5rem] max-h-60 overflow-y-auto rounded-xl p-1 text-xs"
          >
            {options.map((opt, idx) => {
              const isSelected = opt.value === value;
              const isFocused = idx === activeIndex;
              return (
                <li
                  key={opt.value}
                  id={`${listboxId}-opt-${idx}`}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    commitIndex(idx);
                  }}
                  className={cn(
                    'flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 transition-colors',
                    isFocused && 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300',
                    isSelected && !isFocused && 'bg-brand-blue/10 font-semibold text-brand-blue dark:text-cyan-300',
                    !isFocused && !isSelected && 'text-foreground/90'
                  )}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSelected && <Check className="h-3.5 w-3.5 shrink-0 text-cyan-500 dark:text-cyan-400" />}
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
};
