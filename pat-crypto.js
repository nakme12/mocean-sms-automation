'use strict';

/**
 * pat-crypto.js — Privacy Pass PAT Cryptographic Utilities
 *
 * Implements the blind-RSA operations required by:
 *   RFC 9474  — RSA Blind Signatures (RSABSSA)
 *   RFC 9576  — Privacy Pass Issuance Protocol (Type 0x0002)
 *   draft-ietf-privacypass-auth-scheme — HTTP Authorization Scheme
 *
 * Algorithm variant: RSABSSA-SHA384-PSS-Randomized
 *   - SHA-384 hash
 *   - PSS padding with random salt (saltLen = hLen = 48)
 *   - Blinding via random invertible scalar r mod n
 *
 * No third-party dependencies — uses Node.js built-in `crypto` only.
 * Node.js >= 18 required (for crypto.subtle RSA-PSS support).
 *
 * SECURITY NOTE:
 *   BigInt arithmetic used here is NOT constant-time and is NOT suitable
 *   for production issuer-side signing.  It is correct for the CLIENT-SIDE
 *   blind / unblind operations where the blinding scalar is locally generated.
 *   For a production issuer, use OpenSSL bindings or a vetted C extension.
 */

const crypto = require('crypto');

// ─── Token type constant (RFC 9576 §6) ───────────────────────────────────────
const TOKEN_TYPE_BLIND_RSA = 0x0002;

// ─── Base64url (RFC 4648 §5) ─────────────────────────────────────────────────

function toBase64url(buf) {
  return Buffer.from(buf)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g,  '');
}

function fromBase64url(str) {
  const padded = str
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .padEnd(str.length + (4 - (str.length % 4)) % 4, '=');
  return Buffer.from(padded, 'base64');
}

// ─── BigInt helpers ───────────────────────────────────────────────────────────

/** Convert a Buffer of big-endian bytes to a BigInt. */
function bufToBigInt(buf) {
  return BigInt('0x' + buf.toString('hex'));
}

/** Convert a BigInt to a fixed-width big-endian Buffer. */
function bigIntToBuf(n, byteLength) {
  let hex = n.toString(16);
  if (hex.length % 2 !== 0) hex = '0' + hex;
  const buf = Buffer.from(hex, 'hex');
  if (buf.length === byteLength) return buf;
  if (buf.length > byteLength) throw new RangeError('BigInt too large for target buffer');
  // Left-pad with zeros
  return Buffer.concat([Buffer.alloc(byteLength - buf.length), buf]);
}

/**
 * Modular exponentiation: base^exp mod mod
 * Uses square-and-multiply.  Not constant-time (see module note).
 */
function modPow(base, exp, mod) {
  if (mod === 1n) return 0n;
  let result = 1n;
  base = base % mod;
  while (exp > 0n) {
    if (exp % 2n === 1n) result = (result * base) % mod;
    exp = exp / 2n;
    base = (base * base) % mod;
  }
  return result;
}

/**
 * Modular inverse via extended Euclidean algorithm.
 * Returns x such that (a * x) ≡ 1 (mod m).
 * Throws if a and m are not coprime.
 */
function modInverse(a, m) {
  let [old_r, r]   = [a, m];
  let [old_s, s]   = [1n, 0n];

  while (r !== 0n) {
    const q          = old_r / r;
    [old_r, r]       = [r, old_r - q * r];
    [old_s, s]       = [s, old_s - q * s];
  }

  if (old_r !== 1n) throw new Error('Inputs are not coprime — modular inverse does not exist.');
  return ((old_s % m) + m) % m;
}

// ─── RSA public-key parsing ───────────────────────────────────────────────────

/**
 * Extract (n, e, modulusBytes) from a DER-encoded SubjectPublicKeyInfo buffer.
 *
 * The `token-key` field in a PAT WWW-Authenticate header is a base64url-encoded
 * SPKI blob.  Node's KeyObject lets us export it as JWK to read n and e cleanly.
 *
 * @param {Buffer} spkiBytes  Raw DER bytes from fromBase64url(params['token-key'])
 * @returns {{ n: BigInt, e: BigInt, modulusLen: number }}
 */
function parsePublicKey(spkiBytes) {
  const keyObj = crypto.createPublicKey({ key: spkiBytes, format: 'der', type: 'spki' });
  const jwk    = keyObj.export({ format: 'jwk' });

  const n          = bufToBigInt(fromBase64url(jwk.n));
  const e          = bufToBigInt(fromBase64url(jwk.e));
  const modulusLen = Math.ceil(n.toString(16).length / 2); // byte length of modulus

  return { n, e, modulusLen };
}

// ─── RSA-PSS message preparation ─────────────────────────────────────────────

/**
 * Encode a message with EMSA-PSS padding (RFC 8017 §9.1.1).
 *
 * Parameters fixed per RSABSSA-SHA384-PSS-Randomized (RFC 9474 §4):
 *   Hash   = SHA-384   (hLen = 48)
 *   MGF    = MGF1-SHA384
 *   sLen   = 48        (random salt, same length as hash)
 *   emBits = 8 * modulusLen - 1
 *
 * @param {Buffer} message       Raw message bytes (the token challenge digest)
 * @param {number} modulusLen    RSA modulus length in bytes
 * @returns {Buffer}             EM: the PSS-encoded message, length = modulusLen
 */
async function emsaPSSEncode(message, modulusLen) {
  const hLen   = 48;           // SHA-384 output bytes
  const sLen   = 48;           // salt length (== hLen for this variant)
  const emLen  = modulusLen;
  const emBits = 8 * emLen - 1;

  if (emLen < hLen + sLen + 2) throw new Error('Encoding parameters too large for modulus.');

  // 1. mHash = Hash(message)
  const mHash  = crypto.createHash('sha384').update(message).digest();

  // 2. Generate random salt
  const salt   = crypto.randomBytes(sLen);

  // 3. M' = (0x)00 00 00 00 00 00 00 00 || mHash || salt
  const mPrime = Buffer.concat([Buffer.alloc(8), mHash, salt]);

  // 4. H = Hash(M')
  const H      = crypto.createHash('sha384').update(mPrime).digest();

  // 5. PS = zero string of length emLen - sLen - hLen - 2
  const psLen  = emLen - sLen - hLen - 2;
  const DB     = Buffer.concat([Buffer.alloc(psLen), Buffer.from([0x01]), salt]);  // DB

  // 6. dbMask = MGF(H, emLen - hLen - 1)
  const dbMask = mgf1SHA384(H, emLen - hLen - 1);

  // 7. maskedDB = DB XOR dbMask  (top bits zeroed per emBits)
  const maskedDB = Buffer.alloc(DB.length);
  for (let i = 0; i < DB.length; i++) maskedDB[i] = DB[i] ^ dbMask[i];

  // Zero the leftmost (8 * emLen - emBits) bits of maskedDB[0]
  const topBitsToZero = 8 * emLen - emBits;   // = 1 for our parameters
  maskedDB[0] &= (0xff >>> topBitsToZero);

  // 8. EM = maskedDB || H || 0xbc
  return Buffer.concat([maskedDB, H, Buffer.from([0xbc])]);
}

/**
 * MGF1 mask generation function with SHA-384 (RFC 8017 Appendix B.2.1).
 *
 * @param {Buffer} seed
 * @param {number} maskLen   Desired output length in bytes
 * @returns {Buffer}
 */
function mgf1SHA384(seed, maskLen) {
  const hLen   = 48;
  const chunks = Math.ceil(maskLen / hLen);
  const parts  = [];

  for (let c = 0; c < chunks; c++) {
    const counter = Buffer.alloc(4);
    counter.writeUInt32BE(c, 0);
    parts.push(crypto.createHash('sha384').update(seed).update(counter).digest());
  }

  return Buffer.concat(parts).slice(0, maskLen);
}

// ─── Blind / Unblind ─────────────────────────────────────────────────────────

/**
 * Blind a PSS-encoded message for submission to the issuer.
 *
 * RFC 9474 §4.2 — Blind:
 *   1. Encode the message with EMSA-PSS → m
 *   2. Pick random r ∈ [2, n-1] with gcd(r, n) = 1
 *   3. x = r^e mod n
 *   4. m_blind = (m_int * x) mod n
 *
 * @param {Buffer} message         The challenge message bytes
 * @param {Buffer} tokenKeyBytes   DER-encoded SPKI public key from the PAT header
 * @returns {{ blindedMsg: Buffer, blindInverse: BigInt, n: BigInt }}
 */
async function blind(message, tokenKeyBytes) {
  const { n, e, modulusLen } = parsePublicKey(tokenKeyBytes);

  // PSS-encode the message
  const em     = await emsaPSSEncode(message, modulusLen);
  const m      = bufToBigInt(em);

  // Generate a random blinding scalar r with gcd(r, n) = 1
  // Rejection-sample: probability of gcd != 1 is negligible for large n
  let r, rInv;
  for (;;) {
    const rBytes = crypto.randomBytes(modulusLen);
    r = bufToBigInt(rBytes) % n;
    if (r < 2n) continue;
    try {
      rInv = modInverse(r, n);
      break;
    } catch {
      // Not coprime — resample (extremely rare)
    }
  }

  // blinded_msg = m * r^e mod n
  const x          = modPow(r, e, n);
  const blindedInt = (m * x) % n;
  const blindedMsg = bigIntToBuf(blindedInt, modulusLen);

  return { blindedMsg, blindInverse: rInv, n };
}

/**
 * Unblind a blind signature received from the issuer.
 *
 * RFC 9474 §4.4 — Finalize:
 *   token = blind_sig * r^-1 mod n
 *
 * @param {Buffer} blindSigBytes   Raw bytes from the issuer's TokenResponse
 * @param {BigInt} blindInverse    r^-1 mod n from the blind() call
 * @param {BigInt} n               RSA modulus
 * @param {number} modulusLen      Byte length of the modulus
 * @returns {Buffer}               The final unblinded token bytes
 */
function unblind(blindSigBytes, blindInverse, n, modulusLen) {
  const z     = bufToBigInt(blindSigBytes);
  const token = (z * blindInverse) % n;
  return bigIntToBuf(token, modulusLen);
}

// ─── TokenRequest serialisation (RFC 9576 §6.1) ──────────────────────────────

/**
 * Build the binary TokenRequest blob.
 *
 * Wire format:
 *   token_type          uint16   2 bytes  (big-endian, always 0x0002)
 *   truncated_token_key_id  uint8    1 byte   (last byte of SHA-256(SPKI))
 *   blinded_msg         opaque   N bytes  (N = RSA modulus length)
 *
 * @param {Buffer} tokenKeyBytes  DER SPKI bytes of the issuer public key
 * @param {Buffer} blindedMsg     Output of blind()
 * @returns {Buffer}
 */
function buildTokenRequest(tokenKeyBytes, blindedMsg) {
  const keyDigest      = crypto.createHash('sha256').update(tokenKeyBytes).digest();
  const truncatedKeyId = keyDigest[keyDigest.length - 1];

  const buf = Buffer.allocUnsafe(2 + 1 + blindedMsg.length);
  buf.writeUInt16BE(TOKEN_TYPE_BLIND_RSA, 0);
  buf.writeUInt8(truncatedKeyId,          2);
  blindedMsg.copy(buf, 3);

  return buf;
}

/**
 * Serialize a TokenRequest to a base64url string for use in HTTP headers
 * or logging.
 *
 * @param {Buffer} tokenRequest  Output of buildTokenRequest()
 * @returns {string}
 */
function serializeTokenRequest(tokenRequest) {
  return toBase64url(tokenRequest);
}

// ─── TokenResponse parsing (RFC 9576 §6.2) ───────────────────────────────────

/**
 * Parse the raw TokenResponse body from the issuer.
 *
 * Wire format:
 *   blind_sig   opaque   N bytes  (N = RSA modulus length, inferred from body length)
 *
 * Returns the blind signature bytes ready to pass to unblind().
 *
 * @param {Buffer} responseBytes  Raw response body (arraybuffer)
 * @returns {Buffer}
 */
function parseTokenResponse(responseBytes) {
  // The response body IS the blind_sig — no framing fields at this layer.
  // Validate length is a plausible RSA modulus size (256 or 512 bytes).
  const len = responseBytes.length;
  if (len !== 256 && len !== 512) {
    throw new RangeError(
      `Unexpected TokenResponse length ${len}: expected 256 (RSA-2048) or 512 (RSA-4096).`
    );
  }
  return Buffer.from(responseBytes);
}

// ─── Authorization header construction ───────────────────────────────────────

/**
 * Encode the final unblinded token into the Authorization header value.
 *
 * Format per draft-ietf-privacypass-auth-scheme §4:
 *   Authorization: PrivateToken token=<base64url>
 *
 * @param {Buffer} tokenBytes  Output of unblind()
 * @returns {string}           Full Authorization header value
 */
function buildAuthorizationHeader(tokenBytes) {
  return `PrivateToken token=${toBase64url(tokenBytes)}`;
}

// ─── End-to-end helper ───────────────────────────────────────────────────────

/**
 * Full client-side PAT crypto flow.
 *
 * Given the parsed PAT challenge parameters, performs blind → request → unblind
 * and returns everything needed for the Authorization header.
 *
 * @param {object} params          Parsed WWW-Authenticate parameters
 * @param {string} params.challenge   base64url-encoded challenge blob
 * @param {string} params['token-key'] base64url-encoded SPKI public key
 * @param {Function} issuerFetch   async (tokenRequest: Buffer) => Buffer
 *                                 Caller supplies the actual HTTP POST to the issuer.
 * @returns {Promise<string>}      Authorization header value
 */
async function performBlindRSAFlow(params, issuerFetch) {
  const challengeBytes  = fromBase64url(params['challenge']);
  const tokenKeyBytes   = fromBase64url(params['token-key']);

  // Derive the public key info (used for modulus length in unblind)
  const { n, modulusLen } = parsePublicKey(tokenKeyBytes);

  // 1. Blind
  const { blindedMsg, blindInverse } = await blind(challengeBytes, tokenKeyBytes);

  // 2. Serialize into a TokenRequest and send to issuer
  const tokenRequest   = buildTokenRequest(tokenKeyBytes, blindedMsg);
  const responseBytes  = await issuerFetch(tokenRequest);

  // 3. Parse issuer response
  const blindSigBytes  = parseTokenResponse(responseBytes);

  // 4. Unblind → final token
  const tokenBytes     = unblind(blindSigBytes, blindInverse, n, modulusLen);

  // 5. Build Authorization header
  return buildAuthorizationHeader(tokenBytes);
}

// ─── Exports ─────────────────────────────────────────────────────────────────

module.exports = {
  // Core operations
  blind,
  unblind,
  emsaPSSEncode,
  mgf1SHA384,

  // Request / response framing
  buildTokenRequest,
  serializeTokenRequest,
  parseTokenResponse,
  buildAuthorizationHeader,

  // Key parsing
  parsePublicKey,

  // Convenience
  performBlindRSAFlow,

  // Base64url
  toBase64url,
  fromBase64url,

  // Constants
  TOKEN_TYPE_BLIND_RSA,
};
