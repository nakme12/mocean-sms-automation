# Next.js Server Actions Login Protocol - Pure API Logic

## Executive Summary
The MoceanSMS login system implements Next.js App Router Server Actions, which use a custom RPC-like protocol. This document details the exact networking sequence required to authenticate via pure HTTP requests without browser automation.

---

## 1. REQUEST FLOW: WHY GET FIRST, THEN POST

### The Two-Phase Flow

#### Phase 1: Initial GET (Session Establishment)
```
GET https://marketing.moceansms.com/en/signin
```

**Why this step is mandatory:**
1. **Cookie Creation**: Server generates and sets HTTP-only cookies
   - `next-auth.csrf-token` - Server's CSRF protection token
   - `next-auth.callback-url` - Post-login redirect target
   - `next-auth.pkce.` - PKCE flow tokens if using OAuth

2. **Server State Preparation**: Server-side session object is created
   - Associates cookies with a server-side session ID
   - Prepares action registry for subsequent requests

3. **Action ID Embedding**: Server embeds next-action IDs in HTML response
   - Allows client to discover valid Server Action function IDs
   - Prevents calling unauthorized/non-existent actions

4. **CSRF Token Acquisition**: The CSRF token is **set as a cookie, not in HTML**
   - Unlike traditional forms, there is no hidden input field
   - Token lives in HTTP-only cookie (cannot be accessed by JavaScript)
   - Token must be sent back in subsequent requests via cookie jar

**Implementation:**
```python
from requests import Session

session = Session()

# Step 1a: GET to establish cookies
response = session.get(
    "https://marketing.moceansms.com/en/signin",
    timeout=15,
    allow_redirects=True
)

# At this point, session.cookies now contains:
# - next-auth.csrf-token
# - next-auth.callback-url
# These will be automatically included in subsequent requests

print(f"Cookies after GET: {dict(session.cookies)}")
```

#### Phase 2: POST (Action Execution)
```
POST https://marketing.moceansms.com/en/signin
```

**What happens:**
1. **Session Validation**: Server validates cookie matches initial request
2. **Action Invocation**: Server executes the login Server Action function
3. **Auth Check**: Credentials are validated against user database
4. **Token Generation**: On success, server generates session token
5. **Response Streaming**: Server responds with text/x-component stream

**Why cookies must persist between requests:**

```python
# WRONG - New session for each request (FAILS)
response1 = requests.get("https://marketing.moceansms.com/en/signin")
response2 = requests.post("https://marketing.moceansms.com/en/signin", data=...)
# ^ response2 has no cookies from response1, POST fails with 403

# CORRECT - Same session object (WORKS)
session = Session()
response1 = session.get("https://marketing.moceansms.com/en/signin")
response2 = session.post("https://marketing.moceansms.com/en/signin", data=...)
# ^ response2 automatically includes cookies from response1
```

---

## 2. THE 'NEXT-ACTION' IDENTIFIER: REPLACING CSRF TOKENS

### Traditional CSRF Tokens vs Next.js Server Actions

| Aspect | Traditional CSRF | Next.js Server Action |
|--------|------------------|----------------------|
| **Location** | Hidden form input | URL query parameter / function registry |
| **Purpose** | Verify form origin | Identify which function to execute |
| **Format** | Random alphanumeric | Deterministic hash/UUID |
| **Validation** | Cryptographic token match | Action ID exists in registry + origin check |
| **Transport** | Form POST body | URL parameter: `?_action=ID` |

### What is next-action?

The **next-action ID** is a 40-64 character hexadecimal string that uniquely identifies a specific Server Action function.

```
Example: 40e92530aa479fd9a04b80dde42c66010d18f4ff51
Pattern: ^[a-f0-9]{40,64}$
```

### How next-action Works

1. **Action Registry on Server**
   ```
   Server maintains a registry:
   {
     "40e92530aa479fd9a04b80dde42c66010d18f4ff51": loginServerAction,
     "a1b2c3d4e5f6...": signupServerAction,
     ...
   }
   ```

2. **Client Discovery of Action IDs**
   - During GET request, server embeds action IDs in HTML
   - Client extracts these IDs via regex/parsing
   - Client passes extracted ID in POST request

3. **Server-Side Validation**
   ```python
   # Server pseudocode on receiving POST
   action_id = request.query.get("_action")

   if action_id not in ACTION_REGISTRY:
       return 404  # Invalid action

   if not validate_origin_and_referer(request):
       return 403  # CSRF check

   if not validate_cookies(request):
       return 403  # Session invalid

   # All checks pass, execute action
   action_function = ACTION_REGISTRY[action_id]
   result = action_function(request.body)
   ```

### CSRF Protection Mechanism

Unlike traditional CSRF tokens (which are cryptographic), Next.js Server Actions use **origin-based CSRF protection**:

```python
# Server-side CSRF validation
def validate_server_action_request(request):
    # Check 1: Origin header must match target domain
    origin = request.headers.get("Origin")
    if origin != "https://marketing.moceansms.com":
        raise CSRFError("Invalid origin")

    # Check 2: Referer header must be same-origin
    referer = request.headers.get("Referer")
    if not referer.startswith("https://marketing.moceansms.com"):
        raise CSRFError("Invalid referer")

    # Check 3: CSRF token cookie must exist
    csrf_token = request.cookies.get("next-auth.csrf-token")
    if not csrf_token:
        raise CSRFError("No CSRF token")

    # Check 4: Action must be registered
    action_id = request.query.get("_action")
    if action_id not in REGISTRY:
        raise CSRFError("Unknown action")

    return True
```

### Why next-action Replaces Traditional CSRF

1. **Binding to Specific Function**: CSRF protection is tied to which function is being called
2. **Server Maintains Registry**: Only registered actions can be invoked
3. **Origin-Based Validation**: Cross-origin requests are automatically rejected
4. **No Token Extraction Needed**: Token lives in HTTP-only cookies, not transmitted in body

---

## 3. PAYLOAD SPECIFICS: TEXT/PLAIN AND STRINGIFIED ARRAYS

### The Critical Format Difference

#### ❌ FAILS: Standard JSON object
```
POST /en/signin?_action=40e92530aa479fd9a04b80dde42c66010d18f4ff51
Content-Type: application/json

{"username":"wkrishab12v2","password":"SecurePassword123!"}

Response: 400 Bad Request or silent failure
```

**Why it fails**: Next.js Server Actions expect a **stringified array**, not a plain object.

#### ✅ WORKS: Stringified array
```
POST /en/signin?_action=40e92530aa479fd9a04b80dde42c66010d18f4ff51
Content-Type: text/plain;charset=UTF-8

[{"username":"wkrishab12v2","password":"SecurePassword123!"}]

Response: 200 OK or 302 Redirect
```

### Why Stringified Array Format?

#### Reason 1: RPC Argument Encoding
```javascript
// Server-side: the action function signature
export default async function loginAction(payload) {
  const { username, password } = payload;
  // ...
}

// The array format allows multiple arguments:
// [arg1, arg2, arg3] -> function(arg1, arg2, arg3)
// For login: [payload] -> function(payload)
```

#### Reason 2: Wire Format Consistency
```
Next.js uses a custom wire format for Server Actions:

Single argument:  [{ username: "...", password: "..." }]
Multiple args:    [{ username: "..." }, { password: "..." }]
With primitives:  ["string_arg", 123, true, { object }]

All arguments wrapped in a JSON array, then stringified.
```

#### Reason 3: Type Safety
```python
# The stringified format preserves type information
# [{"key": "value"}]  -> dict passed to server
# ["string"]          -> string passed to server
# [123]               -> number passed to server
# [true]              -> boolean passed to server

# Parsing on server:
payload = json.loads(request.body)
arg1 = payload[0]  # First argument
```

### Implementation in Python

```python
import json

# Step 1: Create payload object
login_payload = {
    "username": "wkrishab12v2",
    "password": "SecurePassword123!"
}

# Step 2: Wrap in array
payload_array = [login_payload]

# Step 3: Stringify (CRITICAL)
body_string = json.dumps(payload_array)

# Result: '[{"username":"wkrishab12v2","password":"SecurePassword123!"}]'

# Step 4: Send as text/plain (NOT application/json)
response = session.post(
    url,
    data=body_string,  # Raw string
    headers={"Content-Type": "text/plain;charset=UTF-8"}
)
```

### Common Mistakes

```python
# WRONG 1: Using requests json parameter
session.post(url, json=payload)
# ^ This sets Content-Type: application/json and sends plain object

# WRONG 2: Not wrapping in array
session.post(url, data=json.dumps(payload))
# ^ Missing array wrapper

# WRONG 3: Not stringifying
session.post(url, data=[payload])
# ^ Sends binary-encoded bytes, not JSON string

# CORRECT
session.post(
    url,
    data=json.dumps([payload]),  # Stringified array
    headers={"Content-Type": "text/plain;charset=UTF-8"}
)
```

---

## 4. HEADER DEPENDENCIES: SECURITY CHECKS

### The Four Critical Headers

#### Header 1: Content-Type: text/plain;charset=UTF-8

```
Purpose: Signals this is a Server Action RPC call
Why: Distinguishes from traditional form submissions
Validation: Server checks if value is exactly "text/plain;charset=UTF-8"
```

**Technical reason:**
```
Content-Type: application/json     -> traditional REST API
Content-Type: application/x-www-form-urlencoded -> form submission
Content-Type: text/plain           -> Server Action RPC call
```

**Validation on server:**
```python
# Server pseudocode
content_type = request.headers.get("Content-Type", "")

if "text/plain" not in content_type:
    return 400  # Invalid content type
```

#### Header 2: Accept: text/x-component

```
Purpose: Instructs server to respond in streaming component format
Why: Server knows to use Next.js RSC (React Server Component) protocol
Value: MUST be exactly "text/x-component"
```

**Response format:**
```
HTTP/1.1 200 OK
Content-Type: text/x-component
Transfer-Encoding: chunked

[server component stream data]
```

**Validation on server:**
```python
accept = request.headers.get("Accept", "")

if "text/x-component" not in accept:
    # May downgrade response format or return error
    return 406  # Not Acceptable
```

#### Header 3: Origin

```
Purpose: CSRF protection - ensures request comes from same-origin
Requirement: MUST match the target domain exactly
Value: https://marketing.moceansms.com (no path, no port unless non-standard)
```

**Domain matching logic:**
```python
origin = request.headers.get("Origin")
target = "https://marketing.moceansms.com"

# Server checks:
if origin != target:
    return 403  # Forbidden - CSRF violation

# This blocks:
# ❌ https://example.com/phishing
# ❌ https://marketing.moceansms.com.attacker.com
# ❌ http://marketing.moceansms.com  (wrong protocol)
# ❌ https://marketing.moceansms.com:8080  (different port)

# This allows:
# ✅ https://marketing.moceansms.com
# ✅ https://marketing.moceansms.com/en/signin  (path ignored)
```

#### Header 4: Referer

```
Purpose: Additional CSRF check, ensures user initiated from legitimate page
Requirement: MUST be from same origin or legitimately linked
Value: https://marketing.moceansms.com/en/signin
```

**Validation:**
```python
referer = request.headers.get("Referer", "")

# Must match origin
if not referer.startswith("https://marketing.moceansms.com"):
    return 403  # CSRF violation

# Server accepts:
# ✅ https://marketing.moceansms.com/en/signin
# ✅ https://marketing.moceansms.com/dashboard
# ✅ https://marketing.moceansms.com/

# Server rejects:
# ❌ https://attacker.com/phishing
# ❌ (missing referer)
```

### The Secret Mechanism: HTTP-Only Cookies

```python
# Headers alone don't validate CSRF, cookies do:

# Server sends in GET response:
Set-Cookie: next-auth.csrf-token=abc123xyz; HttpOnly; Secure; SameSite=Lax

# Browser/session automatically includes in POST:
Cookie: next-auth.csrf-token=abc123xyz

# Server validates:
# 1. Origin header = target domain ✅
# 2. Referer header = target domain ✅
# 3. Cookie next-auth.csrf-token exists ✅
# 4. Action ID is registered ✅
# ALL PASS -> execute action
```

### Complete Required Header Set

```python
headers = {
    # Critical for Server Action identification
    "Content-Type": "text/plain;charset=UTF-8",
    "Accept": "text/x-component",

    # Critical for CSRF protection
    "Origin": "https://marketing.moceansms.com",
    "Referer": "https://marketing.moceansms.com/en/signin",

    # Required for browser mimicking
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",

    # Additional fetch metadata (modern security)
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Site": "same-origin",

    # Cache control
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
```

---

## 5. RESPONSE HANDLING: PARSING TEXT/X-COMPONENT STREAM

### Response Structure

```
HTTP/1.1 200 OK
Content-Type: text/x-component
Content-Length: 1234

[streaming component data]
```

### Response Parsing Strategy

```python
def parse_server_action_response(response):
    """
    Parse Next.js Server Action response
    """

    # Check 1: Status code
    if response.status_code not in [200, 302, 307]:
        return {
            "success": False,
            "status": response.status_code,
            "error": "HTTP error"
        }

    # Check 2: Redirect response (successful authentication)
    if response.status_code in [302, 307]:
        redirect_url = response.headers.get("Location")
        return {
            "success": True,
            "type": "redirect",
            "url": redirect_url,
            "message": f"Redirect to {redirect_url}"
        }

    # Check 3: Response body content type
    content_type = response.headers.get("Content-Type", "")
    if "text/x-component" not in content_type:
        return {
            "success": False,
            "error": f"Unexpected content type: {content_type}"
        }

    # Check 4: Parse response body
    body = response.text

    # Indicators of success
    success_indicators = [
        "redirect" in body.lower(),
        "success" in body.lower(),
        "authenticated" in body.lower(),
        response.status_code == 200
    ]

    # Indicators of failure
    error_indicators = [
        "invalid" in body.lower(),
        "error" in body.lower(),
        "failed" in body.lower(),
        "unauthorized" in body.lower(),
        "incorrect" in body.lower()
    ]

    if any(error_indicators):
        return {
            "success": False,
            "type": "authentication_error",
            "body": body[:200]
        }

    # Check 5: Verify new session token was set
    new_cookies = dict(response.cookies)
    has_session_token = any(
        "session" in key.lower() or "auth" in key.lower()
        for key in new_cookies.keys()
    )

    return {
        "success": True if any(success_indicators) else False,
        "type": "text_x_component",
        "new_cookies": new_cookies,
        "body_preview": body[:300],
        "has_session_token": has_session_token
    }
```

### Typical Successful Responses

#### Response Type 1: 302 Redirect (Most Common)
```
HTTP/1.1 302 Found
Location: https://marketing.moceansms.com/dashboard
Set-Cookie: next-auth.session-token=eyJhbGc...; HttpOnly; Secure
Content-Type: text/x-component

[empty or minimal body]
```

**Interpretation:**
```python
if response.status_code == 302:
    redirect_url = response.headers.get("Location")
    # Authentication successful, client should navigate to redirect_url
    # Session token is now in cookies
```

#### Response Type 2: 200 Success with Body
```
HTTP/1.1 200 OK
Content-Type: text/x-component
Set-Cookie: next-auth.session-token=xyz...

3:I{"type":"redirect","url":"https://marketing.moceansms.com/dashboard"}
```

**Interpretation:**
```python
if response.status_code == 200:
    body = response.text
    # Parse the streaming format
    # 3:I indicates a JSON object in React Server Component format
    # Extract redirect URL from body
```

#### Response Type 3: 200 OTP Required
```
HTTP/1.1 200 OK
Content-Type: text/x-component

2:I{"type":"otp_required","message":"OTP sent to email"}
```

**Interpretation:**
```python
if "otp" in response.text.lower():
    # Login triggered OTP flow
    # Next step: verify OTP code
```

#### Response Type 4: 401 Invalid Credentials
```
HTTP/1.1 401 Unauthorized
Content-Type: text/x-component

1:E{"error":"Invalid username or password","type":"AuthError"}
```

**Interpretation:**
```python
if response.status_code == 401:
    # Authentication failed, invalid credentials
```

### Complete Response Handler Implementation

```python
def handle_server_action_response(response):
    """
    Complete handler for Server Action login response
    """

    import json
    import re

    result = {
        "status_code": response.status_code,
        "success": False,
        "type": None,
        "data": None,
        "action": None
    }

    # Type 1: Redirect response (status 302/307)
    if response.status_code in [302, 307]:
        result["success"] = True
        result["type"] = "redirect"
        result["action"] = "navigate"
        result["data"] = {
            "url": response.headers.get("Location"),
            "method": "GET"
        }
        return result

    # Type 2: Success response (status 200)
    if response.status_code == 200:
        body = response.text.strip()

        # Parse React Server Component format
        # Format: "TYPE:MARKER{json}"
        # Example: '3:I{"type":"redirect","url":"..."}'

        match = re.search(r'"type":"(\w+)"', body)
        if match:
            response_type = match.group(1)
            result["type"] = response_type

            if response_type == "redirect":
                url_match = re.search(r'"url":"([^"]+)"', body)
                if url_match:
                    result["success"] = True
                    result["action"] = "navigate"
                    result["data"] = {"url": url_match.group(1)}

            elif response_type == "otp_required":
                result["success"] = True
                result["action"] = "verify_otp"
                result["data"] = body

            elif response_type == "error":
                result["success"] = False
                result["action"] = "error"
                msg_match = re.search(r'"message":"([^"]+)"', body)
                result["data"] = msg_match.group(1) if msg_match else body

    # Type 3: Error responses
    elif response.status_code in [400, 401, 403, 404, 500]:
        result["success"] = False
        result["type"] = "error"
        result["data"] = {
            "status": response.status_code,
            "body": response.text[:200]
        }

    return result
```

---

## SUMMARY: THE COMPLETE PROTOCOL

```
1. GET https://marketing.moceansms.com/en/signin
   ↓ (Session established, cookies set, action IDs embedded)

2. Parse HTML, extract next-action ID
   ↓ (Regex search for hex string)

3. POST https://marketing.moceansms.com/en/signin?_action=ID
   Headers:
   - Content-Type: text/plain;charset=UTF-8
   - Accept: text/x-component
   - Origin: https://marketing.moceansms.com
   - Referer: https://marketing.moceansms.com/en/signin

   Body: [{"username":"...","password":"..."}]
   ↓ (Request validated server-side via cookies + origin + action registry)

4. Receive response
   ↓ 302 Redirect with Location header
      → Navigate to dashboard (successful login)
   ↓ 200 with text/x-component containing OTP requirement
      → Proceed to OTP verification
   ↓ 401 with error message
      → Invalid credentials
```

This is the complete networking protocol for Next.js Server Actions login via pure API.

