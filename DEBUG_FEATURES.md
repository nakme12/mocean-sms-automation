# MoceanSMS Auth Script - Debugging & Auto-Retry Features

## Overview
The updated `moceansms_auth.py` script now includes comprehensive debugging capabilities and intelligent auto-retry logic to handle common registration errors.

---

## 1. FULL RESPONSE LOGGING

**Feature:** Every API response is printed to console with clear DEBUG labels.

```
[DEBUG] Full Response Body:
======================================================================
0:"[{"message":"registration_failed","code":400}]"
1:"message":"Registration failed: Multiple accounts detected"
2:"success":false
======================================================================
```

**Location:** Printed to STDERR immediately after each signup submission
**File Saved:** `last_response.txt` (in the same directory)

---

## 2. RAW JSON PARSING

**Feature:** Aggressively searches for `success":false` anywhere in the response.

```python
# Pattern detection:
raw_success_false = re.search(r'success"\s*:\s*false', response.text)

if raw_success_false:
    # Error found! Extract message and handle it
```

**Why:** Next.js streaming format doesn't always have clean JSON structure.

---

## 3. ERROR EXTRACTION & COLORED OUTPUT

**Feature:** Extracts error messages and prints them in RED BOLD text.

```
[ERROR] Registration failed: Multiple accounts detected
^
RED + BOLD for visibility
```

**Message Extraction Methods:**
1. Look for `"message":""` field
2. Look for `"error":""` field  
3. Look for `"description":""` field
4. Greedy fallback for any "Registration..." text

---

## 4. AUTO-RETRY WITH RANDOM DATA

**When Triggered:**
- Error contains: "multiple account" (case-insensitive)
- Script detects: `success":false`

**What Happens:**
```
❌ Registration failed: Multiple accounts detected

[RETRY] Attempting signup with random credentials:
  New Username: user7a2f5k9m
  New Email: test8x9q2r5n@gmail.com

[*] Refreshing page and Turnstile token for retry...
[*] Retrying signup with random data...

[DEBUG] Full Response Body:
[New response from server]
```

**Random Data Generation:**
- **Username:** `user` + 8 random alphanumeric characters
  - Example: `user7a2f5k9m`
- **Email:** `test` + 10 random alphanumeric + `@gmail.com`
  - Example: `test8x9q2r5n@gmail.com`

---

## 5. RESPONSE FILE SAVING

**Feature:** Every response is automatically saved to `last_response.txt` for manual review.

**Location:** Same directory as `moceansms_auth.py`
**Updated:** After every signup attempt

**Usage:**
```bash
# After running the script, review:
cat last_response.txt

# Search for errors:
grep -i "error\|failed" last_response.txt
```

---

## Complete Flow Diagram

```
STEP 3: Submit Signup
  ↓
[DEBUG] Print Full Response Body
  ↓
Save to last_response.txt
  ↓
Check HTTP Status
  ├─ IF 429 (Rate Limited):
  │   └─ Print RED error + Exit
  │
  └─ Parse response for 'success":false'
      ├─ IF Found:
      │   ├─ Extract error message
      │   ├─ Print in RED BOLD
      │   └─ IF "multiple account":
      │       ├─ Generate random username/email
      │       ├─ Refresh Turnstile
      │       ├─ Retry signup
      │       ├─ [DEBUG] Print retry response
      │       └─ Save retry response
      │   └─ IF other error:
      │       └─ Exit with error details
      │
      └─ IF Not Found:
          └─ Continue to OTP verification
```

---

## Example Output

### Scenario 1: Multiple Accounts Error (with successful retry)

```
[STEP 3] Submitting signup form...
[*] POSTing signup payload with complete registration data...
[*] Username: Pratik_Automation_User

[DEBUG] Full Response Body:
======================================================================
{"success":false,"message":"Registration failed: Multiple accounts detected"}
======================================================================
[+] Response saved to: /Users/mac/Downloads/New status/last_response.txt

[ERROR] Registration failed: Multiple accounts detected

[!] Detected 'Multiple accounts' error. Retrying with completely random data...
[RETRY] Attempting signup with random credentials:
  New Username: user7a2f5k9m
  New Email: test8x9q2r5n@gmail.com

[*] Refreshing page and Turnstile token for retry...
[*] Retrying signup with random data...

[DEBUG] Full Response Body:
======================================================================
{"success":true,"redirect":"/verify"}
======================================================================
[+] Response saved to: /Users/mac/Downloads/New status/last_response.txt

[+] Retry succeeded!

[STEP 4] Checking for OTP/Verification requirement...
[!] OTP verification detected
```

### Scenario 2: Rate Limited (429)

```
[STEP 3] Submitting signup form...

[*] Submission response status: 429

[DEBUG] Full Response Body:
======================================================================
<html><body>429 Too Many Requests</body></html>
======================================================================

[ERROR] IP is being rate limited (429 Too Many Requests)

[ERROR] IP is rate limited (429). Switch VPN/Proxy and try again.

Response Status: 429
Error: rate_limited
Message: Your IP is being rate limited. Please switch to a different VPN or proxy and try again.
```

---

## Debugging Tips

### 1. Check the Full Response
```bash
cat last_response.txt | grep -i "success\|error\|message"
```

### 2. Look for Streaming Format Issues
```bash
# Check if response has streaming markers
cat last_response.txt | grep -E "^[0-9]+:"
```

### 3. Parse JSON manually
```bash
# Try to extract the JSON part
cat last_response.txt | sed 's/^[0-9]://' | jq .
```

### 4. Monitor Retry Attempts
```bash
# Run script and save full output
/Library/Developer/CommandLineTools/usr/bin/python3 moceansms_auth.py 2>&1 | tee full_run.log
```

---

## Configuration

No additional configuration needed. All debugging features are:
- ✅ **Always enabled** (cannot be disabled)
- ✅ **Non-blocking** (printed to STDERR, JSON to STDOUT)
- ✅ **Automatic** (no user intervention required)

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - Account created & OTP verified |
| 1 | Failure - Error during registration or retry |
| 1 | 429 - Rate limited (switch VPN/proxy) |

