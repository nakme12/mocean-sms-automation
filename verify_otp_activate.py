#!/usr/bin/env python3
"""
STEP 4: VERIFY OTP AND ACTIVATE ACCOUNT
Calls /signup/verify with OTP code and reqid to activate the account
User provides the OTP code manually (received via email)
"""

import subprocess
import json
import argparse
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

logger = Logger()

# ============================================================================
# CONFIG
# ============================================================================

SIGNUP_VERIFY_URL = "https://marketing.moceansms.com/signup/verify"
SIGNUP_VERIFY_NEXT_ACTION = "0058da3d16d322c669c30e9298c74fe3436cb50a55"

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STEP 4: Verify OTP and Activate Account")
    parser.add_argument("--otp", required=True, help="OTP code (6 digits)")
    parser.add_argument("--reqid", required=True, help="ReqId from Step 2")
    parser.add_argument("--proxy", help="Proxy URL")

    args = parser.parse_args()

    print("\n" + "="*80)
    print("STEP 4: VERIFY OTP AND ACTIVATE ACCOUNT")
    print("="*80)
    print(f"OTP Code: {args.otp}")
    print(f"ReqId: {args.reqid}")
    print(f"Proxy: {args.proxy if args.proxy else 'None (direct)'}\n")

    # Validate OTP
    if not args.otp.isdigit() or len(args.otp) != 6:
        logger.error(f"✗ Invalid OTP format (must be 6 digits): {args.otp}")
        sys.exit(1)

    # Build payload with OTP and reqid
    payload = json.dumps([{"code": args.otp, "reqId": args.reqid}])

    # Build curl command
    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", "accept: text/x-component",
        "-H", "accept-encoding: gzip, deflate, br, zstd",
        "-H", "accept-language: en-GB,en-US;q=0.9,en;q=0.8",
        "-H", "content-type: text/plain;charset=UTF-8",
        "-H", f"next-action: {SIGNUP_VERIFY_NEXT_ACTION}",
        "-H", "next-router-state-tree: %5B%22%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22signup%22%2C%7B%22children%22%3A%5B%22verify%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "-H", "origin: https://marketing.moceansms.com",
        "-H", "priority: u=1, i",
        "-H", "referer: https://marketing.moceansms.com/signup/verify",
        "-H", "sec-ch-ua: \"Brave\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
        "-H", "sec-ch-ua-mobile: ?0",
        "-H", "sec-ch-ua-platform: \"macOS\"",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-H", "sec-gpc: 1",
        "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "-d", payload,
    ]

    if args.proxy:
        if args.proxy.startswith("socks5://"):
            cmd.extend(["--socks5-hostname", args.proxy])
        else:
            cmd.extend(["-x", args.proxy])

    cmd.append(SIGNUP_VERIFY_URL)

    # Make request
    logger.info(f"POST {SIGNUP_VERIFY_URL}")
    logger.info(f"Payload: {payload}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Log EXACT raw response
    print("="*80)
    print("EXACT RAW RESPONSE:")
    print("="*80)
    print(result.stdout)
    print("="*80 + "\n")

    # Parse response
    print("PARSING RESPONSE:")
    response_data = {}
    for line in result.stdout.split("\n"):
        if line.startswith("1:"):
            try:
                response_data = json.loads(line[2:])
                print(json.dumps(response_data, indent=2))
                break
            except Exception as e:
                logger.error(f"Parse error: {e}")

    # Final result
    print("\n" + "="*80)
    print("RESULT:")
    print("="*80 + "\n")

    if response_data.get("success"):
        logger.success(f"✓ OTP VERIFIED - ACCOUNT ACTIVATED")
        logger.info(f"  Message: {response_data.get('message')}")
        logger.info(f"\n  You can now login with your credentials")
        sys.exit(0)
    else:
        logger.error(f"✗ OTP VERIFICATION FAILED")
        logger.error(f"  Message: {response_data.get('message')}")
        sys.exit(1)
