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
};

// ─── CLI entrypoint ──────────────────────────────────────────────────────────
if (require.main === module) {
  let runner;
  if (process.argv.includes('--bridge')) {
    runner = runViaBridge;          // exec + cookie injection
  } else if (process.argv.includes('--python')) {
    runner = runViaPython;          // spawn, streaming
  } else {
    runner = main;                  // original JS-only flow
  }

  runner().catch((err) => {
    console.error('\nFatal error:', err.message);
    process.exit(1);
  });
}