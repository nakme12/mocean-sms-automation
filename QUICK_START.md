# Quick Start Guide - Updated moceansms_auth.py

## Installation

```bash
# 1. Install dependencies
/Library/Developer/CommandLineTools/usr/bin/python3 -m pip install --upgrade curl-cffi anticaptchaofficial python-dotenv

# 2. Copy and configure .env
cp .env.example .env
nano .env
```

## Configuration

Edit `.env` with your credentials:

```bash
ANTICAPTCHA_KEY=YOUR_API_KEY_HERE
SITE_KEY=0x4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
MOCEAN_FULLNAME=Pratik Kumar
MOCEAN_EMAIL=nakmeis.iliya12@gmail.com
MOCEAN_MOBILE=133251752
MOCEAN_USERNAME=Pratik_Automation_User
MOCEAN_PASSWORD=Mmmmmm@12345
MOCEAN_COUNTRY_CODE=+60
TARGET_URI=https://marketing.moceansms.com/signup
```

## Run the Script

```bash
/Library/Developer/CommandLineTools/usr/bin/python3 moceansms_auth.py
```

## What to Expect

### 1. Full Response Logging
Every API response prints with debug label:
```
[DEBUG] Full Response Body:
======================================================================
[Raw response here...]
======================================================================
```

### 2. Automatic Response Saving
File `last_response.txt` is created automatically with full response.

### 3. Error Detection
If `success":false` is found anywhere in response:
```
[ERROR] Registration failed: [extracted message in RED]
```

### 4. Auto-Retry on "Multiple Accounts"
If error mentions "multiple account":
```
[RETRY] Attempting signup with random credentials:
  New Username: user7a2f5k9m
  New Email: test8x9q2r5n@gmail.com
```

### 5. OTP Input Prompt
When OTP is required:
```
============================================================
OTP VERIFICATION REQUIRED
============================================================
Enter OTP received on your email/phone: [awaiting input]
```

## Check Results

### After Success
- Exit code: `0`
- JSON output with session cookies
- File: `last_response.txt` (saved response)

### After Failure
- Exit code: `1`
- Error message in JSON
- File: `last_response.txt` (for debugging)

## Debug Commands

### View last response
```bash
cat last_response.txt
```

### Search for errors in response
```bash
grep -i "error\|failed\|success.*false" last_response.txt
```

### Capture full output
```bash
/Library/Developer/CommandLineTools/usr/bin/python3 moceansms_auth.py 2>&1 | tee full_run.log
cat full_run.log | grep -E "\[ERROR\]|\[DEBUG\]|\[RETRY\]"
```

## Files Created

| File | Purpose |
|------|---------|
| `moceansms_auth.py` | Main script |
| `.env` | Configuration (API keys, credentials) |
| `last_response.txt` | Last API response (for review) |
| `full_run.log` | Full execution log (if you pipe output) |

## Troubleshooting

### 1. "Multiple accounts detected" error
- ✅ Script auto-retries with random username/email
- Check `last_response.txt` to see both attempts

### 2. 429 Rate Limited
- ❌ Switch VPN/Proxy
- Wait 5-10 minutes
- Run script again

### 3. OTP never arrives
- Check spam folder
- Verify email in `.env` is correct
- Check mobile number format: `+60` prefix

### 4. Turnstile solving fails
- Verify Anti-Captcha API key is correct
- Check account balance
- Verify sitekey matches target website

## Example Workflow

```bash
# 1. Setup
cp .env.example .env
nano .env  # Edit with your API keys

# 2. Run with debugging
/Library/Developer/CommandLineTools/usr/bin/python3 moceansms_auth.py 2>&1 | tee run.log

# 3. If "Multiple accounts" error:
#    - Script auto-retries automatically
#    - Check last_response.txt for new credentials used
#    - Continue to OTP step if retry succeeds

# 4. If OTP required:
#    - Enter code when prompted
#    - Script submits OTP automatically

# 5. Review results:
cat last_response.txt  # Check API response
echo $?  # Check exit code (0=success, 1=failure)
```

## JSON Output Examples

### Success
```json
{
  "success": true,
  "status": 200,
  "cookies": {
    "session_id": "...",
    "auth_token": "..."
  },
  "otp_verified": true,
  "stage": "otp_verified"
}
```

### Multiple Accounts Error (before retry)
```json
{
  "success": false,
  "status": 200,
  "error": "Registration failed: Multiple accounts detected",
  "requires_retry": true,
  "stage": "post"
}
```

### Rate Limited
```json
{
  "success": false,
  "error": "rate_limited",
  "message": "Your IP is being rate limited. Please switch to a different VPN or proxy and try again.",
  "status": 429
}
```

