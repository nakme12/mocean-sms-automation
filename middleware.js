'use strict';

/**
 * middleware.js — Generic PrivateToken 401 Interceptor
 *
 * Implements an axios response interceptor that detects 401 Unauthorized responses
 * with a 'WWW-Authenticate: PrivateToken' challenge, delegates cryptographic
 * handling to a caller-supplied function, and automatically retries the original
 * request with the resulting Authorization header.
 *
 * Suitable for any HTTP service issuing RFC 9576-compatible PrivateToken challenges.
 */

const axios = require('axios');
const { wrapper } = require('axios-cookiejar-support');
const { CookieJar } = require('tough-cookie');

// ─── WWW-Authenticate Parser ──────────────────────────────────────────────────

/**
 * Parse the 'www-authenticate' header value and extract PrivateToken parameters.
 *
 * Grammar (RFC 9110 §11.3):
 *   WWW-Authenticate = auth-scheme [ 1*SP ( token68 / #auth-param ) ]
 *   auth-param = token "=" ( token / quoted-string )
 *
 * For PrivateToken:
 *   WWW-Authenticate: PrivateToken challenge="...", token-key="..."
 *
 * @param {string} headerValue    Raw value of 'www-authenticate' header
 * @returns {object|null}         { challenge, 'token-key', ... } or null if not PrivateToken
 */
function parseWWWAuthenticate(headerValue) {
  if (!headerValue) return null;

  const trimmed = headerValue.trim();
  const schemeMatch = trimmed.match(/^(\S+)\s+(.*)$/);
  if (!schemeMatch) return null;

  const [, scheme, paramsPart] = schemeMatch;
  if (scheme.toLowerCase() !== 'privatetoken') return null;

  const params = {};
  const paramRegex = /([a-zA-Z][a-zA-Z0-9-]*)\s*=\s*(?:"([^"]*)"|([^,\s]+))/g;
  let match;

  while ((match = paramRegex.exec(paramsPart)) !== null) {
    const key = match[1].toLowerCase();
    const value = match[2] !== undefined ? match[2] : match[3];
    params[key] = value;
  }

  return Object.keys(params).length > 0 ? params : null;
}

// ─── Placeholder for Caller's Cryptographic Handler ──────────────────────────

/**
 * Placeholder function for handling the PrivateToken challenge round-trip.
 *
 * The caller MUST provide their own implementation via setProtocolHandler().
 * This function will be called with the parsed challenge parameters and should
 * return an Authorization header value (string) suitable for the retry request.
 *
 * Expected signature:
 *   async (challengeParams: object) => string
 *
 * Where:
 *   - challengeParams has keys like 'challenge', 'token-key', 'max-age', etc.
 *   - return value is a complete Authorization header, e.g.:
 *     "PrivateToken token=<base64url>"
 *
 * Typically this function will:
 *   1. POST to an issuer endpoint with a TokenRequest
 *   2. Receive a TokenResponse
 *   3. Unblind / process the response
 *   4. Return the formatted Authorization header
 */
let _protocolHandler = async (params) => {
  throw new Error(
    'No protocol handler configured. Call setProtocolHandler() first.\n' +
    'Handler must be: async (params: object) => string'
  );
};

/**
 * Register the caller's cryptographic handler function.
 *
 * @param {Function} handler  async (challengeParams) => authHeaderString
 */
function setProtocolHandler(handler) {
  if (typeof handler !== 'function') {
    throw new TypeError('Handler must be a function');
  }
  _protocolHandler = handler;
}

// ─── Interceptor Setup ─────────────────────────────────────────────────────────

/**
 * Create an axios instance with PrivateToken 401 interceptor and session management.
 *
 * The instance automatically:
 *   - Detects 401 responses with 'WWW-Authenticate: PrivateToken'
 *   - Calls the registered protocol handler to obtain an Authorization header
 *   - Retries the original request with that header
 *   - Persists cookies via tough-cookie across all requests
 *
 * @param {object} options              Optional configuration
 * @param {CookieJar} options.jar       Custom cookie jar (default: new CookieJar())
 * @param {object} options.axiosConfig  Additional axios instance config
 * @returns {AxiosInstance}             Configured axios instance
 */
function createPrivateTokenClient(options = {}) {
  const jar = options.jar || new CookieJar();

  // Wrap axios with cookiejar support
  const client = wrapper(
    axios.create({
      jar,
      withCredentials: true,
      validateStatus: () => true,  // Don't throw on any status — we handle 401 manually
      ...options.axiosConfig,
    })
  );

  // ── Response Interceptor ──────────────────────────────────────────────────────
  //
  // Detects 401 with PrivateToken and automatically performs the handshake.
  // If the handshake succeeds, retries the original request.
  //
  client.interceptors.response.use(
    async (response) => {
      // Non-401 responses pass through unchanged
      if (response.status !== 401) {
        return response;
      }

      const wwwAuth = response.headers['www-authenticate'];
      const params = parseWWWAuthenticate(wwwAuth);

      // Not a PrivateToken challenge — return the 401 as-is
      if (!params) {
        return response;
      }

      // PrivateToken challenge detected. Delegate to the protocol handler.
      console.log('[PrivateToken] 401 challenge detected. Initiating handshake.');
      console.log('[PrivateToken] Challenge parameters:', Object.keys(params));

      let authHeader;
      try {
        authHeader = await _protocolHandler(params);
      } catch (err) {
        console.error('[PrivateToken] Handshake failed:', err.message);
        return response;  // Return the original 401 if handshake fails
      }

      if (!authHeader) {
        console.warn('[PrivateToken] Handler returned empty Authorization header.');
        return response;
      }

      // Reconstruct the original request with the Authorization header
      const originalRequest = response.config;
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = authHeader;

      console.log('[PrivateToken] Retrying original request with Authorization header.');

      try {
        // Retry the request. This will go through the interceptors again,
        // so if it's another 401 we'll detect it and handle accordingly
        // (or bail if max-retry is exceeded).
        const retryResponse = await client.request(originalRequest);
        console.log('[PrivateToken] Retry succeeded. Status:', retryResponse.status);
        return retryResponse;
      } catch (err) {
        console.error('[PrivateToken] Retry request failed:', err.message);
        // Return the original 401 response if retry fails
        return response;
      }
    },
    (error) => {
      // Error in response (e.g., network error) — pass through
      return Promise.reject(error);
    }
  );

  return client;
}

// ─── Convenience exports ───────────────────────────────────────────────────────

module.exports = {
  createPrivateTokenClient,
  setProtocolHandler,
  parseWWWAuthenticate,
};
