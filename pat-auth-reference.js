'use strict';

/**
 * Private Access Token (PAT) — Challenge-Response Reference Implementation
 *
 * Standards:
 *   - RFC 9576 / RFC 9577  : Privacy Pass Issuance Protocol (Blind RSA)
 *   - draft-ietf-privacypass-auth-scheme : HTTP Authentication Scheme
 *   - RFC 9209              : Proxy-Status header (context only)
 *
 * Flow:
 *   1. Client  → GET /resource               (no token)
 *   2. Server  ← 401  WWW-Authenticate: PrivateToken challenge=…, token-key=…
 *   3. Client  → POST /token  (to issuer)     (TokenRequest blob)
 *   4. Issuer  ← 200  (TokenResponse blob)
 *   5. Client  → GET /resource  Authorization: PrivateToken token=…
 *   6. Server  ← 200  (access granted)
 *
 * Dependencies:
 *   npm install axios axios-cookiejar-support tough-cookie
 */

const axios  = require('axios');
const { wrapper }   = require('axios-cookiejar-support');
const { CookieJar } = require('tough-cookie');

// ---------------------------------------------------------------------------
// Constants (Privacy Pass HTTP Auth draft, §4)
// ---------------------------------------------------------------------------
const TOKEN_TYPE_BLIND_RSA = 0x0002;   // 2-byte big-endian token type
const BLINDED_MSG_LEN      = 512;      // RSA-2048: 256 bytes; RSA-4096: 512 bytes
const CONTENT_TYPE_REQUEST  = 'application/private-token-request';
const CONTENT_TYPE_RESPONSE = 'application/private-token-response';

// ---------------------------------------------------------------------------
// Browser-like headers (mirrors a real Chrome/macOS request)
// ---------------------------------------------------------------------------
const BROWSER_HEADERS = {
  'User-Agent'        : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'sec-ch-ua'         : '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
  'sec-ch-ua-mobile'  : '?0',
  'sec-ch-ua-platform': '"macOS"',
  'Accept'            : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language'   : 'en-US,en;q=0.9',
  'sec-fetch-dest'    : 'document',
  'sec-fetch-mode'    : 'navigate',
  'sec-fetch-site'    : 'none',
};

// ---------------------------------------------------------------------------
// Base64url helpers (RFC 4648 §5 — no padding, URL-safe alphabet)
// ---------------------------------------------------------------------------

/** Decode a base64url string to a Buffer. */
function fromBase64url(str) {
  const base64 = str
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .padEnd(str.length + (4 - (str.length % 4)) % 4, '=');
  return Buffer.from(base64, 'base64');
}

/** Encode a Buffer to a base64url string. */
function toBase64url(buf) {
  return Buffer.from(buf)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g,  '');
}

// ---------------------------------------------------------------------------
// WWW-Authenticate header parser
// ---------------------------------------------------------------------------

/**
 * Parse the value of a WWW-Authenticate header that uses the PrivateToken scheme.
 *
 * Grammar (auth-scheme + auth-params per RFC 9110 §11.3):
 *
 *   WWW-Authenticate: PrivateToken challenge="<b64url>", token-key="<b64url>", max-age=<seconds>
 *
 * Returns an object with lower-cased parameter names as keys.
 * Throws if the scheme is not "PrivateToken".
 */
function parseWWWAuthenticate(headerValue) {
  const SCHEME = 'PrivateToken';

  const trimmed = headerValue.trim();
  if (!trimmed.toLowerCase().startsWith(SCHEME.toLowerCase())) {
    throw new Error(
      `Unsupported auth scheme. Expected "${SCHEME}", got: "${trimmed.slice(0, 20)}…"`
    );
  }

  const paramsPart = trimmed.slice(SCHEME.length).trim();
  const result     = {};

  // Match:  key="quoted value"   OR   key=unquoted-value
  // Handles base64url values that contain '+', '/', '=', '-', '_'
  const TOKEN_PARAM = /([A-Za-z][A-Za-z0-9-]*)=(?:"([^"]*)"|([^,\s]*))/g;
  let match;

  while ((match = TOKEN_PARAM.exec(paramsPart)) !== null) {
    const key   = match[1].toLowerCase();
    const value = match[2] !== undefined ? match[2] : match[3]; // quoted vs bare
    result[key] = value;
  }

  return result;
}

// ---------------------------------------------------------------------------
// TokenRequest serialisation  (Privacy Pass auth draft §5.1)
// ---------------------------------------------------------------------------

/**
 * Build a serialised TokenRequest binary blob.
 *
 * Structure (big-endian):
 *   token_type       : uint16   (2 bytes)
 *   truncated_key_id : uint8    (1 byte  — last byte of SHA-256(token_key))
 *   blinded_msg      : opaque   (BLINDED_MSG_LEN bytes)
 *
 * In a real implementation `blindedMsg` is produced by the RSA-blind step using
 * the public key from `token-key` and a random secret scalar the client stores
 * for later unblinding.  Here we accept the blinded message as a parameter so
 * callers can plug in real crypto (e.g. via the `blindrsa` npm package).
 *
 * @param {number} truncatedKeyId  - Last byte of SHA-256(tokenKeyBytes)
 * @param {Buffer} blindedMsg      - Blinded challenge message (BLINDED_MSG_LEN bytes)
 * @returns {Buffer}
 */
function buildTokenRequest(truncatedKeyId, blindedMsg) {
  if (blindedMsg.length !== BLINDED_MSG_LEN) {
    throw new RangeError(
      `blinded_msg must be exactly ${BLINDED_MSG_LEN} bytes, got ${blindedMsg.length}`
    );
  }

  const buf = Buffer.allocUnsafe(2 + 1 + BLINDED_MSG_LEN);
  buf.writeUInt16BE(TOKEN_TYPE_BLIND_RSA, 0);   // token_type
  buf.writeUInt8(truncatedKeyId,          2);   // truncated_token_key_id
  blindedMsg.copy(buf, 3);                      // blinded_msg
  return buf;
}

/**
 * Reconstruct the issuer URL from challenge parameters.
 *
 * The draft specifies an optional "challenge-platform" field; when absent the
 * issuer URL can be discovered via the token-key's HTTPS resource record or
 * a well-known registry.  This helper implements a simple fallback.
 */
function resolveIssuerUrl(params) {
  if (params['challenge-platform']) return params['challenge-platform'];
  // Fallback: caller provides an explicit issuer base URL
  if (params['_issuer-base-url']) {
    return `${params['_issuer-base-url']}/token`;
  }
  throw new Error(
    'Cannot resolve issuer URL: neither "challenge-platform" nor a fallback base URL was provided.'
  );
}

// ---------------------------------------------------------------------------
// Main handshake
// ---------------------------------------------------------------------------

/**
 * Perform the full PAT challenge-response handshake.
 *
 * @param {string}  targetUrl        - Protected resource URL (step 1 request)
 * @param {string}  issuerBaseUrl    - Base URL of the token issuer  (e.g. "https://token-issuer.example.com")
 * @param {Function} blindFn         - async (tokenKeyBytes: Buffer, challengeBytes: Buffer) => { blindedMsg: Buffer, blindScalar: any }
 * @param {Function} unblindFn       - async (blindedSig: Buffer, blindScalar: any) => Buffer  (final token)
 */
async function performPATHandshake(targetUrl, issuerBaseUrl, blindFn, unblindFn) {

  // Shared cookie jar — persists cookies across all requests in the session
  const jar    = new CookieJar();
  const client = wrapper(axios.create({
    jar,
    withCredentials: true,
    // Do not throw on non-2xx so we can inspect 401 ourselves
    validateStatus: () => true,
  }));

  // ── Step 1: Initial unauthenticated request ────────────────────────────────
  console.log(`[1/4] GET ${targetUrl}`);
  const initialRes = await client.get(targetUrl, { headers: BROWSER_HEADERS });

  console.log(`      Response status: ${initialRes.status}`);

  if (initialRes.status === 200) {
    console.log('      Resource accessible without a token — handshake not required.');
    return { status: 200, data: initialRes.data };
  }

  if (initialRes.status !== 401) {
    throw new Error(`Unexpected status ${initialRes.status} on initial request.`);
  }

  // ── Step 2: Parse the challenge ───────────────────────────────────────────
  const wwwAuth = initialRes.headers['www-authenticate'];
  if (!wwwAuth) {
    throw new Error('Server returned 401 but no WWW-Authenticate header.');
  }

  console.log(`[2/4] Parsing WWW-Authenticate: ${wwwAuth}`);
  const params = parseWWWAuthenticate(wwwAuth);
  console.log('      Parsed parameters:', params);

  const { challenge, 'token-key': tokenKeyB64 } = params;
  if (!challenge)    throw new Error('Missing "challenge" in WWW-Authenticate.');
  if (!tokenKeyB64)  throw new Error('Missing "token-key" in WWW-Authenticate.');

  const challengeBytes  = fromBase64url(challenge);
  const tokenKeyBytes   = fromBase64url(tokenKeyB64);

  console.log(`      challenge  : ${challengeBytes.length} bytes  → ${challengeBytes.slice(0, 8).toString('hex')}…`);
  console.log(`      token-key  : ${tokenKeyBytes.length} bytes  → ${tokenKeyBytes.slice(0, 8).toString('hex')}…`);

  // truncated_token_key_id = last byte of SHA-256(token_key)
  // (stdlib crypto used to avoid an extra dependency)
  const { createHash } = require('crypto');
  const keyDigest       = createHash('sha256').update(tokenKeyBytes).digest();
  const truncatedKeyId  = keyDigest[keyDigest.length - 1];
  console.log(`      truncated_token_key_id: 0x${truncatedKeyId.toString(16).padStart(2, '0')}`);

  // ── Step 3: Blind the challenge and POST to the issuer ────────────────────
  const issuerUrl = resolveIssuerUrl({ ...params, '_issuer-base-url': issuerBaseUrl });
  console.log(`[3/4] POST ${issuerUrl}  (token request)`);

  // Blind step (caller-supplied; see stub below for structure)
  const { blindedMsg, blindScalar } = await blindFn(tokenKeyBytes, challengeBytes);
  const tokenRequestBody = buildTokenRequest(truncatedKeyId, blindedMsg);

  console.log(`      TokenRequest: ${tokenRequestBody.length} bytes`);
  console.log(`        token_type       : 0x${TOKEN_TYPE_BLIND_RSA.toString(16).padStart(4, '0')}`);
  console.log(`        truncated_key_id : 0x${truncatedKeyId.toString(16).padStart(2, '0')}`);
  console.log(`        blinded_msg      : ${blindedMsg.length} bytes  → ${blindedMsg.slice(0, 8).toString('hex')}…`);

  const issuerRes = await client.post(issuerUrl, tokenRequestBody, {
    headers: {
      ...BROWSER_HEADERS,
      'Content-Type': CONTENT_TYPE_REQUEST,
      'Accept'       : CONTENT_TYPE_RESPONSE,
    },
    responseType: 'arraybuffer',
  });

  console.log(`      Issuer response status: ${issuerRes.status}`);
  if (issuerRes.status !== 200) {
    throw new Error(`Issuer returned HTTP ${issuerRes.status} — token issuance failed.`);
  }

  const tokenResponseBytes = Buffer.from(issuerRes.data);
  console.log(`      TokenResponse: ${tokenResponseBytes.length} bytes`);

  // Unblind the signature to obtain the final token
  const token = await unblindFn(tokenResponseBytes, blindScalar);
  console.log(`      Unblinded token: ${token.length} bytes`);

  // ── Step 4: Retry the original request with the Authorization header ───────
  const authHeader = `PrivateToken token=${toBase64url(token)}`;
  console.log(`[4/4] GET ${targetUrl}`);
  console.log(`      Authorization: ${authHeader.slice(0, 60)}…`);

  const authenticatedRes = await client.get(targetUrl, {
    headers: {
      ...BROWSER_HEADERS,
      Authorization: authHeader,
    },
  });

  console.log(`      Final response status: ${authenticatedRes.status}`);
  return { status: authenticatedRes.status, data: authenticatedRes.data };
}

// ---------------------------------------------------------------------------
// Stub crypto functions (replace with real blind-RSA implementation)
// ---------------------------------------------------------------------------
//
// A production implementation would use a library such as:
//   - https://github.com/nicowillis/blindrsa  (npm: blindrsa)
//   - Or a WASM/native binding to BoringSSL's RSA_blind / RSA_unblind
//
// The blinding step must:
//   1. Decode the SubjectPublicKeyInfo (SPKI) from tokenKeyBytes
//   2. Generate a random blinding scalar r
//   3. Compute blinded_msg = (challenge_digest * r^e) mod n   (RSA blinding)
//
// The unblinding step must:
//   1. Compute token = blinded_sig * r^-1 mod n

async function stubBlind(tokenKeyBytes, challengeBytes) {
  // WARNING: NOT real blinding — placeholder for structure illustration only.
  console.log('      [STUB] blind() called — replace with real RSA blind operation');
  const blindedMsg  = Buffer.alloc(BLINDED_MSG_LEN, 0xab); // placeholder
  const blindScalar = Symbol('blind-scalar-placeholder');   // placeholder
  return { blindedMsg, blindScalar };
}

async function stubUnblind(tokenResponseBytes, blindScalar) {
  // WARNING: NOT real unblinding — returns the raw issuer response as-is.
  console.log('      [STUB] unblind() called — replace with real RSA unblind operation');
  return tokenResponseBytes;
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

(async () => {
  try {
    const result = await performPATHandshake(
      'https://example.com/protected-resource',   // ← target URL
      'https://token-issuer.example.com',          // ← issuer base URL
      stubBlind,
      stubUnblind,
    );
    console.log('\nHandshake complete. Final status:', result.status);
  } catch (err) {
    console.error('\nHandshake failed:', err.message);
    process.exit(1);
  }
})();
