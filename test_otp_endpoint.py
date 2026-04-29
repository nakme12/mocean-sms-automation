#!/usr/bin/env python3
"""
Test and identify MoceanSMS OTP Verification Endpoint
Determines exact API format required for verification
"""

import json
import logging
import re
import sys
from typing import Optional, Dict, Any
from curl_cffi import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================================================
# OTP VERIFICATION ENDPOINT TESTING
# ============================================================================

def test_verify_endpoint(
    otp_code: str,
    activation_token: str,
    base_url: str = "https://marketing.moceansms.com",
) -> Dict[str, Any]:
    """
    Test different OTP verification endpoint configurations

    Args:
        otp_code: 6-digit OTP
        activation_token: Activation token from signup
        base_url: Base URL of the service

    Returns:
        Dict with test results showing which endpoint/format works
    """

    session = requests.Session(impersonate="chrome110")

    # Test configurations
    endpoints = [
        "/signup/verify",
        "/api/auth/verify",
        "/api/verify",
        "/verify",
    ]

    payloads = [
        # Format 1: Simple OTP object
        json.dumps([{"otp": otp_code}]),
        # Format 2: OTP with code field
        json.dumps([{"otp": otp_code, "code": otp_code}]),
        # Format 3: Individual digits
        json.dumps([{
            "otp1": otp_code[0],
            "otp2": otp_code[1],
            "otp3": otp_code[2],
            "otp4": otp_code[3],
            "otp5": otp_code[4],
            "otp6": otp_code[5],
        }]),
        # Format 4: With activation token
        json.dumps([{"otp": otp_code, "activateCodeToken": activation_token}]),
        # Format 5: Form data style
        json.dumps([{"token": activation_token, "otp": otp_code}]),
    ]

    headers_configs = [
        # Config 1: Next.js Server Action (text/plain)
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://marketing.moceansms.com",
            "Referer": "https://marketing.moceansms.com/signup/verify",
        },
        # Config 2: Standard JSON
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://marketing.moceansms.com",
        },
        # Config 3: Form urlencoded
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://marketing.moceansms.com",
        },
    ]

    cookies = {"activateCodeToken": activation_token}

    results = {
        "tests": [],
        "successful_configs": [],
        "errors": [],
    }

    print("\n" + "=" * 80)
    print("TESTING OTP VERIFICATION ENDPOINTS")
    print("=" * 80)

    test_count = 0
    for endpoint_idx, endpoint in enumerate(endpoints):
        url = f"{base_url}{endpoint}"

        for payload_idx, payload in enumerate(payloads):
            for header_idx, headers in enumerate(headers_configs):
                test_count += 1
                test_id = f"{endpoint_idx}.{payload_idx}.{header_idx}"

                logger.info(f"\n[TEST {test_count}] {test_id}")
                logger.info(f"  Endpoint: {endpoint}")
                logger.info(f"  Payload format: {payload_idx + 1}")
                logger.info(f"  Headers config: {header_idx + 1}")

                try:
                    response = session.post(
                        url,
                        data=payload,
                        headers=headers,
                        cookies=cookies,
                        timeout=15,
                        allow_redirects=False,
                    )

                    logger.info(f"  Status: {response.status_code}")

                    # Log response snippet
                    response_preview = response.text[:200] if response.text else "(empty)"
                    logger.info(f"  Response: {response_preview}")

                    # Check for success indicators
                    success_indicators = [
                        '"success":true',
                        '"success": true',
                        'verified',
                        'confirmed',
                        'activated',
                    ]

                    is_success = any(indicator in response.text.lower() for indicator in success_indicators)

                    test_result = {
                        "test_id": test_id,
                        "endpoint": endpoint,
                        "payload_format": payload_idx,
                        "headers_config": header_idx,
                        "status": response.status_code,
                        "success": is_success or response.status_code == 200,
                        "response_length": len(response.text),
                        "response_preview": response.text[:500],
                    }

                    results["tests"].append(test_result)

                    if is_success or (response.status_code == 200 and "error" not in response.text.lower()):
                        logger.info(f"  ✓ POTENTIAL SUCCESS!")
                        results["successful_configs"].append({
                            "endpoint": endpoint,
                            "payload_format": payload_idx,
                            "headers_config": header_idx,
                            "status": response.status_code,
                        })

                except Exception as e:
                    logger.error(f"  Error: {str(e)[:100]}")
                    results["errors"].append({
                        "test_id": test_id,
                        "error": str(e)[:200],
                    })

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {test_count}")
    print(f"Successful configs: {len(results['successful_configs'])}")
    print(f"Errors: {len(results['errors'])}")

    if results["successful_configs"]:
        print("\n✓ SUCCESSFUL CONFIGURATIONS:")
        for config in results["successful_configs"]:
            print(f"  - Endpoint: {config['endpoint']}")
            print(f"    Payload format: {config['payload_format']}")
            print(f"    Headers config: {config['headers_config']}")
            print(f"    Status: {config['status']}")
    else:
        print("\n✗ No successful configurations found")
        print("\nLikely issues:")
        print("  1. OTP code might be incorrect or expired")
        print("  2. Activation token might be invalid")
        print("  3. Endpoint might be different from tested URLs")
        print("  4. Additional headers or parameters might be required")

    return results


def identify_verify_endpoint_from_page(html: str) -> Optional[str]:
    """
    Try to identify the verify endpoint from HTML content

    Args:
        html: HTML content from verify page

    Returns:
        Identified endpoint or None
    """
    patterns = [
        r'/signup/verify',
        r'/api/.*verify',
        r'action["\']?\s*=\s*["\']([^"\']+verify[^"\']*)',
        r'endpoint["\']?\s*[:=]\s*["\']([^"\']+verify[^"\']*)',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            if len(match.groups()) > 0:
                return match.group(1)
            else:
                return match.group(0)

    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test OTP verification endpoints")
    parser.add_argument("--otp", required=True, help="OTP code to test (6 digits)")
    parser.add_argument("--token", required=True, help="Activation token")
    parser.add_argument("--base-url", default="https://marketing.moceansms.com", help="Base URL")

    args = parser.parse_args()

    if len(args.otp) != 6 or not args.otp.isdigit():
        print("Error: OTP must be 6 digits")
        sys.exit(1)

    results = test_verify_endpoint(
        otp_code=args.otp,
        activation_token=args.token,
        base_url=args.base_url,
    )

    # Output results as JSON for analysis
    print("\n" + "=" * 80)
    print("DETAILED RESULTS (JSON)")
    print("=" * 80)
    print(json.dumps(results, indent=2))
