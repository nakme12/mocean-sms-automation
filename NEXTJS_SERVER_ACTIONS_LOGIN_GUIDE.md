# Next.js Server Actions Login - Technical Implementation Guide

## Overview
Next.js App Router Server Actions use a special wire format for RPC calls. Unlike traditional forms or REST APIs, they require:
1. **Initial session capture** via GET request
2. **Next-Action ID discovery** from page HTML or response headers
3. **Specific headers** that identify the request as a Server Action call
4. **Stringified array payload** format (not JSON object)
5. **text/x-component response parsing**

---

## 1. INITIAL SESSION CAPTURE

### Purpose
Establish session cookies and capture initial request context.

### HTTP Request
```
GET https://marketing.moceansms.com/en/signin
```

### Headers
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}
```

### Session Management
```python
from requests import Session

session = Session()
session.headers.update(headers)

# Capture initial page
response = session.get("https://marketing.moceansms.com/en/signin", timeout=15)
# Session now contains: cookies, default headers
```

### What Happens
- Server sets `next-auth.csrf-token` cookie
- Server sets `next-auth.callback-url` cookie
- Page HTML is rendered with embedded next-action IDs

---

## 2. NEXT-ACTION ID DISCOVERY

### Purpose
Find the Server Action function ID for the login action.

### Two Discovery Methods

#### Method A: Extract from HTML Response Body
```python
import re

def extract_next_action_ids(html_content):
    """Extract all next-action IDs from page HTML"""

    # Pattern: Next.js encodes actions in special format
    # Look for hex strings (32-64 chars) that appear in action contexts
    patterns = [
        # Direct action ID references
        r'"([a-f0-9]{32,64})"',
        # In data attributes
        r'data-action="([a-f0-9]{32,64})"',
        # In form attributes
        r'formAction="([a-f0-9]{32,64})"',
        # In script tags
        r'__NEXT_DATA__.*?"actions":\s*\{[^}]*"([a-f0-9]{32,64})"',
    ]

    found_ids = []
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        found_ids.extend(matches)

    return list(set(found_ids))  # Remove duplicates
```

#### Method B: Extract from Request Headers
```python
def extract_from_response_headers(response):
    """
    Some versions of Next.js include action ID in response headers:
    - x-action-id
    - x-server-action
    """
    action_id = (
        response.headers.get('x-action-id') or
        response.headers.get('x-server-action') or
        response.headers.get('x-next-action')
    )
    return action_id
```

#### Method C: Use Known/Previously Captured ID
```python
# If you've previously captured the action ID, reuse it
# Format: 32-64 character hex string
LOGIN_ACTION_ID = "40e92530aa479fd9a04b80dde42c66010d18f4ff51"
```

### Typical Action IDs Format
```
Length: 32-64 hexadecimal characters
Pattern: ^[a-f0-9]{32,64}$
Example: 40e92530aa479fd9a04b80dde42c66010d18f4ff51
```

---

## 3. API REQUEST CONSTRUCTION

### Target URL
```
POST https://marketing.moceansms.com/en/signin
```

**CRITICAL**: Use the same URL as the GET request (with `/en/` prefix)

### Mandatory Headers

```python
headers = {
    # CRITICAL: Identifies this as a Next.js Server Action RPC call
    "Content-Type": "text/plain;charset=UTF-8",
    "Accept": "text/x-component",

    # CSRF Protection
    "Origin": "https://marketing.moceansms.com",
    "Referer": "https://marketing.moceansms.com/en/signin",

    # Browser Mimicking
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",

    # Server Action Metadata
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Site": "same-origin",
}
```

### Request Construction

```python
def construct_server_action_request(session, action_id, **action_params):
    """
    Construct a Next.js Server Action request

    Args:
        session: requests.Session object with active cookies
        action_id: The next-action ID (hex string)
        **action_params: Arguments to pass to the Server Action function

    Returns:
        dict with: url, headers, data, cookies
    """

    # Build the request URL with action ID as query parameter
    url = f"https://marketing.moceansms.com/en/signin?_action={action_id}"

    # Critical headers for Server Action
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "text/x-component",
        "Origin": "https://marketing.moceansms.com",
        "Referer": "https://marketing.moceansms.com/en/signin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Payload: STRINGIFIED ARRAY FORMAT (NOT plain JSON object)
    # This is the critical difference from standard API calls
    payload = [action_params]  # Wrap in array
    payload_str = json.dumps(payload)  # Stringify as JSON string

    return {
        "url": url,
        "headers": headers,
        "data": payload_str,  # Raw string, not dict
        "cookies": session.cookies
    }
```

### Execution Example

```python
import json
from requests import Session

# Step 1: Initial session capture
session = Session()
response = session.get("https://marketing.moceansms.com/en/signin")

# Step 2: Extract next-action ID
action_ids = extract_next_action_ids(response.text)
login_action_id = action_ids[0] if action_ids else "40e92530aa479fd9a04b80dde42c66010d18f4ff51"

# Step 3: Construct login request
headers = {
    "Content-Type": "text/plain;charset=UTF-8",
    "Accept": "text/x-component",
    "Origin": "https://marketing.moceansms.com",
    "Referer": "https://marketing.moceansms.com/en/signin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

login_payload = {
    "username": "wkrishab12v2",
    "password": "SecurePassword123!"
}

# CRITICAL: Payload must be stringified array
body = json.dumps([login_payload])

# Step 4: Execute
response = session.post(
    f"https://marketing.moceansms.com/en/signin?_action={login_action_id}",
    data=body,
    headers=headers,
    timeout=15,
    allow_redirects=False
)
```

---

## 4. PAYLOAD STRUCTURE

### Format: Stringified Array
```python
# DO NOT send this (plain object):
{"username": "user", "password": "pass"}

# DO send this (stringified array):
[{"username": "user", "password": "pass"}]

# In raw HTTP:
Content-Type: text/plain;charset=UTF-8

[{"username":"wkrishab12v2","password":"SecurePassword123!"}]
```

### Why Stringified Array?
- Next.js Server Actions use RPC encoding
- Multiple arguments are passed as array elements
- Single function call = one object in array
- Server decodes and passes as: `functionName(...payload[0])`

### Supported Payload Fields
```python
login_payload = {
    "username": "string",        # Required: username or email
    "password": "string",        # Required: password
    "rememberMe": bool,          # Optional: session persistence
    "callbackUrl": "string",     # Optional: post-login redirect
}
```

---

## 5. RESPONSE PARSING

### Response Headers Analysis
```python
def parse_server_action_response(response):
    """
    Parse Next.js Server Action response
    """
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"Location: {response.headers.get('location')}")
    print(f"Set-Cookie: {response.headers.get('set-cookie')}")

    # Success indicators
    success_indicators = {
        "status_200": response.status_code == 200,
        "status_302": response.status_code == 302,  # Redirect
        "status_307": response.status_code == 307,  # Temporary redirect
        "has_location": "location" in response.headers,
        "content_type_match": "text/x-component" in response.headers.get('content-type', '')
    }

    return success_indicators
```

### Response Format: text/x-component
```
Content-Type: text/x-component

[Server-side streamed data]
```

This is a **text/x-component** MIME type response, which is Next.js's internal format for streaming Server Action responses.

### Parsing the Response Body

```python
def parse_response_body(response_text):
    """
    Parse text/x-component response body
    Typically contains:
    - Redirect URL
    - Error messages
    - Session tokens
    """

    # Check for redirect indication
    if "redirect" in response_text.lower():
        import re
        match = re.search(r'redirect["\']?\s*:\s*["\']([^"\']+)["\']', response_text)
        if match:
            return {"type": "redirect", "url": match.group(1)}

    # Check for OTP trigger
    if "otp" in response_text.lower():
        return {"type": "otp_required", "message": response_text}

    # Check for error
    if "error" in response_text.lower():
        return {"type": "error", "message": response_text}

    # Success
    return {"type": "success", "body": response_text}
```

### HTTP Status Code Meanings

| Status | Meaning |
|--------|---------|
| **200** | Action executed successfully, response body contains data |
| **302** | Redirect (check Location header) |
| **307** | Temporary redirect with method preservation |
| **400** | Bad request (invalid payload format) |
| **401** | Unauthorized (invalid credentials) |
| **403** | Forbidden (CSRF token invalid or missing) |
| **404** | Action ID not found |
| **500** | Server error during action execution |

### Cookie Preservation
```python
# After successful login, session object contains:
print(session.cookies)
# Expected: next-auth.session-token=...
#          next-auth.csrf-token=...
#          next-auth.callback-url=...
```

---

## COMPLETE LOGIN FLOW EXAMPLE

```python
import json
import re
import logging
from requests import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NextJSServerActionLogin:
    def __init__(self):
        self.session = Session()
        self.action_id = None
        self.csrf_token = None

    def step1_initial_session(self):
        """Capture initial session and cookies"""
        logger.info("[STEP 1] Capturing initial session...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        response = self.session.get(
            "https://marketing.moceansms.com/en/signin",
            headers=headers,
            timeout=15
        )

        logger.info(f"  Status: {response.status_code}")
        logger.info(f"  Cookies: {dict(self.session.cookies)}")
        return response.status_code == 200

    def step2_extract_action_id(self, html_content):
        """Extract next-action ID from HTML"""
        logger.info("[STEP 2] Extracting next-action ID...")

        patterns = [
            r'"([a-f0-9]{40,64})"',
            r'data-action="([a-f0-9]{40,64})"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                self.action_id = matches[0]
                logger.info(f"  Found: {self.action_id[:20]}...")
                return True

        logger.warning("  Not found in HTML, using fallback")
        self.action_id = "40e92530aa479fd9a04b80dde42c66010d18f4ff51"
        return True

    def step3_login(self, username, password):
        """Execute login Server Action"""
        logger.info("[STEP 3] Executing login...")

        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "text/x-component",
            "Origin": "https://marketing.moceansms.com",
            "Referer": "https://marketing.moceansms.com/en/signin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        payload = [{"username": username, "password": password}]
        body = json.dumps(payload)

        response = self.session.post(
            f"https://marketing.moceansms.com/en/signin?_action={self.action_id}",
            data=body,
            headers=headers,
            timeout=15,
            allow_redirects=False
        )

        logger.info(f"  Status: {response.status_code}")
        logger.info(f"  Content-Type: {response.headers.get('content-type')}")
        logger.info(f"  Body preview: {response.text[:200]}")

        return response.status_code in [200, 302, 307]

    def run(self, username, password):
        """Execute complete login flow"""
        if not self.step1_initial_session():
            logger.error("Step 1 failed")
            return False

        response = self.session.get("https://marketing.moceansms.com/en/signin", timeout=15)
        if not self.step2_extract_action_id(response.text):
            logger.error("Step 2 failed")
            return False

        if not self.step3_login(username, password):
            logger.error("Step 3 failed")
            return False

        logger.info("✓ Login successful")
        return True

# Usage
flow = NextJSServerActionLogin()
flow.run("wkrishab12v2", "SecurePassword123!")
```

---

## KEY TAKEAWAYS

1. **Content-Type MUST be `text/plain;charset=UTF-8`** - This signals a Server Action RPC call
2. **Accept MUST be `text/x-component`** - Server responds with streaming component format
3. **Payload is stringified array, not object** - `[{...}]` not `{...}`
4. **Session persistence is critical** - Use same Session object for all requests
5. **Next-Action ID is required** - Extract from HTML or use fallback
6. **Status codes 200/302/307 indicate success** - Check for redirect URL in headers
7. **CSRF protection relies on Origin/Referer headers** - Not CSRF tokens in traditional sense

