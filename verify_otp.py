#!/usr/bin/env python3
"""
MoceanSMS OTP Verification - Enhanced & Refactored
Verifies OTP during signup process
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

# User Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]

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

# OTP verification endpoints to try
ENDPOINTS = [
    "https://marketing.moceansms.com/api/signup/verify",
    "https://marketing.moceansms.com/verify",
    "https://dashboard.moceansms.com/api/verify"
]

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
# OTP VERIFICATION
# ============================================================================

def verify_otp(
    otp_code: str,
    activation_token: str,
    proxy_url: Optional[str] = None,
    timeout: int = 120
) -> Tuple[bool, Dict]:
    """Verify OTP code"""
    
    logger.info(f"Verifying OTP code: {otp_code[:3]}***")
    logger.info(f"Token: {activation_token[:20]}...")
    
    payload = json.dumps({
        "otp_code": otp_code,
        "token": activation_token
    })
    
    # Try each endpoint
    for endpoint in ENDPOINTS:
        logger.info(f"Trying: {endpoint}")

        user_agent = random.choice(USER_AGENTS)

        cmd = [
            "curl", "-s", "-w", "\n%{http_code}",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-H", f"User-Agent: {user_agent}",
            "-d", payload
        ]
        
        if proxy_url:
            if proxy_url.startswith("socks5://"):
                cmd.extend(["--socks5-hostname", proxy_url])
            else:
                cmd.extend(["-x", proxy_url])
        
        cmd.append(endpoint)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            
            if result.returncode == 0:
                output = result.stdout.rsplit("\n", 1)
                body = output[0] if output else ""
                status_code = int(output[1]) if len(output) > 1 else 0
                
                logger.info(f"Status: {status_code}")
                
                try:
                    response_data = json.loads(body)
                    
                    if response_data.get("success") or status_code in [200, 303]:
                        logger.success(f"OTP verified! Using {endpoint}")
                        return True, response_data
                    
                except:
                    pass
        
        except Exception as e:
            logger.error(f"Error: {str(e)[:50]}")
    
    logger.error("OTP verification failed on all endpoints")
    return False, {"error": "OTP_VERIFICATION_FAILED"}

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoceanSMS OTP Verification")
    parser.add_argument("--otp", required=True, help="OTP code (6 digits)")
    parser.add_argument("--token", required=True, help="Activation token")
    parser.add_argument("--proxy", help="Proxy URL")
    
    args = parser.parse_args()
    
    # Validate OTP
    if not args.otp.isdigit() or len(args.otp) != 6:
        logger.error("Invalid OTP format (must be 6 digits)")
        sys.exit(1)
    
    logger.info("="*80)
    logger.info("OTP VERIFICATION")
    logger.info("="*80)
    
    success, response = verify_otp(
        otp_code=args.otp,
        activation_token=args.token,
        proxy_url=args.proxy
    )
    
    logger.info("="*80)
    
    print("\n" + json.dumps({
        "success": success,
        "message": response.get("message")
    }, indent=2))
    
    sys.exit(0 if success else 1)
