import React, { useEffect, useRef } from 'react';
import { usePointerCapabilities } from '@/hooks/usePointerCapabilities';

/**
 * Full-viewport ambient backdrop with a subtle pointer-following radial spotlight.
 * Updates DOM style variables directly in rAF (stopping when idle) and automatically
 * disables cursor tracking on touch devices or when prefers-reduced-motion is active.
 */
export const CursorSpotlight: React.FC = () => {
  const { interactiveMotionEnabled } = usePointerCapabilities();
  const spotlightRef = useRef<HTMLDivElement>(null);
  const pointerStateRef = useRef<{
    rafId: number | null;
    currentX: number;
    currentY: number;
    targetX: number;
    targetY: number;
    visible: boolean;
  }>({
    rafId: null,
    currentX: 0,
    currentY: 0,
    targetX: 0,
    targetY: 0,
    visible: false,
  });

  useEffect(() => {
    const el = spotlightRef.current;
    if (!el || !interactiveMotionEnabled) {
      return;
    }

    const st = pointerStateRef.current;
    st.currentX = window.innerWidth * 0.5;
    st.currentY = window.innerHeight * 0.3;
    st.targetX = st.currentX;
    st.targetY = st.currentY;
    st.visible = false;

    const tick = () => {
      const dx = st.targetX - st.currentX;
      const dy = st.targetY - st.currentY;
      st.currentX += dx * 0.14;
      st.currentY += dy * 0.14;

      el.style.setProperty('--spot-x', `${st.currentX.toFixed(1)}px`);
      el.style.setProperty('--spot-y', `${st.currentY.toFixed(1)}px`);
      el.style.opacity = st.visible ? '1' : '0';

      if (Math.abs(dx) > 0.35 || Math.abs(dy) > 0.35) {
        st.rafId = window.requestAnimationFrame(tick);
      } else {
        st.rafId = null;
      }
    };

    const scheduleTick = () => {
      if (st.rafId === null) {
        st.rafId = window.requestAnimationFrame(tick);
      }
    };

    const handleMouseMove = (event: MouseEvent) => {
      st.targetX = event.clientX;
      st.targetY = event.clientY;
      if (!st.visible) {
        st.currentX = st.targetX;
        st.currentY = st.targetY;
        st.visible = true;
      }
      scheduleTick();
    };

    const handleMouseLeave = () => {
      st.visible = false;
      el.style.opacity = '0';
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    document.documentElement.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      document.documentElement.removeEventListener('mouseleave', handleMouseLeave);
      if (st.rafId !== null) {
        window.cancelAnimationFrame(st.rafId);
        st.rafId = null;
      }
    };
  }, [interactiveMotionEnabled]);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {/* Static low-intensity ambient navy / cyan glows visible behind glass panels */}
      <div
        className="absolute -top-44 right-[-10%] h-[34rem] w-[34rem] rounded-full opacity-55 dark:opacity-100"
        style={{
          background: 'radial-gradient(circle, rgba(0, 200, 255, 0.11) 0%, rgba(8, 123, 255, 0.04) 48%, transparent 72%)',
        }}
      />
      <div
        className="absolute bottom-[-14rem] left-[-8%] h-[36rem] w-[36rem] rounded-full opacity-50 dark:opacity-100"
        style={{
          background: 'radial-gradient(circle, rgba(8, 123, 255, 0.10) 0%, rgba(79, 70, 229, 0.04) 46%, transparent 72%)',
        }}
      />

      {/* Pointer-interpolated subtle radial glow (fine pointer + motion allowed only) */}
      {interactiveMotionEnabled && (
        <div
          ref={spotlightRef}
          className="absolute inset-0 transition-opacity duration-300"
          style={{
            opacity: 0,
            background:
              'radial-gradient(540px circle at var(--spot-x, 50%) var(--spot-y, 35%), rgba(0, 200, 255, 0.085), rgba(8, 123, 255, 0.035) 38%, transparent 70%)',
          }}
        />
      )}
    </div>
  );
};
