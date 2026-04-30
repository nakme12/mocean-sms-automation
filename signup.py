#!/usr/bin/env python3
"""
MoceanSMS Signup - Enhanced & Refactored
Supports: HTTP/SOCKS5 proxies, proper error handling, production logging
"""

import os
import sys
import json
import time
import random
import string
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

try:
    from anticaptchaofficial.turnstileproxyless import turnstileProxyless
except ImportError:
    print("ERROR: anticaptchaofficial not installed")
    print("  pip install anticaptchaofficial")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_env():
    """Load environment variables from .env"""
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
TARGET_URL = "https://marketing.moceansms.com/signup"
DEFAULT_NEXT_ACTION = "40e92530aa479fd9a04b80dde42c66010d18f4ff51"

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def __init__(self):
        self.start_time = datetime.now()
    
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

def solve_captcha(timeout: int = 120) -> Optional[str]:
    """Solve Cloudflare Turnstile using Anti-Captcha API"""
    logger.info(f"Solving Turnstile CAPTCHA (timeout: {timeout}s)...")
    
    if not ANTICAPTCHA_KEY:
        logger.error("ANTICAPTCHA_KEY not set")
        return None
    
    try:
        solver = turnstileProxyless()
        solver.set_verbose(0)
        solver.set_key(ANTICAPTCHA_KEY)
        solver.set_website_key(SITE_KEY)
        solver.set_website_url(TARGET_URL)
        
        token = solver.solve_and_return_solution()
        
        if token:
            logger.success(f"CAPTCHA solved: {token[:40]}...")
            return token
        else:
            logger.error("CAPTCHA solving failed")
            return None
    
    except Exception as e:
        logger.error(f"CAPTCHA error: {e}")
        return None

# ============================================================================
# HTTP REQUEST (via curl for better proxy support)
# ============================================================================

def send_signup_request(
    email: str,
    username: str,
    password: str,
    captcha_token: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Send signup request via curl with optional proxy"""
    
    payload = json.dumps([{
        "name": "User",
        "username": username,
        "email": email,
        "mobile": "+60133251752",
        "password": password,
        "confirmPassword": password,
        "captchaToken": captcha_token,
        "agreeLicense": True,
        "receiveOffer": False
    }])
    
    logger.info(f"Sending signup request (proxy: {'Yes' if proxy_url else 'No'})...")
    
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", "Content-Type: text/plain;charset=UTF-8",
        "-H", "Accept: text/x-component",
        "-H", f"Next-Action: {DEFAULT_NEXT_ACTION}",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "-d", payload
    ]
    
    if proxy_url:
        if proxy_url.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy_url])
        else:
            cmd.extend(["-x", proxy_url])
    
    cmd.append(TARGET_URL)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode != 0:
            logger.error(f"curl error: {result.stderr[:100]}")
            return False, {"error": result.stderr[:100]}
        
        output = result.stdout.rsplit("\n", 1)
        body = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0
        
        logger.debug(f"HTTP Status: {status_code}")
        
        # Parse RSC response format
        response_data = {}
        for line in body.split("\n"):
            if line.startswith("1:"):
                try:
                    response_data = json.loads(line[2:])
                except:
                    pass
        
        if response_data.get("success"):
            logger.success("Signup successful!")
            return True, response_data
        else:
            msg = response_data.get("message", "Unknown error")
            logger.error(f"Signup failed: {msg}")
            return False, response_data
    
    except subprocess.TimeoutExpired:
        logger.error(f"Request timeout ({timeout}s)")
        return False, {"error": "timeout"}
    except Exception as e:
        logger.error(f"Request error: {e}")
        return False, {"error": str(e)}

# ============================================================================
# MAIN FLOW
# ============================================================================

def signup(
    email: str,
    username: str,
    password: str = "SecurePassword123!",
    proxy_url: Optional[str] = None,
    captcha_token: Optional[str] = None
) -> Dict:
    """Complete signup flow"""
    
    logger.info("="*80)
    logger.info("SIGNUP FLOW STARTED")
    logger.info("="*80)
    logger.info(f"Email: {email}")
    logger.info(f"Username: {username}")
    logger.info(f"Proxy: {proxy_url if proxy_url else 'None (direct)'}")
    logger.info("="*80)
    
    # Solve CAPTCHA if not provided
    if not captcha_token:
        captcha_token = solve_captcha()
        if not captcha_token:
            return {
                "success": False,
                "error": "CAPTCHA_SOLVE_FAILED",
                "message": "Failed to solve CAPTCHA"
            }
    
    # Send signup request
    success, response = send_signup_request(
        email=email,
        username=username,
        password=password,
        captcha_token=captcha_token,
        proxy_url=proxy_url
    )
    
    logger.info("="*80)
    if success:
        logger.success("SIGNUP COMPLETED SUCCESSFULLY")
        logger.info(f"Email: {email}")
        logger.info(f"Username: {username}")
        if response.get("activation_token"):
            logger.info(f"Token: {response['activation_token']}")
    else:
        logger.error("SIGNUP FAILED")
        if response.get("message"):
            logger.error(f"Reason: {response['message']}")
    logger.info("="*80)
    
    return {
        "success": success,
        "email": email,
        "username": username,
        "password": password,
        "activation_token": response.get("activation_token"),
        "response": response
    }

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoceanSMS Signup")
    parser.add_argument("--email", required=True, help="Email address")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", default="SecurePassword123!", help="Password")
    parser.add_argument("--proxy", help="Proxy URL (http://... or socks5://...)")
    parser.add_argument("--captcha", help="Pre-solved CAPTCHA token (skip solving)")
    parser.add_argument("--random", action="store_true", help="Generate random email/username")
    
    args = parser.parse_args()
    
    email = args.email
    username = args.username
    
    if args.random:
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        email = f"test{suffix}@gmail.com"
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        logger.info(f"Generated random credentials:")
        logger.info(f"  Email: {email}")
        logger.info(f"  Username: {username}")
    
    result = signup(
        email=email,
        username=username,
        password=args.password,
        proxy_url=args.proxy,
        captcha_token=args.captcha
    )
    
    print("\n" + "="*80)
    print("RESULT")
    print("="*80)
    print(json.dumps({
        "success": result["success"],
        "email": result["email"],
        "username": result["username"],
        "activation_token": result["activation_token"]
    }, indent=2))
    print("="*80)
    
    sys.exit(0 if result["success"] else 1)
