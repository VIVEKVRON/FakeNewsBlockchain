import React from 'react';
import type { RippleWave } from '@/hooks/useRipple';

interface RippleOverlayProps {
  ripples: RippleWave[];
}

export const RippleOverlay: React.FC<RippleOverlayProps> = ({ ripples }) => {
  if (ripples.length === 0) return null;

  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]">
      {ripples.map((wave) => (
        <span
          key={wave.id}
          className="glass-ripple-circle"
          style={{
            left: wave.x,
            top: wave.y,
            width: wave.size,
            height: wave.size,
          }}
        />
      ))}
    </span>
  );
};
