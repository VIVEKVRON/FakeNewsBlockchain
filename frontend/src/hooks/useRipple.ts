import { useCallback, useEffect, useRef, useState } from 'react';

export interface RippleWave {
  id: number;
  x: number;
  y: number;
  size: number;
}

/**
 * Provides restrained pointer-centered click ripple waves without affecting
 * layout or keeping idle timers running.
 */
export function useRipple() {
  const [ripples, setRipples] = useState<RippleWave[]>([]);
  const nextId = useRef(0);
  const timeoutsRef = useRef<number[]>([]);

  useEffect(() => {
    const timeouts = timeoutsRef.current;
    return () => {
      timeouts.forEach((t) => window.clearTimeout(t));
    };
  }, []);

  const triggerRipple = useCallback((event: React.MouseEvent<HTMLElement>) => {
    if (
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.45;
    const isKeyboardOrigin = event.clientX === 0 && event.clientY === 0;
    const x = isKeyboardOrigin ? rect.width / 2 : event.clientX - rect.left;
    const y = isKeyboardOrigin ? rect.height / 2 : event.clientY - rect.top;
    const id = ++nextId.current;

    setRipples((prev) => [...prev.slice(-2), { id, x, y, size }]);

    const timer = window.setTimeout(() => {
      setRipples((prev) => prev.filter((item) => item.id !== id));
    }, 520);
    timeoutsRef.current.push(timer);
  }, []);

  return { ripples, triggerRipple };
}
