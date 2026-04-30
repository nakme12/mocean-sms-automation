#!/usr/bin/env python3
"""
MoceanSMS Sign-In - Enhanced & Refactored
Proper error handling, logging, and proxy support
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime

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
TARGET_URL = "https://marketing.moceansms.com/signin"
DEFAULT_NEXT_ACTION = "40e92530aa479fd9a04b80dde42c66010d18f4ff51"

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

logger = Logger()

# ============================================================================
# SIGNIN
# ============================================================================

def solve_captcha() -> Optional[str]:
    """Solve Turnstile CAPTCHA"""
    logger.info("Solving CAPTCHA...")
    
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
            logger.success(f"CAPTCHA solved")
            return token
        else:
            logger.error("CAPTCHA solving failed")
            return None
    except Exception as e:
        logger.error(f"CAPTCHA error: {e}")
        return None

def signin(
    username: str,
    password: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Send signin request"""
    
    # Solve CAPTCHA
    captcha_token = solve_captcha()
    if not captcha_token:
        return False, {"error": "CAPTCHA_SOLVE_FAILED"}
    
    payload = json.dumps([{
        "username": username,
        "password": password,
        "captcha_token": captcha_token
    }])
    
    logger.info(f"Sending signin request...")
    
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", "Content-Type: text/plain;charset=UTF-8",
        "-H", "Accept: text/x-component",
        "-H", f"Next-Action: {DEFAULT_NEXT_ACTION}",
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
            logger.error(f"curl error: {result.stderr[:80]}")
            return False, {"error": result.stderr[:80]}
        
        output = result.stdout.rsplit("\n", 1)
        body = output[0] if output else ""
        status_code = int(output[1]) if len(output) > 1 else 0
        
        logger.info(f"HTTP Status: {status_code}")
        
        # Parse response
        response_data = {}
        for line in body.split("\n"):
            if line.startswith("1:"):
                try:
                    response_data = json.loads(line[2:])
                except:
                    pass
        
        if status_code in [307, 302] or response_data.get("success"):
            logger.success("Signin successful!")
            return True, response_data
        else:
            msg = response_data.get("message", f"HTTP {status_code}")
            logger.error(f"Signin failed: {msg}")
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
    parser = argparse.ArgumentParser(description="MoceanSMS Sign-In")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--proxy", help="Proxy URL")
    
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("SIGNIN FLOW")
    logger.info("="*80)
    logger.info(f"Username: {args.username}")
    
    success, response = signin(
        username=args.username,
        password=args.password,
        proxy_url=args.proxy
    )
    
    logger.info("="*80)
    
    print("\n" + json.dumps({
        "success": success,
        "message": response.get("message"),
        "status": response.get("status")
    }, indent=2))
    
    sys.exit(0 if success else 1)
