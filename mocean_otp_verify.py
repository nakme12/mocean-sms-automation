#!/usr/bin/env python3
"""
MoceanSMS OTP Verification via API
Direct HTTP requests to verify account (no browser automation)
"""

import email
import imaplib
import json
import logging
import re
import sys
import time
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ============================================================================
# IMPORT ERROR HANDLING
# ============================================================================
try:
    from curl_cffi import requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run:", file=sys.stderr)
    print("  pip install curl-cffi", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# IMAP EMAIL EXTRACTION
# ============================================================================
class IMAPEmailExtractor:
    """Extract OTP from email using IMAP protocol"""

    def __init__(self, imap_server: str, email_address: str, email_password: str):
        self.imap_server = imap_server
        self.email_address = email_address
        self.email_password = email_password
        self.connection = None

    def connect(self) -> bool:
        """Connect to IMAP server"""
        try:
            logger.info(f"[*] Connecting to IMAP server: {self.imap_server}")
            self.connection = imaplib.IMAP4_SSL(self.imap_server, 993)
            self.connection.login(self.email_address, self.email_password)
            logger.info("[+] IMAP login successful")
            return True
        except Exception as e:
            logger.error(f"[-] IMAP connection failed: {e}")
            return False

    def get_latest_otp(
        self, sender: str = "MoceanSMS", max_retries: int = 5, retry_delay: int = 5
    ) -> Optional[str]:
        """
        Poll inbox for latest email and extract OTP

        Args:
            sender: Expected sender name/email
            max_retries: Number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            6-digit OTP code or None if not found
        """
        if not self.connection:
            if not self.connect():
                return None

        for attempt in range(max_retries):
            try:
                logger.info(f"[*] Polling inbox for OTP (attempt {attempt + 1}/{max_retries})...")

                # Select inbox
                self.connection.select("INBOX")

                # Search for emails from sender (case-insensitive)
                status, messages = self.connection.search(None, f'FROM "{sender}"')

                if status != "OK" or not messages[0]:
                    logger.warning(f"[-] No emails from {sender} found, trying broader search...")
                    # Try broader search
                    status, messages = self.connection.search(None, "ALL")

                if status != "OK" or not messages[0]:
                    logger.warning("[-] No emails found in inbox")
                    if attempt < max_retries - 1:
                        logger.info(f"[*] Waiting {retry_delay}s before retry...")
                        time.sleep(retry_delay)
                    continue

                # Get the latest email
                email_ids = messages[0].split()
                latest_email_id = email_ids[-1]

                status, msg_data = self.connection.fetch(latest_email_id, "(RFC822)")

                if status != "OK":
                    logger.error("[-] Failed to fetch email")
                    continue

                # Parse email
                msg = email.message_from_bytes(msg_data[0][1])
                email_body = self._get_email_body(msg)

                logger.info(f"[+] Email received from: {msg.get('From')}")
                logger.info(f"[+] Subject: {msg.get('Subject')}")

                # Extract OTP (6-digit code)
                otp_match = re.search(r'\b(\d{6})\b', email_body)

                if otp_match:
                    otp = otp_match.group(1)
                    logger.info(f"[+] OTP extracted: {otp}")
                    return otp

                logger.warning("[-] No 6-digit OTP found in email body")
                logger.debug(f"Email body preview: {email_body[:500]}")

            except Exception as e:
                logger.error(f"[-] Error during polling: {e}")

            # Retry
            if attempt < max_retries - 1:
                logger.info(f"[*] Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)

        return None

    def _get_email_body(self, msg) -> str:
        """Extract plain text or HTML body from email"""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()

                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
                elif content_type == "text/html":
                    body = part.get_payload(decode=True).decode(errors="ignore")
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore")

        return body

    def disconnect(self):
        """Close IMAP connection"""
        if self.connection:
            try:
                self.connection.close()
                logger.info("[+] IMAP connection closed")
            except Exception as e:
                logger.warning(f"[-] Error closing IMAP: {e}")


# ============================================================================
# OTP VERIFICATION API
# ============================================================================
class MoceanOTPVerifier:
    """Verify OTP via direct API requests"""

    def __init__(self, verify_url: str = "https://marketing.moceansms.com/signup/verify"):
        self.verify_url = verify_url
        self.session = requests.Session(impersonate="chrome110")

    def verify_account_api(
        self, otp_code: str, activation_token: str, cookies: Optional[Dict[str, str]] = None, max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Verify account via API using OTP code

        Args:
            otp_code: 6-digit OTP code
            activation_token: activateCodeToken from registration response
            cookies: Session cookies (will add activation token if provided)
            max_retries: Number of retry attempts for rate limiting

        Returns:
            Dict with success status and response details
        """
        if not cookies:
            cookies = {}

        # Ensure activation token is in cookies
        cookies["activateCodeToken"] = activation_token

        # Prepare headers (Next.js Server Action format)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://marketing.moceansms.com",
            "Referer": "https://marketing.moceansms.com/signup/verify",
        }

        # Prepare payload - try multiple formats to find what works
        payload_formats = [
            # Format 1: Direct OTP in JSON
            json.dumps([{"otp": otp_code, "code": otp_code}]),
            # Format 2: OTP with token
            json.dumps([{"otp": otp_code, "activateCodeToken": activation_token}]),
            # Format 3: Individual digits (if server expects them)
            json.dumps([{"otp1": otp_code[0], "otp2": otp_code[1], "otp3": otp_code[2],
                         "otp4": otp_code[3], "otp5": otp_code[4], "otp6": otp_code[5]}]),
        ]

        for attempt in range(max_retries):
            for payload_idx, payload_body in enumerate(payload_formats):
                try:
                    logger.info(
                        f"[*] Verification attempt {attempt + 1}/{max_retries}, "
                        f"payload format {payload_idx + 1}/{len(payload_formats)}"
                    )

                    logger.info(f"[*] Sending OTP to: {self.verify_url}")
                    logger.debug(f"    Headers: {headers}")
                    logger.debug(f"    Cookies: {cookies}")
                    logger.debug(f"    Body: {payload_body}")

                    response = self.session.post(
                        self.verify_url,
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
                    sys.stderr.write("[OTP RESPONSE DEBUG]\n")
                    sys.stderr.write("=" * 70 + "\n")
                    sys.stderr.write(f"Status Code: {response.status_code}\n")
                    sys.stderr.write(f"URL: {response.url}\n")
                    sys.stderr.write(f"Content-Type: {response.headers.get('content-type', 'N/A')}\n")
                    sys.stderr.write(f"\nResponse Body (first 1000 chars):\n{response.text[:1000]}\n")
                    sys.stderr.write("=" * 70 + "\n\n")
                    sys.stderr.flush()

                    # Check for success
                    if response.status_code == 200:
                        # Parse response
                        try:
                            if "success" in response.text.lower():
                                # Check for success indicator
                                success_match = re.search(
                                    r'"success"\s*:\s*true|"message"\s*:\s*"[^"]*success|verified|completed',
                                    response.text,
                                    re.IGNORECASE,
                                )
                                if success_match:
                                    logger.info("[+] OTP verification successful!")
                                    return {
                                        "success": True,
                                        "status": response.status_code,
                                        "message": "OTP verified successfully",
                                        "response_body": response.text[:1000],
                                    }
                        except:
                            pass

                        # If 200 but not clearly success, might still be success
                        logger.info("[+] Received 200 OK response")
                        return {
                            "success": True,
                            "status": response.status_code,
                            "message": "OTP submitted (check browser for confirmation)",
                            "response_body": response.text[:1000],
                        }

                    # Check for rate limiting
                    elif response.status_code == 429:
                        logger.warning("[-] Rate limited (429)")
                        if attempt < max_retries - 1:
                            backoff = 60 * (attempt + 1)
                            logger.info(f"[*] Waiting {backoff}s before retry...")
                            time.sleep(backoff)
                        continue

                    # Check for bad request
                    elif response.status_code == 422:
                        logger.error(f"[-] Validation error: {response.text[:200]}")
                        # Try next payload format
                        continue

                    # Check for other errors
                    elif response.status_code >= 400:
                        logger.error(f"[-] Error {response.status_code}: {response.text[:200]}")
                        continue

                except Exception as e:
                    logger.error(f"[-] Request exception: {e}")
                    continue

        logger.error("[-] OTP verification failed after all attempts")
        return {
            "success": False,
            "status": None,
            "message": "OTP verification failed",
            "error": "max_retries_exceeded",
        }


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================
def complete_mocean_verification(
    email_address: str,
    email_password: str,
    activation_token: str,
    imap_server: str = "imap.gmail.com",
    verify_url: str = "https://marketing.moceansms.com/signup/verify",
) -> Dict[str, Any]:
    """
    Complete MoceanSMS account verification via API

    Args:
        email_address: Email address for OTP retrieval
        email_password: Email password or app password
        activation_token: activateCodeToken from signup response
        imap_server: IMAP server address
        verify_url: OTP verification API endpoint

    Returns:
        Dict with verification result

    Example:
        result = complete_mocean_verification(
            email_address="user@example.com",
            email_password="gmail_app_password",
            activation_token="3045%7Cu1NMGnx9EsL..."
        )
        if result['success']:
            print("Account verified!")
    """
    logger.info("[=] Starting MoceanSMS OTP Verification [=]")

    if not activation_token:
        logger.error("[-] activation_token is required")
        return {"success": False, "error": "missing_activation_token"}

    # Step 1: Extract OTP from email
    logger.info("\n[STEP 1] Extracting OTP from email...")
    extractor = IMAPEmailExtractor(imap_server, email_address, email_password)

    otp = extractor.get_latest_otp()
    extractor.disconnect()

    if not otp:
        logger.error("[-] Failed to extract OTP from email")
        return {"success": False, "error": "otp_extraction_failed"}

    logger.info(f"[+] OTP extracted: {otp}")

    # Step 2: Verify via API
    logger.info(f"\n[STEP 2] Submitting OTP via API...")
    verifier = MoceanOTPVerifier(verify_url)

    result = verifier.verify_account_api(
        otp_code=otp,
        activation_token=activation_token,
    )

    if result["success"]:
        logger.info("\n[+] Account verification completed successfully!")
    else:
        logger.error("\n[-] Account verification failed")

    return result


# ============================================================================
# CLI INTERFACE
# ============================================================================
def main():
    """CLI interface for testing"""
    import argparse

    parser = argparse.ArgumentParser(description="MoceanSMS OTP Verification (API)")
    parser.add_argument("--email", required=True, help="Email address for OTP")
    parser.add_argument("--password", required=True, help="Email password")
    parser.add_argument("--token", required=True, help="Activation token from registration")
    parser.add_argument("--imap", default="imap.gmail.com", help="IMAP server")
    parser.add_argument("--verify-url", default="https://marketing.moceansms.com/signup/verify",
                        help="OTP verification endpoint")

    args = parser.parse_args()

    result = complete_mocean_verification(
        email_address=args.email,
        email_password=args.password,
        activation_token=args.token,
        imap_server=args.imap,
        verify_url=args.verify_url,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        main()
    else:
        print("Usage: python3 mocean_otp_verify.py --email <email> --password <password> --token <token>")
        sys.exit(1)
