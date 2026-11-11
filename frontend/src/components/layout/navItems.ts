import type { LucideIcon } from 'lucide-react';
import {
  Home,
  LayoutDashboard,
  ShieldCheck,
  SearchCheck,
  Radio,
  Blocks,
  Info,
} from 'lucide-react';

export interface NavItemConfig {
  to: string;
  label: string;
  shortLabel?: string;
  icon: LucideIcon;
  matchPrefixes: string[];
  exact?: boolean;
}

export const NAV_ITEMS: NavItemConfig[] = [
  {
    to: '/',
    label: 'Home',
    icon: Home,
    matchPrefixes: ['/'],
    exact: true,
  },
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
    matchPrefixes: ['/dashboard'],
  },
  {
    to: '/verify',
    label: 'Verify',
    icon: ShieldCheck,
    matchPrefixes: ['/verify', '/text', '/article', '/image'],
  },
  {
    to: '/evidence',
    label: 'Evidence Explorer',
    shortLabel: 'Evidence',
    icon: SearchCheck,
    matchPrefixes: ['/evidence', '/history'],
  },
  {
    to: '/live',
    label: 'Live News',
    icon: Radio,
    matchPrefixes: ['/live'],
  },
  {
    to: '/blockchain',
    label: 'Blockchain Records',
    shortLabel: 'Blockchain',
    icon: Blocks,
    matchPrefixes: ['/blockchain', '/audit', '/verify-certificate'],
  },
  {
    to: '/about',
    label: 'About',
    icon: Info,
    matchPrefixes: ['/about'],
  },
];

export function isNavItemActive(pathname: string, item: NavItemConfig): boolean {
  if (item.exact) {
    return pathname === item.to;
  }
  return item.matchPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
