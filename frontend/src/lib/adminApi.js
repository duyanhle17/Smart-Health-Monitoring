// Admin calls carry the deployment PIN entered once on the admin console.
// The backend only enforces it when SAFEWORK_ADMIN_PIN is configured.

const PIN_KEY = 'safework_admin_pin';

export const getAdminPin = () => sessionStorage.getItem(PIN_KEY) || '';
export const setAdminPin = (pin) => sessionStorage.setItem(PIN_KEY, pin);
export const clearAdminPin = () => sessionStorage.removeItem(PIN_KEY);

export function adminRequest(url, method, body) {
  return fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Pin': getAdminPin(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const adminPost = (url, body) => adminRequest(url, 'POST', body ?? {});

export async function verifyAdminPin(pin) {
  const res = await fetch('/api/admin/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Pin': pin },
    body: '{}',
  });
  return res.ok;
}
