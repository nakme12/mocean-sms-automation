#!/usr/bin/env python3
"""
MoceanSMS 6-Step Authentication Flow
Step 2: Signin (202 Pending Activation)
Step 3: Activate with OTP
Step 4: Second Login
Step 5: Verify Session OTP
Step 6: Dashboard Verification
"""

import os
import sys
import json
import subprocess
import argparse
import random
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime
from urllib.parse import urlencode

# User Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

try:
    from anticaptchaofficial.turnstileproxyless import turnstileProxyless
except ImportError:
    print("ERROR: anticaptchaofficial not installed")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return {}

    env_vars = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        env_vars[k] = v
    return env_vars

ENV = load_env()

ANTICAPTCHA_KEY = os.environ.get("ANTICAPTCHA_KEY", ENV.get("ANTICAPTCHA_KEY", ""))
SITE_KEY = os.environ.get("SITE_KEY", ENV.get("SITE_KEY", "0x4AAAAAABkK8iPAGoGsGhNf"))
SIGNIN_ENDPOINT = "https://marketing.moceansms.com/signin"
ACTIVATE_ENDPOINT = "https://marketing.moceansms.com/api/v1/auth/activate"
VERIFY_LOGIN_ENDPOINT = "https://marketing.moceansms.com/api/v1/auth/verify-login"
DASHBOARD_ENDPOINT = "https://marketing.moceansms.com/api/v1/dashboard/summary"
SIGNIN_NEXT_ACTION = "404f077d184e097f9f8779873fc060e09d1682ddc7"  # Latest from HAR files

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{level:5}] {msg}")

    def info(self, msg: str):
        self.log("INFO", msg)

    def success(self, msg: str):
        self.log("✓", msg)

    def error(self, msg: str):
        self.log("✗", msg)

    def debug(self, msg: str):
        self.log("DEBUG", msg)

logger = Logger()

# ============================================================================
# CAPTCHA SOLVING
# ============================================================================

def solve_captcha() -> Optional[str]:
    """Solve Turnstile CAPTCHA - Fresh token for each attempt"""
    logger.info("Solving CAPTCHA...")

    if not ANTICAPTCHA_KEY:
        logger.error("ANTICAPTCHA_KEY not set")
        return None

    try:
        solver = turnstileProxyless()
        solver.set_verbose(0)
        solver.set_key(ANTICAPTCHA_KEY)
        solver.set_website_key(SITE_KEY)
        solver.set_website_url("https://marketing.moceansms.com")

        token = solver.solve_and_return_solution()
        if token:
            logger.success(f"CAPTCHA solved")
            return token
        else:
            logger.error("CAPTCHA solving failed")
            return None
    except Exception as e:
        logger.error(f"CAPTCHA error: {e}")
        return None

# ============================================================================
# STEP 2: SIGNIN (First Login - Expecting 202)
# ============================================================================

def signin_step1(
    username: str,
    password: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Step 2: First login attempt (should return 202 pending activation)"""

    logger.info("="*80)
    logger.info("STEP 2: FIRST LOGIN (Expecting 202 - Account Pending Activation)")
    logger.info("="*80)

    captcha_token = solve_captcha()
    if not captcha_token:
        return False, {"error": "CAPTCHA_SOLVE_FAILED"}

    logger.info(f"Submitting signin request for: {username}")

    # Select random user agent
    user_agent = random.choice(USER_AGENTS)
    logger.debug(f"Using User-Agent: {user_agent[:60]}...")

    # Multipart form-data payload (EXACT format from HAR 5)
    boundary = "----WebKitFormBoundaryXxnBC6o5xM5BeTIC"
    payload = f"""{boundary}\r\nContent-Disposition: form-data; name="1_username"\r\n\r\n{username}\r\n{boundary}\r\nContent-Disposition: form-data; name="1_password"\r\n\r\n{password}\r\n{boundary}\r\nContent-Disposition: form-data; name="1_captcha_token"\r\n\r\n{captcha_token}\r\n{boundary}\r\nContent-Disposition: form-data; name="1_cf-turnstile-response"\r\n\r\n{captcha_token}\r\n{boundary}\r\nContent-Disposition: form-data; name="0"\r\n\r\n["$K1"]\r\n{boundary}--\r\n"""

    logger.debug(f"Payload constructed (multipart/form-data)")

    # Show exact payload
    print("\n" + "="*80)
    print("EXACT PAYLOAD SENT:")
    print("="*80)
    print(repr(payload))
    print("="*80 + "\n")

    cmd = [
        "curl", "-i",
        "-X", "POST",
        "-H", "accept: text/x-component",
        "-H", "accept-encoding: gzip, deflate, br, zstd",
        "-H", "accept-language: en-GB,en-US;q=0.9,en;q=0.8",
        "-H", "content-type: multipart/form-data; boundary=----WebKitFormBoundaryXxnBC6o5xM5BeTIC",
        "-H", f"next-action: {SIGNIN_NEXT_ACTION}",
        "-H", "next-router-state-tree: %5B%22%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22signin%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "-H", "origin: https://marketing.moceansms.com",
        "-H", "priority: u=1, i",
        "-H", "referer: https://marketing.moceansms.com/signin",
        "-H", "sec-ch-ua: \"Brave\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
        "-H", "sec-ch-ua-mobile: ?0",
        "-H", "sec-ch-ua-platform: \"macOS\"",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-H", "sec-gpc: 1",
        "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "-d", payload
    ]

    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])

    cmd.append(SIGNIN_ENDPOINT)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}

        # *** SHOW EXACT COMPLETE RESPONSE ***
        print("\n" + "="*80)
        print("EXACT COMPLETE API RESPONSE - SIGNIN_STEP1:")
        print("="*80)
        print(result.stdout)
        print("="*80 + "\n")

        # Parse response (split headers from body)
        response_parts = result.stdout.split("\r\n\r\n", 1)
        headers = response_parts[0] if response_parts else ""
        body = response_parts[1] if len(response_parts) > 1 else ""

        # Extract status code from first line
        status_line = headers.split("\r\n")[0] if headers else ""
        try:
            status_code = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0
        except:
            status_code = 0

        logger.info(f"HTTP Status Code: {status_code}")

        # Parse RSC response format (look for line starting with "1:")
        response_data = {}
        for line in body.split("\n"):
            if line.startswith("1:"):
                # Handle error format: 1:E{...}
                if line.startswith("1:E"):
                    try:
                        error_data = json.loads(line[3:])
                        logger.error(f"Server error - digest: {error_data.get('digest', 'unknown')}")
                        return False, {"error": "Server error", "digest": error_data.get('digest')}
                    except Exception as e:
                        logger.error(f"Failed to parse error response: {e}")
                        return False, {"error": "Server error (unparseable)"}
                else:
                    try:
                        response_data = json.loads(line[2:])
                        break
                    except:
                        pass

        if not response_data and not any(line.startswith("1:E") for line in body.split("\n")):
            logger.error(f"Failed to parse response body")
            return False, {"error": "Invalid response format"}

        logger.debug(f"DEBUG SIGNIN_STEP1 | Full: {json.dumps(response_data)}")

        # API returns success boolean and message
        if response_data.get("success"):
            logger.success(f"Signin successful!")
            logger.info(f"Message: {response_data.get('message', 'No message')}")
            return True, response_data
        else:
            msg = response_data.get("message", "Unknown error")
            logger.error(f"Signin failed: {msg}")
            return False, response_data

    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# STEP 3: ACTIVATE (Verification Round 1 - OTP)
# ============================================================================

def activate_account(
    request_id: str,
    otp_code: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Step 3: Verify OTP and activate account"""

    logger.info("="*80)
    logger.info("STEP 3: ACTIVATE ACCOUNT (Verification Round 1 - OTP)")
    logger.info("="*80)

    payload = json.dumps({
        "otp": otp_code,
        "request_id": request_id
    })

    logger.info(f"Submitting OTP for request_id: {request_id[:20]}...")

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"User-Agent: {user_agent}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-d", payload
    ]

    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])

    cmd.append(ACTIVATE_ENDPOINT)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}

        # Parse response and status code
        output = result.stdout.rsplit("\n", 1)
        response_text = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0

        # *** SHOW EXACT API RESPONSE WITH STATUS CODE ***
        print("\n" + "="*80)
        print("EXACT API RESPONSE - ACTIVATE:")
        print("="*80)
        print(f"HTTP STATUS CODE: {status_code}")
        print(f"\nCOMPLETE RESPONSE BODY:\n{response_text}")
        print("="*80 + "\n")

        try:
            response_data = json.loads(response_text)
        except:
            logger.error(f"Failed to parse JSON response")
            return False, {"error": "Invalid JSON response"}

        logger.debug(f"DEBUG ACTIVATE | Status: {response_data.get('status')} | Full: {json.dumps(response_data)}")

        if response_data.get("success"):
            logger.success("Account activated successfully!")
            return True, response_data

        msg = response_data.get("message", "Activation failed")
        logger.error(f"Activation failed: {msg}")
        return False, response_data

    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# STEP 4: SECOND LOGIN (After Activation)
# ============================================================================

def signin_step2(
    username: str,
    password: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Step 4: Second login attempt after activation (Fresh CAPTCHA required)"""

    logger.info("="*80)
    logger.info("STEP 4: SECOND LOGIN (After Activation)")
    logger.info("="*80)

    captcha_token = solve_captcha()
    if not captcha_token:
        return False, {"error": "CAPTCHA_SOLVE_FAILED"}

    logger.info(f"Submitting second signin request for: {username}")

    # Select random user agent
    user_agent = random.choice(USER_AGENTS)
    logger.debug(f"Using User-Agent: {user_agent[:60]}...")

    # Multipart form-data payload (CORRECT format with fresh CAPTCHA)
    boundary = "----WebKitFormBoundaryXxnBC6o5xM5BeTIC"
    payload = f"""{boundary}\r
Content-Disposition: form-data; name="1_username"\r
\r
{username}\r
{boundary}\r
Content-Disposition: form-data; name="1_password"\r
\r
{password}\r
{boundary}\r
Content-Disposition: form-data; name="1_captcha_token"\r
\r
{captcha_token}\r
{boundary}\r
Content-Disposition: form-data; name="1_cf-turnstile-response"\r
\r
{captcha_token}\r
{boundary}\r
Content-Disposition: form-data; name="0"\r
\r
["$K1"]\r
{boundary}--\r
"""

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"User-Agent: {user_agent}",
        "-H", "Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryXxnBC6o5xM5BeTIC",
        "-H", "Accept: text/x-component",
        "-H", f"next-action: {SIGNIN_NEXT_ACTION}",
        "-H", "accept-language: en-GB,en-US;q=0.9,en;q=0.8",
        "-H", "origin: https://marketing.moceansms.com",
        "-H", "referer: https://marketing.moceansms.com/signin",
        "-H", "sec-ch-ua: \"Brave\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
        "-H", "sec-ch-ua-mobile: ?0",
        "-H", "sec-ch-ua-platform: \"macOS\"",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-d", payload
    ]

    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])

    cmd.append(SIGNIN_ENDPOINT)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}

        # Parse response and status code
        output = result.stdout.rsplit("\n", 1)
        response_text = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0

        # *** SHOW EXACT API RESPONSE WITH STATUS CODE ***
        print("\n" + "="*80)
        print("EXACT API RESPONSE - SIGNIN_STEP2:")
        print("="*80)
        print(f"HTTP STATUS CODE: {status_code}")
        print(f"\nCOMPLETE RESPONSE BODY:\n{response_text}")
        print("="*80 + "\n")

        try:
            response_data = json.loads(response_text)
        except:
            logger.error(f"Failed to parse JSON response")
            return False, {"error": "Invalid JSON response"}

        logger.debug(f"DEBUG SIGNIN_STEP2 | Status: {response_data.get('status')} | Full: {json.dumps(response_data)}")

        status = response_data.get("status")

        # After activation, should get 200 or 202 if second OTP needed
        if status == 200 and response_data.get("success"):
            logger.success("Login successful!")
            return True, response_data

        # Check if second OTP is needed
        if status == 202:
            logger.info("Second OTP required for session verification")
            return True, response_data

        msg = response_data.get("message", f"Status {status}")
        logger.error(f"Login failed: {msg}")
        return False, response_data

    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# STEP 5: VERIFY LOGIN (Verification Round 2 - Session OTP)
# ============================================================================

def verify_login(
    otp_code: str,
    login_token: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Step 5: Verify login with session OTP"""

    logger.info("="*80)
    logger.info("STEP 5: VERIFY LOGIN (Verification Round 2 - Session OTP)")
    logger.info("="*80)

    payload = json.dumps({
        "otp": otp_code,
        "session_id": login_token
    })

    logger.info(f"Submitting session OTP")

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"User-Agent: {user_agent}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-d", payload
    ]

    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])

    cmd.append(VERIFY_LOGIN_ENDPOINT)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}

        # Parse response and status code
        output = result.stdout.rsplit("\n", 1)
        response_text = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0

        # *** SHOW EXACT API RESPONSE WITH STATUS CODE ***
        print("\n" + "="*80)
        print("EXACT API RESPONSE - VERIFY_LOGIN:")
        print("="*80)
        print(f"HTTP STATUS CODE: {status_code}")
        print(f"\nCOMPLETE RESPONSE BODY:\n{response_text}")
        print("="*80 + "\n")

        try:
            response_data = json.loads(response_text)
        except:
            logger.error(f"Failed to parse JSON response")
            return False, {"error": "Invalid JSON response"}

        logger.debug(f"DEBUG VERIFY_LOGIN | Status: {response_data.get('status')} | Full: {json.dumps(response_data)}")

        if response_data.get("success"):
            logger.success("Login verified successfully!")
            return True, response_data

        msg = response_data.get("message", "Verification failed")
        logger.error(f"Login verification failed: {msg}")
        return False, response_data

    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# STEP 6: DASHBOARD VERIFICATION
# ============================================================================

def verify_dashboard(
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Step 6: Verify session by accessing dashboard"""

    logger.info("="*80)
    logger.info("STEP 6: DASHBOARD VERIFICATION")
    logger.info("="*80)

    logger.info("Accessing dashboard...")

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "GET",
        "-H", f"User-Agent: {user_agent}",
        "-H", "Accept: application/json"
    ]

    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])

    cmd.append(DASHBOARD_ENDPOINT)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}

        # Parse response and status code
        output = result.stdout.rsplit("\n", 1)
        response_text = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0

        # *** SHOW EXACT API RESPONSE WITH STATUS CODE ***
        print("\n" + "="*80)
        print("EXACT API RESPONSE - DASHBOARD:")
        print("="*80)
        print(f"HTTP STATUS CODE: {status_code}")
        print(f"\nCOMPLETE RESPONSE BODY:\n{response_text}")
        print("="*80 + "\n")

        try:
            response_data = json.loads(response_text)
        except:
            logger.error(f"Failed to parse JSON response")
            return False, {"error": "Invalid JSON response"}

        logger.debug(f"DEBUG DASHBOARD | Status: {response_data.get('status')} | Full: {json.dumps(response_data)}")

        if response_data.get("status") == 200 or response_data.get("success"):
            logger.success("Dashboard access verified!")
            return True, response_data

        msg = response_data.get("message", "Dashboard access failed")
        logger.error(f"Dashboard access failed: {msg}")
        return False, response_data

    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoceanSMS 6-Step Authentication Flow")
    parser.add_argument("--username", required=True, help="Username (not email)")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--proxy", help="Proxy URL (optional)")

    args = parser.parse_args()

    logger.info("="*80)
    logger.info("MOCEANSMS 6-STEP AUTHENTICATION FLOW")
    logger.info("="*80)
    logger.info(f"Username: {args.username}")
    logger.info(f"Proxy: {args.proxy if args.proxy else 'None (direct)'}")
    logger.info("="*80)

    # STEP 2: First Login
    success, response = signin_step1(
        username=args.username,
        password=args.password,
        proxy_url=args.proxy
    )

    if not success:
        logger.error("First login failed. Exiting.")
        sys.exit(1)

    # Check if account needs activation (202 status)
    if response.get("status") == 202:
        logger.info("\nAccount pending activation. Proceeding to OTP verification...")

        # STEP 3: Activate with OTP
        request_id = response.get("request_id")
        if not request_id:
            logger.error("request_id not found in response")
            sys.exit(1)

        otp_code = input("\nEnter activation OTP (6 digits): ").strip()
        if not otp_code or len(otp_code) != 6:
            logger.error("Invalid OTP format")
            sys.exit(1)

        success, response = activate_account(
            request_id=request_id,
            otp_code=otp_code,
            proxy_url=args.proxy
        )

        if not success:
            logger.error("Account activation failed. Exiting.")
            sys.exit(1)

        # STEP 4: Second Login (Fresh CAPTCHA)
        logger.info("\nProceeding to second login after activation...")
        success, response = signin_step2(
            username=args.username,
            password=args.password,
            proxy_url=args.proxy
        )

        if not success:
            logger.error("Second login failed. Exiting.")
            sys.exit(1)

        # Check if session OTP is needed
        if response.get("status") == 202:
            logger.info("\nSession OTP required for full access...")

            # STEP 5: Verify Login
            login_token = response.get("session_id") or response.get("login_token")
            if not login_token:
                logger.error("login_token/session_id not found in response")
                sys.exit(1)

            session_otp = input("\nEnter session OTP (6 digits): ").strip()
            if not session_otp or len(session_otp) != 6:
                logger.error("Invalid OTP format")
                sys.exit(1)

            success, response = verify_login(
                otp_code=session_otp,
                login_token=login_token,
                proxy_url=args.proxy
            )

            if not success:
                logger.error("Session verification failed. Exiting.")
                sys.exit(1)

    # STEP 6: Dashboard Verification
    logger.info("\nVerifying dashboard access...")
    success, response = verify_dashboard(proxy_url=args.proxy)

    if success:
        logger.info("\n" + "="*80)
        logger.success("AUTHENTICATION FLOW COMPLETED SUCCESSFULLY!")
        logger.info("="*80)
    else:
        logger.error("\nDashboard verification failed.")
        sys.exit(1)
