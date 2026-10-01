/* OPTIONAL INTEGRATION EXAMPLE - not loaded by any demo page.
 * Endpoint names, JSON shape and CSRF policy must match your own backend.
 * Usage: const api = CircuitApi.create({ baseURL: '/api/' });
 */
(function (global) {
  'use strict';

  class ApiError extends Error {
    constructor(message, status, details) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.details = details;
    }
  }

  /**
   * @param {{baseURL?:string, timeoutMs?:number,
   *   getCSRFToken?:(()=>string|null), csrfHeader?:string}} options
   * @returns {{listEmployees:Function,createEmployee:Function,
   *   updateEmployee:Function,deleteEmployee:Function}}
   * Same-origin cookie authentication is intentional. Never put API secrets here.
   */
  function create(options = {}) {
    const {
      baseURL = '/api/',
      timeoutMs = 15000,
      getCSRFToken = () => document.querySelector('meta[name="csrf-token"]')?.content || null,
      csrfHeader = 'X-CSRFToken'
    } = options;
    const base = new URL(baseURL, global.location.href);
    if (!/^https?:$/.test(base.protocol) || base.origin !== global.location.origin) {
      throw new TypeError('Use a same-origin HTTP(S) API base URL. Serve the app over HTTP first.');
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      throw new TypeError('timeoutMs must be a positive number.');
    }
    if (!base.pathname.endsWith('/')) base.pathname += '/';
    base.search = ''; base.hash = '';

    async function request(path, { method = 'GET', body, signal } = {}) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      if (signal?.aborted) abort();
      signal?.addEventListener('abort', abort, { once: true });
      const timer = global.setTimeout(abort, timeoutMs);
      try {
        const headers = { Accept: 'application/json' };
        if (body !== undefined) headers['Content-Type'] = 'application/json';
        if (!['GET', 'HEAD'].includes(method)) {
          const token = getCSRFToken();
          if (token) headers[csrfHeader] = token;
        }
        const response = await fetch(new URL(path, base), {
          method, headers,
          credentials: 'same-origin',
          signal: controller.signal,
          body: body === undefined ? undefined : JSON.stringify(body)
        });
        const text = response.status === 204 ? '' : await response.text();
        let data = null;
        if (text) {
          try { data = JSON.parse(text); }
          catch (_) {
            throw new ApiError('The server returned a non-JSON response.', response.status, null);
          }
        }
        if (!response.ok) {
          throw new ApiError(
            typeof data?.message === 'string' ? data.message : 'Request failed (' + response.status + ').',
            response.status,
            data
          );
        }
        return data;
      } finally {
        global.clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
      }
    }

    function employeePath(id) {
      if (!Number.isSafeInteger(id) || id < 1) throw new TypeError('Employee id must be a positive integer.');
      return 'employees/' + encodeURIComponent(id) + '/';
    }
    return Object.freeze({
      // Contract: GET returns an array. Adapt this method for a paginated API.
      listEmployees: async (options = {}) => {
        const data = await request('employees/', options);
        if (!Array.isArray(data)) throw new ApiError('Expected an employee array.', 200, null);
        return data;
      },
      createEmployee: (values, { signal } = {}) => request('employees/', { method: 'POST', body: values, signal }),
      updateEmployee: (id, values, { signal } = {}) => request(employeePath(id), { method: 'PATCH', body: values, signal }),
      deleteEmployee: (id, { signal } = {}) => request(employeePath(id), { method: 'DELETE', signal })
    });
  }
  global.CircuitApi = Object.freeze({ create, ApiError });
})(window);
