import { useCallback, useEffect, useState } from 'react';

/** Below this viewport width the admin console shows the map-only view. */
export const MOBILE_MAX_WIDTH = 1024;

export const VIEW_PREF_KEY = 'safework_admin_view';

/**
 * A wide screen always gets the full console — an operator at a desk should
 * never be handed the stripped-down view. A narrow screen gets the map unless
 * the operator explicitly asked for the console, which they need on site for
 * UWB calibration.
 */
export function resolveAdminView(width, preference) {
  if (width >= MOBILE_MAX_WIDTH) return 'full';
  return preference === 'full' ? 'full' : 'map';
}

export const readViewPreference = () => {
  try {
    return localStorage.getItem(VIEW_PREF_KEY);
  } catch {
    return null; // private mode
  }
};

export const writeViewPreference = (value) => {
  try {
    localStorage.setItem(VIEW_PREF_KEY, value);
  } catch {
    /* private mode: the choice simply does not persist */
  }
};

export default function useMobileMapMode() {
  const [width, setWidth] = useState(() =>
    typeof window === 'undefined' ? MOBILE_MAX_WIDTH : window.innerWidth
  );
  const [preference, setPreference] = useState(readViewPreference);

  // The isometric map sizes itself once at mount and registers no resize
  // listener, so rotating a phone leaves its view wrong. Track width properly.
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('orientationchange', onResize);
    };
  }, []);

  const setView = useCallback((value) => {
    writeViewPreference(value);
    setPreference(value);
  }, []);

  return { view: resolveAdminView(width, preference), setView, width };
}
