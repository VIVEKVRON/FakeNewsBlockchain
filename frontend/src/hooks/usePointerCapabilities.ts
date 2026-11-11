import { useEffect, useState } from 'react';

interface PointerCapabilities {
  canHoverFine: boolean;
  prefersReducedMotion: boolean;
  interactiveMotionEnabled: boolean;
}

const getInitialCapabilities = (): PointerCapabilities => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return {
      canHoverFine: false,
      prefersReducedMotion: false,
      interactiveMotionEnabled: false,
    };
  }
  const canHoverFine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  return {
    canHoverFine,
    prefersReducedMotion,
    interactiveMotionEnabled: canHoverFine && !prefersReducedMotion,
  };
};

/**
 * Tracks pointer precision and user reduced-motion preferences so spotlight
 * and 3D card tilt automatically disable on touch devices or reduced motion.
 */
export function usePointerCapabilities(): PointerCapabilities {
  const [caps, setCaps] = useState<PointerCapabilities>(getInitialCapabilities);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }

    const pointerMq = window.matchMedia('(hover: hover) and (pointer: fine)');
    const motionMq = window.matchMedia('(prefers-reduced-motion: reduce)');

    const update = () => {
      const canHoverFine = pointerMq.matches;
      const prefersReducedMotion = motionMq.matches;
      setCaps({
        canHoverFine,
        prefersReducedMotion,
        interactiveMotionEnabled: canHoverFine && !prefersReducedMotion,
      });
    };

    pointerMq.addEventListener('change', update);
    motionMq.addEventListener('change', update);
    return () => {
      pointerMq.removeEventListener('change', update);
      motionMq.removeEventListener('change', update);
    };
  }, []);

  return caps;
}
