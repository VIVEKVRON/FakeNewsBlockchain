/**
 * frontend/src/hooks/useTheme.ts
 * Manages dark/light theme state with localStorage persistence.
 * Defaults to 'dark' per design guidelines.
 */

import { useState, useEffect } from 'react';

type Theme = 'dark' | 'light';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('fakenews_theme');
    if (saved === 'light' || saved === 'dark') {
      return saved;
    }
    return 'dark'; // Dark-mode first
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('fakenews_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  return { theme, toggleTheme, isDark: theme === 'dark' };
}
