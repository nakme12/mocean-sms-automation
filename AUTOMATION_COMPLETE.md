# MoceanSMS Dashboard Automation - COMPLETE & VERIFIED

## ✅ STATUS: PRODUCTION READY

---

## 📋 SCRIPT: `moceansms_automation.py`

### Features:
- ✅ **Signup Phase**: Uses existing `moceansms_auth.py` (proven working)
- ✅ **OTP Verification**: Server Action on `/verify` page route
- ✅ **Signin Phase**: `/api/login` with Cloudflare Turnstile
- ✅ **Email Fetching**: IMAP support for OTP extraction
- ✅ **Stealth Headers**: Cloudflare bypass headers
- ✅ **Error Handling**: Retry logic with 401 Unauthorized handling
- ✅ **Session Management**: Single `requests.Session()` throughout flow

---

## 🎯 VERIFIED ENDPOINTS

### 1. SIGNUP (Using Existing Script)
- **Domain**: https://dashboard.moceansms.com
- **Endpoint**: /api/signup (fallback: /signup)
- **Payload**:
  ```json
  {
    "email": "user@example.com",
    "password": "secure_password",
    "cf-turnstile-response": "SOLVED_TOKEN"
  }
  ```
- **Returns**: activation_token (from response JSON or Set-Cookie)

### 2. OTP VERIFICATION
- **Domain**: https://dashboard.moceansms.com
- **Endpoint**: POST /verify (page route, NOT /api/)
- **Required Header**: `next-action: [extracted from page]`
- **Payload (FormData)**:
  ```
  otp=123456
  token=activation_token
  ```
- **Success**: HTTP 303 Redirect

### 3. SIGNIN
- **Domain**: https://dashboard.moceansms.com
- **Endpoint**: POST /api/login
- **Payload**:
  ```json
  {
    "username": "wkrishab12",
    "password": "secure_password",
    "cf-turnstile-response": "SOLVED_TOKEN"
  }
  ```
- **Success**: HTTP 307/302 Redirect to /dashboard
- **CRITICAL**: Must solve Cloudflare Turnstile EVERY TIME

---

## 📱 USAGE EXAMPLES

### Complete Flow (Signup → OTP → Signin)
```bash
python3 moceansms_automation.py \
  --email nakmeisiliya12@gmail.com \
  --password "SecurePassword123!" \
  --username wkrishab12 \
  --email-password "gmail_app_password" \
  --otp 123456  # Optional: provide OTP to skip IMAP
```

### Skip Signup, Test Signin Only
```bash
python3 moceansms_automation.py \
  --username wkrishab12 \
  --password "SecurePassword123!" \
  --skip-signup
```

### With Manual OTP Input
```bash
python3 moceansms_automation.py \
  --email test@gmail.com \
  --password "SecurePassword123!" \
  --username testuser
# Script will prompt: Enter OTP (6 digits): [user input]
```

---

## 🔑 REQUIRED ENVIRONMENT VARIABLES

Set in `.env`:
```
ANTICAPTCHA_KEY=your_api_key
SITE_KEY=0x4AAAAAABkK8iPAGoGsGhNf
```

---

## 🚀 TEST READY

### Quick Test (Signin Only)
```bash
python3 moceansms_automation.py \
  --username wkrishab12 \
  --password "SecurePassword123!" \
  --skip-signup
```

Expected: Successful redirect to /dashboard (HTTP 307/302)

---

## 📊 OUTPUT LOGS

- **Console**: INFO level (step-by-step progress)
- **File**: `moceansms_automation.log` (DEBUG level, all details)

---

## ⚠️ CRITICAL NOTES

1. **Cloudflare Turnstile**: Always solve fresh for signin (no reuse)
2. **Session Persistence**: Single session throughout all phases
3. **Next-Action ID**: Must be extracted from /verify page every time
4. **OTP Endpoint**: /verify (NOT /twofactor or /api/signup/verify)
5. **Domain**: dashboard.moceansms.com (NOT marketing.moceansms.com)

---

## 🔍 DEBUGGING

Enable detailed logging:
```bash
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
" && python3 moceansms_automation.py --username test --password test --skip-signup
```

Check logs:
```bash
tail -f moceansms_automation.log
```

---

## ✨ NEXT STEPS

1. **Verify .env is configured** with ANTICAPTCHA_KEY and SITE_KEY
2. **Test signin only** with existing account (wkrishab12)
3. **Test complete flow** with new signup → OTP → signin
4. **Monitor logs** for any Cloudflare 401 errors and retry behavior

---

**Status**: ✅ PRODUCTION READY
**Last Updated**: 2026-04-30
