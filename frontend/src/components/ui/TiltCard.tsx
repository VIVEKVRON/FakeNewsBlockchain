import React, { useRef } from 'react';
import { usePointerCapabilities } from '@/hooks/usePointerCapabilities';
import { cn } from '@/lib/utils';

interface TiltCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  maxTiltDeg?: number;
  className?: string;
}

/**
 * Compact interactive glass container with gentle GPU-composited 3D pointer tilt
 * and a soft cyan edge sheen. Disabled on touch devices and reduced-motion setups.
 */
export const TiltCard: React.FC<TiltCardProps> = ({
  children,
  maxTiltDeg = 3.2,
  className,
  onMouseMove,
  onMouseLeave,
  ...rest
}) => {
  const { interactiveMotionEnabled } = usePointerCapabilities();
  const cardRef = useRef<HTMLDivElement>(null);
  const sheenRef = useRef<HTMLDivElement>(null);

  const handleMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    onMouseMove?.(event);
    if (!interactiveMotionEnabled) return;

    const card = cardRef.current;
    if (!card) return;
    const rect = card.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const px = (event.clientX - rect.left) / rect.width;
    const py = (event.clientY - rect.top) / rect.height;
    const rotateY = (px - 0.5) * (maxTiltDeg * 2);
    const rotateX = (0.5 - py) * (maxTiltDeg * 2);

    card.style.transform = `perspective(950px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-2px)`;
    if (sheenRef.current) {
      sheenRef.current.style.opacity = '1';
      sheenRef.current.style.background = `radial-gradient(280px circle at ${(px * 100).toFixed(1)}% ${(py * 100).toFixed(1)}%, rgba(0, 200, 255, 0.14), transparent 72%)`;
    }
  };

  const handleMouseLeave = (event: React.MouseEvent<HTMLDivElement>) => {
    onMouseLeave?.(event);
    const card = cardRef.current;
    if (card) {
      card.style.transform = '';
    }
    if (sheenRef.current) {
      sheenRef.current.style.opacity = '0';
    }
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={cn(
        'glass-panel relative overflow-hidden rounded-2xl transition-[transform,border-color,box-shadow] duration-200 ease-out will-change-transform',
        'hover:border-cyan-400/35 hover:shadow-glow-cyan',
        className
      )}
      {...rest}
    >
      {interactiveMotionEnabled && (
        <div
          ref={sheenRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-200"
        />
      )}
      <div className="relative z-10 h-full">{children}</div>
    </div>
  );
};
