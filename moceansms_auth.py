#!/usr/bin/env python3
"""
MoceanSMS Account Registration Automation with Anti-Captcha
Implements Next.js Server Action wire format for form submission.
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

# ============================================================================
# IMPORT ERROR HANDLING
# ============================================================================
try:
    from curl_cffi import requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run:", file=sys.stderr)
    print("  /Library/Developer/CommandLineTools/usr/bin/python3 -m pip install curl-cffi", file=sys.stderr)
    sys.exit(1)

try:
    from anticaptchaofficial.turnstileproxyless import turnstileProxyless
except ImportError:
    print("ERROR: anticaptchaofficial not installed. Run:", file=sys.stderr)
    print("  /Library/Developer/CommandLineTools/usr/bin/python3 -m pip install anticaptchaofficial", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# .env LOADING
# ============================================================================
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        return
    except ImportError:
        pass
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        os.environ.setdefault(k, v)

_load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
API_KEY      = os.environ.get("ANTICAPTCHA_KEY", "YOUR_ANTICAPTCHA_KEY")
SITEKEY      = os.environ.get("SITE_KEY", "0x4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
TARGET_URI   = os.environ.get("TARGET_URI", "https://marketing.moceansms.com/signup")
MAX_RETRIES  = int(os.environ.get("MAX_RETRIES", "1"))

DEFAULT_FULLNAME    = os.environ.get("MOCEAN_FULLNAME", "Pratik Kumar")
DEFAULT_EMAIL       = os.environ.get("MOCEAN_EMAIL", "nakmeis.iliya12@gmail.com")
DEFAULT_MOBILE      = os.environ.get("MOCEAN_MOBILE", "60133251752")
DEFAULT_USERNAME    = os.environ.get("MOCEAN_USERNAME", "Pratik_User")
DEFAULT_PASSWORD    = os.environ.get("MOCEAN_PASSWORD", "Mmmmmm@12345")

# Proxy configuration
PROXY_URL           = os.environ.get("PROXY_URL", None)  # e.g., http://proxy.com:8080 or socks5://proxy.com:1080

# Geonix residential proxy pool (12 proxies with authentication)
PROXY_POOL = [
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10000",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10001",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10002",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10003",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10004",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10005",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10006",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10007",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10008",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10009",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10010",
    "http://d92790ff4b1705b1:Xg8SOTh9rolReN5E@res.geonix.com:10011",
]

# Default headers for initial page fetch
FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
}

# Next.js Server Action wire format headers
SIGNUP_HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/x-component",
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": "https://marketing.moceansms.com",
    "Referer": "https://marketing.moceansms.com/signup",
}

# Fixed next-router-state-tree (same for all requests to this page)
NEXT_ROUTER_STATE_TREE = "%5B%22%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22signup%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"

# Default next-action ID (fallback when extraction fails)
# Updated to current valid ID from recent successful requests
DEFAULT_NEXT_ACTION = "40e92530aa479fd9a04b80dde42c66010d18f4ff51"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def extract_next_action(html: str) -> Optional[str]:
    """
    Extract the next-action ID from Next.js flight data.

    The ID is embedded in self.__next_f.push script blocks. Look for 40-character
    hex strings in the flight data. The action ID is typically a 40-char hex value.
    """
    # Strategy 1: Search for hex IDs directly (broad search)
    hex_pattern = r'\b([a-f0-9]{40})\b'
    all_hex_matches = re.findall(hex_pattern, html)

    if all_hex_matches:
        # Filter out null hashes and common non-action IDs
        for hex_id in all_hex_matches:
            if hex_id != "0" * 40 and hex_id != "1" * 40:
                # Prefer IDs that appear near flight data or signup context
                context_start = max(0, html.find(hex_id) - 100)
                context_end = min(len(html), html.find(hex_id) + 100)
                context = html[context_start:context_end].lower()

                # Check if this looks like an action ID (appears in flight data)
                if 'next_f' in context or 'action' in context or 'signup' in context:
                    logger.info("[+] Extracted next-action ID from context: %s", hex_id)
                    return hex_id

    # Strategy 2: Look specifically in flight data blocks
    script_pattern = r'self\.__next_f\.push\(\[(\d+)?[,\]]["\']([^"\']{1,500})["\']'
    matches = re.findall(script_pattern, html)
    if matches:
        for match in matches:
            hex_matches = re.findall(r'([a-f0-9]{40})', str(match))
            for hex_id in hex_matches:
                if hex_id and hex_id != "0" * 40:
                    logger.info("[+] Extracted next-action ID from flight data: %s", hex_id)
                    return hex_id

    # Strategy 3: Look for ID in common Next.js patterns
    fallback_patterns = [
        # Direct hex in signup context
        r'(auth)["\']?[,\s]*(signup)["\']?[^}]*?([a-f0-9]{40})',
        # Chunk references
        r'static/chunks/app/\(auth\)/signup/page[^,]*?([a-f0-9]{40})',
        # Action pattern
        r'"action"\s*[=:]\s*["\']([a-f0-9]{40})["\']',
    ]

    for pattern in fallback_patterns:
        matches = re.findall(pattern, html)
        if matches:
            for match in matches:
                # Extract the hex if it's part of a tuple
                hex_id = match[-1] if isinstance(match, tuple) else match
                if hex_id and len(hex_id) == 40 and hex_id != "0" * 40:
                    logger.info("[+] Extracted next-action ID using pattern: %s", hex_id)
                    return hex_id

    logger.warning("[-] Could not extract next-action ID from Next.js flight data, will use fallback")
    return None


# ============================================================================
# MAIN CLASS
# ============================================================================
class MoceanSMSAuthAutomated:
    def __init__(self, api_key: str, target_url: str, sitekey: str, proxy_url: Optional[str] = None, reuse_token: Optional[str] = None):
        self.api_key = api_key
        self.target_url = target_url
        self.sitekey = sitekey
        self.turnstile_token: Optional[str] = reuse_token  # Start with provided token if any
        self.next_action: Optional[str] = None

        # Initialize session with proxy if provided
        self.session = requests.Session(impersonate="chrome110")

        # Determine which proxy to use
        if proxy_url and proxy_url.lower() in ("none", "disable", ""):
            # Explicitly disabled proxy
            logger.info("[*] No proxy configured - using direct connection")
        elif proxy_url:
            # Use provided proxy
            selected_proxy = proxy_url
            logger.info("[*] Using provided proxy: %s", proxy_url)
            # Configure proxies for session
            self.session.proxies = {
                "http": selected_proxy,
                "https": selected_proxy,
            }
            logger.info("[+] Proxy configured successfully: %s", selected_proxy)
        else:
            # No proxy specified - randomly select from proxy pool for rotation
            selected_proxy = random.choice(PROXY_POOL)
            logger.info("[*] Selected random proxy from pool")
            # Configure proxies for session
            self.session.proxies = {
                "http": selected_proxy,
                "https": selected_proxy,
            }
            logger.info("[+] Proxy configured successfully: %s", selected_proxy)

    # ------------------------------------------------------------------
    # Step 1: GET signup page to capture session and next-action
    # ------------------------------------------------------------------
    def fetch_signup_page(self) -> Optional[Dict[str, Any]]:
        """Fetch signup page to capture session and extract next-action ID"""
        try:
            logger.info("[*] Fetching signup page...")
            response = self.session.get(
                self.target_url,
                headers=FETCH_HEADERS,
                timeout=30,
                allow_redirects=True,
            )
            logger.info("[+] Page fetched. Status: %s", response.status_code)

            # Extract sitekey if not already known
            sitekey_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', response.text)
            if sitekey_match:
                detected = sitekey_match.group(1)
                if detected != self.sitekey:
                    logger.info("[+] Updated sitekey from HTML: %s", detected)
                    self.sitekey = detected

            # Extract next-action ID (use fallback if extraction fails)
            self.next_action = extract_next_action(response.text)
            if not self.next_action:
                self.next_action = DEFAULT_NEXT_ACTION
                logger.info("[*] Using default next-action ID: %s", self.next_action)

            return {
                "status": response.status_code,
                "html": response.text,
                "next_action": self.next_action,
            }
        except Exception as e:
            logger.error("[-] Failed to fetch signup page: %s", e)
            return None

    # ------------------------------------------------------------------
    # Step 2: Solve Turnstile via Anti-Captcha
    # ------------------------------------------------------------------
    def solve_turnstile_anticaptcha(self, skip_if_existing: bool = True) -> Optional[str]:
        """Solve Turnstile challenge using Anti-Captcha API"""
        # If token is already available and skip_if_existing is True, reuse it
        if self.turnstile_token and skip_if_existing:
            logger.info("[+] Reusing existing Turnstile token (saves Anti-Captcha cost)")
            return self.turnstile_token

        try:
            logger.info("[*] Initializing Anti-Captcha solver...")
            solver = turnstileProxyless()
            solver.set_verbose(0)
            solver.set_key(self.api_key)
            solver.set_website_url(self.target_url)
            solver.set_website_key(self.sitekey)

            logger.info("[*] Submitting Turnstile to Anti-Captcha API...")
            g_response = solver.solve_and_return_solution()

            if g_response:
                logger.info("[+] Turnstile solved successfully (len=%d)", len(g_response))
                return g_response

            logger.error(
                "[-] Anti-Captcha error: code=%s desc=%s",
                getattr(solver, "error_code", "?"),
                getattr(solver, "error_description", "?"),
            )
            return None
        except Exception as e:
            logger.error("[-] Anti-Captcha exception: %s", e)
            return None

    # ------------------------------------------------------------------
    # Step 3: Submit signup form using Next.js Server Action wire format
    # ------------------------------------------------------------------
    def submit_signup_form(
        self,
        name: str,
        email: str,
        mobile: str,
        username: str,
        password: str,
    ) -> Optional[Dict[str, Any]]:
        """
        POST signup form using Next.js Server Action wire format.

        Wire format:
        - Content-Type: text/plain;charset=UTF-8
        - Body: JSON array as raw string
        - Headers: next-action, next-router-state-tree, etc.
        """
        if not self.turnstile_token:
            logger.error("[-] Turnstile token missing")
            return None

        if not self.next_action:
            logger.error("[-] next-action ID missing - cannot proceed")
            return None

        # Clean mobile number
        mobile_clean = mobile.strip()
        if not mobile_clean.startswith('+') and not mobile_clean.startswith('0'):
            mobile_clean = '+' + mobile_clean

        # Build payload as dictionary
        payload_dict = {
            "name": name,
            "username": username,
            "email": email,
            "mobile": mobile_clean,
            "password": password,
            "confirmPassword": password,
            "captchaToken": self.turnstile_token,
            "agreeLicense": True,
            "receiveOffer": False,
        }

        # Format payload as JSON array string (Next.js wire format)
        # The body should be a JSON array containing the form data
        payload_body = json.dumps([payload_dict])

        # Build headers for Next.js Server Action
        headers = SIGNUP_HEADERS_BASE.copy()
        headers["Next-Action"] = self.next_action
        headers["Next-Router-State-Tree"] = NEXT_ROUTER_STATE_TREE

        try:
            logger.info("[*] Submitting signup form (Next.js Server Action format)...")
            logger.info("[*] Email: %s | Username: %s | Mobile: %s", email, username, mobile_clean)
            logger.info("[*] Using next-action: %s", self.next_action)

            # ============================================================
            # LOG EXACT REQUEST BEING SENT
            # ============================================================
            sys.stderr.write("\n" + "="*70 + "\n")
            sys.stderr.write("[REQUEST DEBUG] EXACT REQUEST BEING SENT:\n")
            sys.stderr.write("="*70 + "\n")
            sys.stderr.write(f"Method: POST\n")
            sys.stderr.write(f"URL: {self.target_url}\n")
            sys.stderr.write(f"\nRequest Headers:\n")
            for k, v in headers.items():
                if len(v) > 80:
                    sys.stderr.write(f"  {k}: {v[:80]}...\n")
                else:
                    sys.stderr.write(f"  {k}: {v}\n")
            sys.stderr.write(f"\nRequest Body (raw):\n{payload_body}\n")
            sys.stderr.write(f"\nRequest Body (length): {len(payload_body)} bytes\n")
            sys.stderr.write("="*70 + "\n\n")
            sys.stderr.flush()

            response = self.session.post(
                self.target_url,
                data=payload_body,
                headers=headers,
                timeout=60,  # Increased for slow proxy connections
                allow_redirects=True,
            )

            logger.info("[*] Form submission response status: %s", response.status_code)

            # ============================================================
            # LOG EXACT RESPONSE RECEIVED
            # ============================================================
            sys.stderr.write("\n" + "="*70 + "\n")
            sys.stderr.write("[RESPONSE DEBUG] EXACT RESPONSE RECEIVED:\n")
            sys.stderr.write("="*70 + "\n")
            sys.stderr.write(f"Status Code: {response.status_code}\n")
            sys.stderr.write(f"URL: {response.url}\n")
            sys.stderr.write(f"Content-Type: {response.headers.get('content-type', 'N/A')}\n")
            sys.stderr.write(f"\nResponse Headers:\n")
            for header_name, header_value in response.headers.items():
                sys.stderr.write(f"  {header_name}: {header_value[:150]}\n")
            sys.stderr.write(f"\nResponse Body (FULL - {len(response.text)} chars):\n")
            sys.stderr.write(response.text[:2000])  # Log first 2000 chars
            if len(response.text) > 2000:
                sys.stderr.write(f"\n... (truncated, total {len(response.text)} chars) ...\n")
            sys.stderr.write("\n" + "="*70 + "\n\n")
            sys.stderr.flush()

            # ============================================================
            # EXTRACT AND LOG SUCCESS/ERROR MESSAGES FROM RESPONSE
            # ============================================================
            # Look for JSON success/message in RSC flight data
            import json as json_module
            sys.stderr.write("[RESPONSE ANALYSIS] Extracting success/error messages:\n")
            sys.stderr.write("="*70 + "\n")

            # Find JSON objects in response
            json_pattern = r'\{"success"[^}]*"message":"[^"]*"[^}]*\}'
            json_matches = re.findall(json_pattern, response.text)
            if json_matches:
                sys.stderr.write(f"[+] Found {len(json_matches)} JSON response object(s):\n")
                for i, match in enumerate(json_matches[:3], 1):
                    sys.stderr.write(f"\n  [{i}] {match}\n")
                    try:
                        parsed = json_module.loads(match)
                        sys.stderr.write(f"      Parsed: {json_module.dumps(parsed, indent=8)}\n")
                    except:
                        pass

            # Look for activation/OTP related info
            otp_patterns = [
                r'"activateCodeToken"[^}]*',
                r'"otp[^}]*',
                r'"activation[^}]*',
                r'"verify[^}]*',
            ]

            sys.stderr.write("\n[*] Searching for OTP/activation info:\n")
            found_otp_info = False
            for pattern in otp_patterns:
                matches = re.findall(pattern, response.text)
                if matches:
                    found_otp_info = True
                    sys.stderr.write(f"  Pattern '{pattern}': {matches[0][:100]}\n")

            if not found_otp_info:
                sys.stderr.write("  No OTP/activation info found in response\n")

            sys.stderr.write("="*70 + "\n\n")
            sys.stderr.flush()

            self._save_response_to_file(response.text)

            # Check for rate limiting
            if response.status_code == 429:
                logger.error("[!] Rate limited (429)")
                return {
                    "status": 429,
                    "error": "rate_limited",
                    "success": False,
                }

            # Check for success indicators
            success = self._check_registration_success(response.text, response.status_code)

            # Extract activation token from response headers/cookies
            activation_token = None
            if "set-cookie" in response.headers:
                cookie_match = re.search(r'activateCodeToken=([^;]+)', response.headers.get("set-cookie", ""))
                if cookie_match:
                    activation_token = cookie_match.group(1)
                    logger.info(f"[+] Activation token extracted: {activation_token[:20]}...")

            return {
                "status": response.status_code,
                "success": success,
                "activation_token": activation_token,
                "body": response.text[:3000],
                "url": response.url,
                "cookies": dict(self.session.cookies) if self.session.cookies else {},
            }

        except Exception as e:
            logger.error("[-] Error submitting form: %s", e)
            return None

    # ------------------------------------------------------------------
    # Check if registration succeeded
    # ------------------------------------------------------------------
    @staticmethod
    def _check_registration_success(response_body: str, status_code: int) -> bool:
        """Determine if registration succeeded by checking response content"""
        body_lower = response_body.lower()

        # Success indicators
        success_patterns = [
            r"verification.*email.*sent",
            r"check.*email.*verification",
            r"otp.*sent",
            r"verification.*code",
            r"confirm.*email",
            r"verify.*account",
            r"activation.*email",
            r"/verify",
            r"/dashboard",
            r'"success"\s*:\s*true',
            r'"registered"\s*:\s*true',
        ]

        for pattern in success_patterns:
            if re.search(pattern, body_lower):
                logger.info("[+] Found success indicator: %s", pattern)
                return True

        # Failure indicators
        failure_patterns = [
            r"multiple.*account",
            r"already.*exist",
            r"email.*already",
            r"username.*already",
            r'"success"\s*:\s*false',
            r"registration\s+failed",
            r"form.*invalid",
        ]

        for pattern in failure_patterns:
            if re.search(pattern, body_lower):
                logger.warning("[-] Found failure indicator: %s", pattern)
                return False

        # Detect blank form (validation failure)
        blank_form_indicators = [
            r'name="name"\s+[^>]*value=""',
            r'name="email"\s+[^>]*value=""',
            r'<div class="space-y-4">',
            r'Create your Account',
        ]

        blank_form_count = sum(1 for ind in blank_form_indicators if re.search(ind, response_body))
        if blank_form_count >= 2:
            logger.warning("[-] Detected blank signup form (validation failure)")
            return False

        # Redirect usually means success
        if status_code in (302, 303, 307, 308):
            logger.info("[+] Got redirect status %d - likely success", status_code)
            return True

        logger.warning("[-] Could not determine success from status %d and content", status_code)
        return False

    @staticmethod
    def _save_response_to_file(response_body: str, filename: str = "last_response.txt") -> None:
        """Save response for review"""
        try:
            filepath = Path(__file__).resolve().parent / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response_body)
            logger.info("[+] Response saved to: %s", filepath)
        except Exception as e:
            logger.warning("[-] Could not save response: %s", e)

    # ------------------------------------------------------------------
    # Detect OTP requirement
    # ------------------------------------------------------------------
    @staticmethod
    def detect_otp_requirement(html: str) -> bool:
        """Check if response requires OTP/verification"""
        otp_patterns = [r"otp", r"verification.*code", r"verify.*code", r"enter.*code", r"2fa"]
        html_lower = html.lower()
        return any(re.search(pattern, html_lower) for pattern in otp_patterns)

    # ------------------------------------------------------------------
    # Handle OTP verification
    # ------------------------------------------------------------------
    def handle_otp_verification(self) -> Optional[Dict[str, Any]]:
        """Handle OTP input and verification"""
        logger.info("[!] OTP verification required")
        sys.stderr.write("\n" + "="*60 + "\n")
        sys.stderr.write("OTP VERIFICATION REQUIRED\n")
        sys.stderr.write("="*60 + "\n")
        sys.stderr.flush()

        otp = input("Enter OTP received on your email/phone: ").strip()

        if not otp:
            logger.error("[-] No OTP provided")
            return None

        logger.info("[*] Submitting OTP...")

        otp_endpoints = [
            "https://marketing.moceansms.com/verify",
            "https://marketing.moceansms.com/api/verify-otp",
        ]

        for endpoint in otp_endpoints:
            try:
                logger.info("[*] Trying OTP endpoint: %s", endpoint)
                response = self.session.post(
                    endpoint,
                    data={"otp": otp, "code": otp},
                    headers={**FETCH_HEADERS, "Origin": "https://marketing.moceansms.com"},
                    timeout=30,
                    allow_redirects=True,
                )
                logger.info("[*] OTP response status: %s", response.status_code)

                if response.status_code in (200, 201, 302):
                    logger.info("[+] OTP verified!")
                    return {"status": response.status_code, "success": True, "endpoint": endpoint}
            except Exception as e:
                logger.warning("[-] OTP endpoint failed: %s", e)
                continue

        logger.warning("[-] OTP verification failed on all endpoints")
        return None

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------
    def run(self, name: str, email: str, mobile: str, username: str, password: str) -> Dict[str, Any]:
        """Main registration flow"""
        logger.info("[=] Starting MoceanSMS registration [=]")
        logger.info("[*] Target: %s", self.target_url)

        # Step 1: Fetch signup page
        logger.info("\n[STEP 1] Fetching signup page...")
        page = self.fetch_signup_page()
        if not page:
            return {"success": False, "error": "fetch_failed", "stage": "get"}

        # Step 2: Solve Turnstile
        logger.info("\n[STEP 2] Solving Turnstile challenge...")
        for attempt in range(MAX_RETRIES + 1):
            logger.info("[*] Anti-Captcha attempt %d/%d", attempt + 1, MAX_RETRIES + 1)
            token = self.solve_turnstile_anticaptcha()
            if token:
                self.turnstile_token = token
                break
            if attempt < MAX_RETRIES:
                logger.info("[*] Retrying in 5s...")
                time.sleep(5)

        if not self.turnstile_token:
            return {"success": False, "error": "turnstile_solve_failed", "stage": "captcha"}

        # Step 3: Submit signup form
        logger.info("\n[STEP 3] Submitting signup form...")
        result = self.submit_signup_form(
            name=name, email=email, mobile=mobile, username=username, password=password
        )

        if not result:
            return {"success": False, "error": "form_submission_failed", "stage": "post"}

        if result.get("status") == 429:
            return {
                "success": False,
                "error": "rate_limited",
                "message": "IP rate limited. Switch VPN/Proxy and try again.",
                "stage": "post",
            }

        # Step 4: Check for OTP
        logger.info("\n[STEP 4] Checking for OTP requirement...")
        if self.detect_otp_requirement(result.get("body", "")):
            logger.info("[!] OTP required")
            otp_result = self.handle_otp_verification()

            if otp_result and otp_result.get("success"):
                logger.info("[+] OTP verification succeeded!")
                return {
                    "success": True,
                    "status": otp_result["status"],
                    "otp_verified": True,
                    "stage": "otp_verified",
                }
            else:
                return {"success": False, "error": "otp_verification_failed", "stage": "otp"}
        else:
            logger.info("[*] No OTP required")

        # Return final result
        return {
            "success": result.get("success", False),
            "status": result.get("status"),
            "otp_verified": False,
            "stage": "complete",
            "error": None if result.get("success") else "registration_failed",
        }


# ============================================================================
# ENTRY POINT
# ============================================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MoceanSMS registration automation with proxy support and OTP verification")
    p.add_argument("--name", default=DEFAULT_FULLNAME, help="Full name")
    p.add_argument("--email", default=DEFAULT_EMAIL, help="Email address for registration")
    p.add_argument("--mobile", default=DEFAULT_MOBILE, help="Mobile number")
    p.add_argument("--username", default=DEFAULT_USERNAME, help="Username")
    p.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for registration")
    p.add_argument("--target-url", default=TARGET_URI, help="Target signup URL")
    p.add_argument("--api-key", default=API_KEY, help="Anti-Captcha API key")
    p.add_argument("--sitekey", default=SITEKEY, help="Turnstile sitekey")
    p.add_argument("--proxy", default=PROXY_URL, help="Proxy URL (e.g., http://proxy.com:8080 or socks5://proxy.com:1080)")
    p.add_argument("--token", default=None, help="Reuse existing Turnstile token (saves Anti-Captcha cost)")

    # OTP verification options
    p.add_argument("--verify-otp", action="store_true", help="Automatically verify OTP after registration")
    p.add_argument("--email-password", default=None, help="Email password for OTP retrieval (Gmail app password recommended)")
    p.add_argument("--imap-server", default="imap.gmail.com", help="IMAP server for email access (default: Gmail)")

    return p.parse_args()


def _missing(value: str) -> bool:
    return (not value) or value.startswith("YOUR_") or value == "your_username" or value == "your_password"


def _run_otp_verification(
    email: str, email_password: str, imap_server: str, activation_token: str
) -> Dict[str, Any]:
    """Run OTP verification via API"""
    try:
        # Import OTP verifier
        sys.path.insert(0, str(Path(__file__).parent))
        from mocean_otp_verify import complete_mocean_verification

        logger.info("\n[OTP VERIFICATION] Starting OTP verification (API-based)...")

        result = complete_mocean_verification(
            email_address=email,
            email_password=email_password,
            activation_token=activation_token,
            imap_server=imap_server,
        )

        return {
            "success": result.get("success", False),
            "otp_verified": result.get("success", False),
            "stage": "otp_verified" if result.get("success") else "otp_failed",
            "error": result.get("error"),
            "message": result.get("message"),
        }

    except Exception as e:
        logger.error(f"[-] OTP verification exception: {e}")
        return {
            "success": False,
            "otp_verified": False,
            "stage": "otp_failed",
            "error": f"otp_exception: {str(e)}",
        }


def main() -> None:
    args = parse_args()

    if _missing(args.api_key):
        logger.error("[!] Missing Anti-Captcha API key")
        print(json.dumps({"success": False, "error": "missing_api_key"}))
        sys.exit(1)

    if _missing(args.sitekey):
        logger.error("[!] Missing Turnstile sitekey")
        print(json.dumps({"success": False, "error": "missing_sitekey"}))
        sys.exit(1)

    # Validate OTP verification options
    if args.verify_otp and not args.email_password:
        logger.error("[!] --verify-otp requires --email-password")
        print(json.dumps({"success": False, "error": "missing_email_password"}))
        sys.exit(1)

    # If no proxy specified and PROXY_POOL is available, use random proxy from pool
    proxy_to_use = args.proxy
    if not proxy_to_use or (proxy_to_use and proxy_to_use.lower() not in ("none", "disable", "")):
        # User provided explicit proxy - use it
        pass
    elif not args.proxy:
        # No proxy specified - use pool (None will trigger pool selection in __init__)
        proxy_to_use = None

    try:
        auth = MoceanSMSAuthAutomated(
            api_key=args.api_key,
            target_url=args.target_url,
            sitekey=args.sitekey,
            proxy_url=proxy_to_use,
            reuse_token=args.token,
        )
        result = auth.run(
            name=args.name,
            email=args.email,
            mobile=args.mobile,
            username=args.username,
            password=args.password,
        )

        # Handle OTP verification if requested and registration succeeded
        if result.get("success") and args.verify_otp and result.get("activation_token"):
            activation_token = result["activation_token"]
            logger.info(f"\n[*] OTP verification requested...")
            logger.info(f"[*] Using activation token: {activation_token[:30]}...")

            # Run OTP verification
            otp_result = _run_otp_verification(
                email=args.email,
                email_password=args.email_password,
                imap_server=args.imap_server,
                activation_token=activation_token,
            )

            # Merge OTP result into main result
            result.update(otp_result)

    except Exception as exc:
        logger.exception("[-] Unhandled exception")
        result = {
            "success": False,
            "error": f"exception: {exc.__class__.__name__}: {exc}",
        }

    print(json.dumps(result))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
