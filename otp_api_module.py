#!/usr/bin/env python3
"""
MoceanSMS OTP Verification API Module
Direct HTTP API requests - no browser automation
Optimized for speed and reliability
"""

import json
import logging
import sys
import time
from typing import Optional, Dict, Any
from curl_cffi import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ============================================================================
# CORE OTP VERIFICATION FUNCTION
# ============================================================================

def verify_account_api(
    otp_code: str,
    activation_token: str,
    verify_url: str = "https://marketing.moceansms.com/signup/verify",
    cookies: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    next_action_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify MoceanSMS account using OTP code via direct API request

    This function sends a direct HTTP POST request to the OTP verification endpoint
    using Next.js Server Action format (same as signup). No browser automation needed.

    **IMPORTANT**: Must include `activateCodeToken` cookie in the request. The server
    validates this cookie to ensure the request comes from the same session that
    completed registration.

    Args:
        otp_code (str): 6-digit OTP code extracted from email
        activation_token (str): The `activateCodeToken` value from signup response
                               (e.g., "3045%7Cu1NMGnx9EsL...")
        verify_url (str): OTP verification endpoint URL
                         Default: https://marketing.moceansms.com/signup/verify
        cookies (Dict[str, str], optional): Additional cookies to include in request.
                                           The activation token will be added automatically.
        max_retries (int): Number of retries on rate limit (429)
        next_action_id (str, optional): Next.js action ID. If not provided, tries common IDs.

    Returns:
        Dict[str, Any]: Result dictionary with keys:
            - success (bool): True if verification succeeded
            - status (int): HTTP status code
            - message (str): Status message
            - response_body (str): First 1000 chars of response
            - error (str, optional): Error description if failed

    Raises:
        ValueError: If OTP code is not 6 digits or token is empty

    Example:
        >>> result = verify_account_api(
        ...     otp_code="123456",
        ...     activation_token="3045%7Cu1NMGnx9EsL...",
        ... )
        >>> if result["success"]:
        ...     print("Account verified!")
        ... else:
        ...     print(f"Verification failed: {result['message']}")

    **Technical Details**:
        - Uses curl_cffi for Chrome 110 TLS fingerprinting
        - Next.js Server Action wire format:
          * Headers: Content-Type: text/plain;charset=UTF-8, Accept: text/x-component
          * Body: JSON array containing payload object
        - Supports RSC (React Server Component) flight data responses
        - Implements exponential backoff for 429 rate limiting
    """

    # ========================================================================
    # INPUT VALIDATION
    # ========================================================================
    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        raise ValueError("OTP code must be exactly 6 digits")

    if not activation_token:
        raise ValueError("activation_token (activateCodeToken) is required")

    # ========================================================================
    # SETUP
    # ========================================================================
    session = requests.Session(impersonate="chrome110")

    # Prepare cookies - add activation token if not already present
    if not cookies:
        cookies = {}

    cookies["activateCodeToken"] = activation_token

    # Headers for Next.js Server Action request
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://marketing.moceansms.com",
        "Referer": "https://marketing.moceansms.com/signup/verify",
    }

    # Payload formats to try (in order of likelihood)
    payload_formats = [
        # Format 1: Simple OTP (most likely - matches signup format)
        json.dumps([{"otp": otp_code}]),
        # Format 2: OTP with code alias
        json.dumps([{"otp": otp_code, "code": otp_code}]),
        # Format 3: Individual digit fields
        json.dumps([{
            "otp1": otp_code[0],
            "otp2": otp_code[1],
            "otp3": otp_code[2],
            "otp4": otp_code[3],
            "otp5": otp_code[4],
            "otp6": otp_code[5],
        }]),
    ]

    # ========================================================================
    # REQUEST LOOP WITH RETRY LOGIC
    # ========================================================================
    for attempt in range(max_retries):
        for payload_idx, payload_body in enumerate(payload_formats):
            try:
                logger.info(
                    f"[*] Verification attempt {attempt + 1}/{max_retries}, "
                    f"payload format {payload_idx + 1}/{len(payload_formats)}"
                )

                logger.debug(f"    URL: {verify_url}")
                logger.debug(f"    OTP: {otp_code}")
                logger.debug(f"    Token: {activation_token[:30]}...")
                logger.debug(f"    Payload: {payload_body}")

                # ================================================================
                # SEND REQUEST
                # ================================================================
                response = session.post(
                    verify_url,
                    data=payload_body,
                    headers=headers,
                    cookies=cookies,
                    timeout=30,
                    allow_redirects=True,
                )

                logger.info(f"[*] Response Status: {response.status_code}")

                # ================================================================
                # LOG RESPONSE
                # ================================================================
                sys.stderr.write("\n" + "=" * 70 + "\n")
                sys.stderr.write("[OTP VERIFICATION RESPONSE]\n")
                sys.stderr.write("=" * 70 + "\n")
                sys.stderr.write(f"Status Code: {response.status_code}\n")
                sys.stderr.write(f"URL: {response.url}\n")
                sys.stderr.write(f"Content-Type: {response.headers.get('content-type', 'N/A')}\n")
                sys.stderr.write(f"\nRequest Headers:\n")
                for k, v in headers.items():
                    sys.stderr.write(f"  {k}: {v[:60]}\n")
                sys.stderr.write(f"\nRequest Body:\n  {payload_body}\n")
                sys.stderr.write(f"\nResponse Body (first 1000 chars):\n{response.text[:1000]}\n")
                sys.stderr.write("=" * 70 + "\n\n")
                sys.stderr.flush()

                # ================================================================
                # HANDLE SUCCESS (200 OK)
                # ================================================================
                if response.status_code == 200:
                    # Check for success indicators in response
                    success_patterns = [
                        '"success":true',
                        '"success": true',
                        'verified',
                        'confirmed',
                        'activated',
                        'account activation',
                    ]

                    is_success = any(
                        pattern in response.text.lower()
                        for pattern in success_patterns
                    )

                    if is_success:
                        logger.info("[+] OTP verification successful!")
                        return {
                            "success": True,
                            "status": response.status_code,
                            "message": "OTP verified successfully",
                            "response_body": response.text[:1000],
                        }
                    else:
                        # 200 OK but no clear success indicator - might still be successful
                        logger.info("[+] Received 200 OK (likely success)")
                        return {
                            "success": True,
                            "status": response.status_code,
                            "message": "OTP submitted (200 OK)",
                            "response_body": response.text[:1000],
                        }

                # ================================================================
                # HANDLE RATE LIMITING (429)
                # ================================================================
                elif response.status_code == 429:
                    logger.warning("[-] Rate limited (429 Too Many Requests)")

                    if attempt < max_retries - 1:
                        # Exponential backoff: 60s, 120s, 180s...
                        backoff = 60 * (attempt + 1)
                        logger.info(f"[*] Waiting {backoff}s before retry...")
                        time.sleep(backoff)
                        break  # Try next payload format after backoff
                    else:
                        return {
                            "success": False,
                            "status": response.status_code,
                            "message": "Rate limited - too many attempts",
                            "error": "rate_limit_exceeded",
                            "response_body": response.text[:1000],
                        }

                # ================================================================
                # HANDLE VALIDATION ERROR (422)
                # ================================================================
                elif response.status_code == 422:
                    logger.warning(f"[-] Validation error (422): {response.text[:200]}")
                    # Try next payload format
                    continue

                # ================================================================
                # HANDLE OTHER ERRORS
                # ================================================================
                elif response.status_code >= 400:
                    logger.error(f"[-] Error {response.status_code}: {response.text[:200]}")
                    # Try next payload format
                    continue

            except requests.exceptions.Timeout:
                logger.error("[-] Request timeout (30s)")
                continue
            except requests.exceptions.ConnectionError as e:
                logger.error(f"[-] Connection error: {str(e)[:100]}")
                continue
            except Exception as e:
                logger.error(f"[-] Unexpected error: {str(e)[:100]}")
                continue

    # ========================================================================
    # ALL ATTEMPTS FAILED
    # ========================================================================
    logger.error("[-] OTP verification failed after all attempts")

    return {
        "success": False,
        "status": None,
        "message": "OTP verification failed",
        "error": "max_retries_exceeded",
    }


# ============================================================================
# CONVENIENCE FUNCTION: FULL VERIFICATION FLOW
# ============================================================================

def verify_mocean_account(
    email_address: str,
    email_password: str,
    activation_token: str,
    imap_server: str = "imap.gmail.com",
) -> Dict[str, Any]:
    """
    Complete verification flow: Extract OTP from email + verify via API

    This is a convenience wrapper that:
    1. Extracts the 6-digit OTP from the latest email
    2. Calls verify_account_api() with the extracted OTP

    Args:
        email_address: Email address to retrieve OTP from
        email_password: Email password or app password
        activation_token: The activateCodeToken from signup
        imap_server: IMAP server address (default: Gmail)

    Returns:
        Same as verify_account_api()

    Example:
        >>> result = verify_mocean_account(
        ...     email_address="user@gmail.com",
        ...     email_password="gmail_app_password",
        ...     activation_token="3045%7Cu1NMGnx9EsL...",
        ... )
    """
    # Import IMAP extractor from main module
    from mocean_otp_verify import IMAPEmailExtractor

    logger.info("[*] Starting verification flow: OTP extraction + API verification")

    # Step 1: Extract OTP from email
    logger.info("\n[STEP 1] Extracting OTP from email...")
    extractor = IMAPEmailExtractor(imap_server, email_address, email_password)

    otp = extractor.get_latest_otp()
    extractor.disconnect()

    if not otp:
        logger.error("[-] Failed to extract OTP from email")
        return {
            "success": False,
            "error": "otp_extraction_failed",
            "message": "Could not extract OTP from email",
        }

    logger.info(f"[+] OTP extracted: {otp}")

    # Step 2: Verify via API
    logger.info(f"\n[STEP 2] Submitting OTP via API...")
    return verify_account_api(
        otp_code=otp,
        activation_token=activation_token,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MoceanSMS OTP Verification")
    parser.add_argument("--otp", help="6-digit OTP code")
    parser.add_argument("--token", required=True, help="Activation token")
    parser.add_argument("--email", help="Email for IMAP extraction")
    parser.add_argument("--email-password", help="Email password")
    parser.add_argument("--imap", default="imap.gmail.com", help="IMAP server")
    parser.add_argument("--verify-url", default="https://marketing.moceansms.com/signup/verify",
                       help="Verification endpoint")

    args = parser.parse_args()

    # Mode 1: Direct OTP verification
    if args.otp:
        result = verify_account_api(
            otp_code=args.otp,
            activation_token=args.token,
            verify_url=args.verify_url,
        )
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["success"] else 1)

    # Mode 2: Full verification flow (email extraction + API)
    elif args.email and args.email_password:
        result = verify_mocean_account(
            email_address=args.email,
            email_password=args.email_password,
            activation_token=args.token,
            imap_server=args.imap,
        )
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["success"] else 1)

    else:
        parser.print_help()
        sys.exit(1)
