#!/usr/bin/env python3
"""
MoceanSMS Complete Authentication Orchestrator
Handles: Signup → OTP Verification → Signin
Production-ready with full logging and error handling
"""

import os
import sys
import json
import subprocess
import argparse
import time
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

# ============================================================================
# LOGGER
# ============================================================================

class Logger:
    def log(self, level: str, msg: str, level_width: int = 5):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{level:^{level_width}}] {msg}")
    
    def info(self, msg: str):
        self.log("INFO", msg)
    
    def success(self, msg: str):
        self.log("✓", msg, 1)
    
    def error(self, msg: str):
        self.log("✗", msg, 1)
    
    def step(self, num: int, name: str):
        print(f"\n{'='*80}")
        print(f"[STEP {num}] {name.upper()}")
        print(f"{'='*80}\n")

logger = Logger()

# ============================================================================
# ORCHESTRATOR
# ============================================================================

class MoceanSMSAuth:
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self.email = None
        self.username = None
        self.password = None
        self.activation_token = None
        self.session_cookies = None
    
    def run_script(self, script: str, args: list) -> Dict:
        """Run a Python script and return its output"""
        cmd = [sys.executable, script] + args
        
        logger.info(f"Running: {script} {' '.join(args)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(Path(__file__).parent)
            )
            
            if result.returncode != 0:
                logger.error(f"Script failed: {result.stderr[:100]}")
                return {"success": False, "error": result.stderr[:100]}
            
            # Extract JSON from output
            lines = result.stdout.strip().split('\n')
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except:
                    pass
            
            return {"success": False, "error": "No JSON output"}
        
        except subprocess.TimeoutExpired:
            logger.error("Script timeout")
            return {"success": False, "error": "timeout"}
        except Exception as e:
            logger.error(f"Script error: {e}")
            return {"success": False, "error": str(e)}
    
    def step_1_signup(self, email: str, username: str, password: str) -> bool:
        """Step 1: Signup"""
        logger.step(1, "Signup")
        
        self.email = email
        self.username = username
        self.password = password
        
        args = [
            "--email", email,
            "--username", username,
            "--password", password
        ]
        
        if self.proxy_url:
            args.extend(["--proxy", self.proxy_url])
        
        result = self.run_script("signup.py", args)
        
        if result.get("success"):
            logger.success(f"Signup successful")
            self.activation_token = result.get("activation_token")
            logger.info(f"Activation Token: {self.activation_token[:30]}...")
            return True
        else:
            logger.error(f"Signup failed: {result.get('message', result.get('error'))}")
            return False
    
    def step_2_verify_otp(self, otp_code: str) -> bool:
        """Step 2: Verify OTP"""
        logger.step(2, "OTP Verification")
        
        if not self.activation_token:
            logger.error("No activation token from signup")
            return False
        
        args = [
            "--otp", otp_code,
            "--token", self.activation_token
        ]
        
        if self.proxy_url:
            args.extend(["--proxy", self.proxy_url])
        
        result = self.run_script("verify_otp.py", args)
        
        if result.get("success"):
            logger.success("OTP verification successful")
            return True
        else:
            logger.error(f"OTP verification failed: {result.get('message', result.get('error'))}")
            return False
    
    def step_3_signin(self) -> bool:
        """Step 3: Signin"""
        logger.step(3, "Signin (Account Activation)")
        
        if not self.username or not self.password:
            logger.error("No credentials available")
            return False
        
        args = [
            "--username", self.username,
            "--password", self.password
        ]
        
        if self.proxy_url:
            args.extend(["--proxy", self.proxy_url])
        
        result = self.run_script("signin.py", args)
        
        if result.get("success"):
            logger.success("Signin successful")
            return True
        else:
            logger.error(f"Signin failed: {result.get('message', result.get('error'))}")
            return False
    
    def run_complete_flow(
        self,
        email: str,
        username: str,
        password: str = "SecurePassword123!",
        otp_code: Optional[str] = None
    ) -> Dict:
        """Run complete authentication flow"""
        
        logger.info("="*80)
        logger.info("MOCEANSMS COMPLETE AUTHENTICATION FLOW")
        logger.info("="*80)
        logger.info(f"Email: {email}")
        logger.info(f"Username: {username}")
        logger.info(f"Proxy: {self.proxy_url if self.proxy_url else 'None (direct)'}")
        logger.info("="*80 + "\n")
        
        results = {
            "signup": False,
            "otp_verify": False,
            "signin": False,
            "overall_success": False
        }
        
        # Step 1: Signup
        if not self.step_1_signup(email, username, password):
            return results
        results["signup"] = True
        
        # Step 2: Verify OTP
        if not otp_code:
            print("\n[?] OTP code required for account activation")
            try:
                otp_code = input("[*] Enter OTP (6 digits): ").strip()
            except KeyboardInterrupt:
                logger.error("Flow cancelled by user")
                return results
        
        if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
            logger.error("Invalid OTP format")
            return results
        
        if not self.step_2_verify_otp(otp_code):
            return results
        results["otp_verify"] = True
        
        # Step 3: Signin
        if not self.step_3_signin():
            return results
        results["signin"] = True
        
        results["overall_success"] = True
        return results

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MoceanSMS Complete Authentication Flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Complete flow with OTP
  python3 authenticate.py --email user@gmail.com --username testuser --otp 123456
  
  # Generate random credentials
  python3 authenticate.py --random --otp 123456
  
  # With proxy
  python3 authenticate.py --email user@gmail.com --username testuser --otp 123456 --proxy socks5://...
        """
    )
    
    parser.add_argument("--email", help="Email address")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", default="SecurePassword123!", help="Password")
    parser.add_argument("--otp", help="OTP code (6 digits)")
    parser.add_argument("--proxy", help="Proxy URL (http://... or socks5://...)")
    parser.add_argument("--random", action="store_true", help="Generate random email/username")
    
    args = parser.parse_args()
    
    # Generate random credentials if requested
    if args.random:
        import random
        import string
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        email = f"test{suffix}@gmail.com"
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    else:
        if not args.email or not args.username:
            parser.print_help()
            sys.exit(1)
        email = args.email
        username = args.username
    
    auth = MoceanSMSAuth(proxy_url=args.proxy)
    result = auth.run_complete_flow(
        email=email,
        username=username,
        password=args.password,
        otp_code=args.otp
    )
    
    # Final summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Signup:          {'✓' if result['signup'] else '✗'}")
    print(f"OTP Verification: {'✓' if result['otp_verify'] else '✗'}")
    print(f"Signin:          {'✓' if result['signin'] else '✗'}")
    print("="*80)
    print(f"Overall: {'✓ SUCCESS' if result['overall_success'] else '✗ FAILED'}")
    print("="*80)
    
    sys.exit(0 if result["overall_success"] else 1)
