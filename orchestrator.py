#!/usr/bin/env python3
"""
MoceanSMS Authentication Orchestrator
Calls existing signup.py, verify, and signin scripts in sequence
Passes data between steps
"""

import subprocess
import json
import argparse
import random
import string
import sys
from datetime import datetime

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def info(self, msg: str):
        self.log(f"[INFO] {msg}")

    def success(self, msg: str):
        self.log(f"[✓] {msg}")

    def error(self, msg: str):
        self.log(f"[✗] {msg}")

    def section(self, title: str):
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}\n")

logger = Logger()

# ============================================================================
# STEP 1: Call signup.py
# ============================================================================

def step1_call_signup(email: str, username: str, password: str, proxy: str) -> tuple:
    """Call existing signup.py script"""

    logger.section("STEP 1: CALLING signup.py")
    logger.info(f"Email: {email}")
    logger.info(f"Username: {username}")
    logger.info(f"Proxy: {proxy if proxy else 'None'}")

    cmd = [
        "python3", "signup.py",
        "--email", email,
        "--username", username,
        "--password", password,
    ]

    if proxy:
        cmd.extend(["--proxy", proxy])

    logger.info(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    print(result.stdout)
    if result.stderr:
        print(f"STDERR:\n{result.stderr}")

    if result.returncode == 0:
        logger.success("✓ Signup completed successfully")
        return True, email, username, password
    else:
        logger.error(f"✗ Signup failed with return code {result.returncode}")
        return False, None, None, None

# ============================================================================
# STEP 2: Get ReqId from /signup/verify
# ============================================================================

def step2_get_reqid(email: str, username: str, password: str, proxy: str) -> tuple:
    """Call /signup/verify to get reqid"""

    logger.section("STEP 2: GET REQID FROM /signup/verify")
    logger.info(f"Email: {email}")
    logger.info(f"Username: {username}")
    logger.info(f"Proxy: {proxy if proxy else 'None'}")

    import subprocess
    import json
    import tempfile
    import os

    try:
        from anticaptchaofficial.turnstileproxyless import turnstileProxyless
    except:
        logger.error("anticaptchaofficial not installed")
        return False, None, None

    # Solve CAPTCHA for this request
    logger.info("Solving CAPTCHA...")
    try:
        solver = turnstileProxyless()
        solver.set_verbose(0)
        solver.set_key("d3dec0ae9d5b03861195442fb2b0fdd5")
        solver.set_website_key("0x4AAAAAABkK8iPAGoGsGhNf")
        solver.set_website_url("https://marketing.moceansms.com")
        token = solver.solve_and_return_solution()
        if not token:
            logger.error("CAPTCHA solving failed")
            return False, None, None
        logger.success(f"CAPTCHA solved")
    except Exception as e:
        logger.error(f"CAPTCHA error: {e}")
        return False, None, None

    # Call /signup/verify
    payload = json.dumps([])

    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", "accept: text/x-component",
        "-H", "content-type: text/plain;charset=UTF-8",
        "-H", "next-action: 0058da3d16d322c669c30e9298c74fe3436cb50a55",
        "-H", "next-router-state-tree: %5B%22%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22signup%22%2C%7B%22children%22%3A%5B%22verify%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "-d", payload,
    ]

    if proxy:
        if proxy.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", proxy])
        else:
            cmd.extend(["-x", proxy])

    cmd.append("https://marketing.moceansms.com/signup/verify")

    logger.info(f"POST https://marketing.moceansms.com/signup/verify")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Log exact response
    logger.section("EXACT RAW RESPONSE")
    print(result.stdout)
    logger.section("PARSING")

    # Parse response
    response_data = {}
    for line in result.stdout.split("\n"):
        if line.startswith("1:"):
            try:
                response_data = json.loads(line[2:])
                print(json.dumps(response_data, indent=2))
                break
            except:
                pass

    if response_data.get("success"):
        reqid = response_data.get("data", {}).get("reqid")
        otp_email = response_data.get("data", {}).get("to")
        if reqid and otp_email:
            logger.success(f"✓ Got reqid: {reqid}")
            logger.success(f"✓ OTP email: {otp_email}")
            return True, reqid, otp_email

    logger.error("✗ Failed to get reqid")
    return False, None, None

# ============================================================================
# STEP 3: Call signin.py
# ============================================================================

def step3_call_signin(username: str, password: str, proxy: str) -> tuple:
    """Call existing signin.py script"""

    logger.section("STEP 3: CALLING signin.py")
    logger.info(f"Username: {username}")
    logger.info(f"Proxy: {proxy if proxy else 'None'}")

    cmd = [
        "python3", "signin.py",
        "--username", username,
        "--password", password,
    ]

    if proxy:
        cmd.extend(["--proxy", proxy])

    logger.info(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    print(result.stdout)
    if result.stderr:
        print(f"STDERR:\n{result.stderr}")

    # Check if signin returned expected status
    if "202" in result.stdout or "pending activation" in result.stdout.lower():
        logger.success("✓ Signin returned 202 (Account pending activation - expected)")
        return True, result.stdout
    elif "success" in result.stdout.lower():
        logger.success("✓ Signin was successful")
        return True, result.stdout
    else:
        logger.error(f"✗ Signin returned unexpected response")
        return False, result.stdout

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoceanSMS Auth Orchestrator")
    parser.add_argument("--email", help="Email address")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", default="SecurePassword123!", help="Password")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--random", action="store_true", help="Generate random credentials")
    parser.add_argument("--skip-step", type=int, help="Skip to step N (1=signup, 2=reqid, 3=signin)")

    args = parser.parse_args()

    # Generate or use provided credentials
    if args.random:
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        email = f"test{suffix}@gmail.com"
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    else:
        if not args.email or not args.username:
            parser.print_help()
            exit(1)
        email = args.email
        username = args.username

    logger.section("MOCEAN SMS - AUTHENTICATION ORCHESTRATOR")
    logger.info(f"Email: {email}")
    logger.info(f"Username: {username}")
    logger.info(f"Password: {args.password}")
    logger.info(f"Proxy: {args.proxy if args.proxy else 'None (direct)'}")

    # ========== STEP 1: SIGNUP ==========
    if not args.skip_step or args.skip_step <= 1:
        s1_ok, s1_email, s1_username, s1_password = step1_call_signup(
            email, username, args.password, args.proxy
        )
        if not s1_ok:
            logger.error("✗ Step 1 failed - aborting")
            exit(1)
    else:
        s1_email, s1_username, s1_password = email, username, args.password
        logger.info("✓ Skipping Step 1 (as requested)")

    # ========== STEP 2: GET REQID ==========
    if not args.skip_step or args.skip_step <= 2:
        logger.section("STEP 2: CALLING signup_verify.py")
        cmd = ["python3", "signup_verify.py"]
        if args.proxy:
            cmd.extend(["--proxy", args.proxy])

        logger.info(f"Command: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        print(result.stdout)
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")

        # Extract reqid and email from output
        s2_reqid = None
        s2_email = None
        for line in result.stdout.split("\n"):
            if line.startswith("REQID="):
                s2_reqid = line.replace("REQID=", "").strip()
            if line.startswith("EMAIL="):
                s2_email = line.replace("EMAIL=", "").strip()

        if s2_reqid and s2_email:
            logger.success("✓ Step 2 (signup_verify) completed successfully")
        else:
            logger.error("✗ Step 2 failed - could not get reqid")
            exit(1)
    else:
        s2_reqid, s2_email = None, email
        logger.info("✓ Skipping Step 2 (as requested)")

    # ========== STEP 3: SIGNIN ==========
    if not args.skip_step or args.skip_step <= 3:
        s3_ok, s3_response = step3_call_signin(
            s1_username, s1_password, args.proxy
        )
        s3_status = "completed" if s3_ok else "failed"
    else:
        logger.info("✓ Skipping Step 3 (as requested)")
        s3_status = "skipped"

    # ========== STEP 4: VERIFY OTP (Optional - needs user input) ==========
    s4_status = "pending_otp"
    s4_ok = False
    otp_input = input(f"\n{'='*80}\nDo you have the OTP code from {s2_email}? (Enter 6-digit code or press Enter to skip): ")

    if otp_input and len(otp_input.strip()) == 6:
        logger.section("STEP 4: CALLING verify_otp_activate.py")
        cmd = [
            "python3", "verify_otp_activate.py",
            "--otp", otp_input.strip(),
            "--reqid", s2_reqid,
        ]
        if args.proxy:
            cmd.extend(["--proxy", args.proxy])

        logger.info(f"Command: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        print(result.stdout)
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")

        if result.returncode == 0:
            logger.success("✓ Step 4 (OTP verification) completed successfully")
            s4_status = "completed"
            s4_ok = True
        else:
            logger.error("✗ Step 4 failed - OTP verification unsuccessful")
            s4_status = "failed"
    else:
        logger.info("⚠ Skipping Step 4 (no OTP provided)")
        s4_status = "skipped"

    # ========== FINAL SIGNIN (after OTP activation) ==========
    if s4_ok:
        logger.section("STEP 5: FINAL SIGNIN (After OTP Activation)")
        s5_ok, s5_response = step3_call_signin(
            s1_username, s1_password, args.proxy
        )
        s5_status = "completed" if s5_ok else "failed"
    else:
        s5_status = "skipped"

    # ========== FINAL SUMMARY ==========
    logger.section("FINAL SUMMARY")
    summary = {
        "email": email,
        "username": username,
        "step1_signup": "completed",
        "step2_get_reqid": "completed" if s2_reqid else "N/A",
        "step3_signin_pending": s3_status,
        "step4_verify_otp": s4_status,
        "step5_final_signin": s5_status,
        "reqid": s2_reqid if s2_reqid else "N/A",
        "otp_email": s2_email if s2_email else "N/A",
        "status": "Account activated and logged in!" if s4_ok and s5_ok else "Account activation pending OTP verification"
    }
    print(json.dumps(summary, indent=2))
    logger.section("END")
