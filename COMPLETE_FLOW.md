# MoceanSMS Complete Registration + OTP Verification Flow

## System Architecture

### Phase 1: Registration (API)
- **Endpoint**: POST `https://marketing.moceansms.com/signup`
- **Format**: Next.js Server Action wire format
- **Input**: Registration form data + Turnstile CAPTCHA token
- **Output**: `success: true` + `activateCodeToken` cookie

### Phase 2: OTP Verification (API)
- **Endpoint**: POST `https://marketing.moceansms.com/signup/verify` (or auto-detected)
- **Format**: Next.js Server Action format
- **Input**: OTP code + `activateCodeToken` cookie
- **Output**: Account verified

## Quick Start

### Installation
```bash
pip install curl-cffi anticaptchaofficial
```

### Full Automated Flow (Registration + OTP)
```bash
python3 moceansms_auth.py \
  --email "test@gmail.com" \
  --password "YourPassword123!" \
  --username "testuser123" \
  --mobile "60133251752" \
  --api-key "your_anticaptcha_key" \
  --verify-otp \
  --email-password "your_gmail_app_password"
```

### Step-by-Step Manual

#### Step 1: Registration Only
```bash
python3 moceansms_auth.py \
  --email "test@gmail.com" \
  --api-key "your_anticaptcha_key"
```

Output will include:
```json
{
  "success": true,
  "status": 200,
  "activation_token": "3045%7Cu1NMGnx9EsL...",
  "otp_verified": false,
  "stage": "complete"
}
```

#### Step 2: OTP Verification (Separate)
```bash
python3 mocean_otp_verify.py \
  --email "test@gmail.com" \
  --password "your_gmail_app_password" \
  --token "3045%7Cu1NMGnx9EsL..."
```

Output:
```json
{
  "success": true,
  "status": 200,
  "message": "OTP verified successfully"
}
```

## Key Technical Details

### Registration Request Format
```
POST /signup HTTP/1.1
Content-Type: text/plain;charset=UTF-8
Accept: text/x-component
Next-Action: 40e92530aa479fd9a04b80dde42c66010d18f4ff51
Next-Router-State-Tree: [encoded state]

[{
  "name": "Full Name",
  "username": "username",
  "email": "test@example.com",
  "mobile": "+60123456789",
  "password": "Password123!",
  "confirmPassword": "Password123!",
  "captchaToken": "1.xxxxx...",
  "agreeLicense": true,
  "receiveOffer": false
}]
```

### OTP Verification Request Format
```
POST /signup/verify HTTP/1.1
Content-Type: text/plain;charset=UTF-8
Accept: text/x-component
Cookie: activateCodeToken=3045%7Cu1NMGnx9EsL...

[{
  "otp": "123456"
}]
```

### Response Format
All responses use **Next.js RSC (React Server Component) Flight Data** format with embedded JSON:
```
0:{"a":"$@1","f":"","b":"..."}
1:{"success":true,"message":"...","data":{}}
```

Success indicator: `"success":true` in response body

## Features

### ✅ Registration
- [x] Automatic Turnstile CAPTCHA solving (Anti-Captcha API)
- [x] Proxy rotation (12 Geonix residential proxies)
- [x] Session cookie handling
- [x] Rate-limit detection (429)
- [x] Token reuse to save CAPTCHA costs
- [x] Detailed request/response logging

### ✅ OTP Verification
- [x] IMAP email extraction (Gmail, Outlook, etc.)
- [x] OTP polling with retry logic
- [x] Direct API verification (no browser automation)
- [x] Activation token cookie handling
- [x] Rate-limit backoff (60s exponential)
- [x] Multiple payload format attempts
- [x] Detailed debug logging

## Environment Configuration

### .env File
```bash
# Anti-Captcha
ANTICAPTCHA_KEY=your_api_key

# Turnstile
SITE_KEY=0x4AAAAAABkK8iPAGoGsGhNf

# Target
TARGET_URI=https://marketing.moceansms.com/signup

# Default credentials
MOCEAN_USERNAME=username_max_15_chars
MOCEAN_PASSWORD=YourPassword123!
```

### Gmail App Password Setup
1. Enable 2FA on Gmail account
2. Go to https://myaccount.google.com/security
3. Select "App passwords"
4. Choose "Mail" and "Mac" (or your device)
5. Google generates 16-character password
6. Use that password with `--email-password` flag

## Error Handling

### Registration Errors
| Status | Error | Solution |
|--------|-------|----------|
| 401 | Recaptcha Invalid | Sitekey changed or CAPTCHA API issue |
| 422 | Validation failed | Check field names and lengths |
| 429 | Rate limited | Use proxy or wait before retry |

### OTP Errors
| Status | Error | Solution |
|--------|-------|----------|
| 429 | Too Many Attempts | Wait 60+ seconds before retry |
| 422 | Invalid OTP | Check email for correct code |
| timeout | No response | Verify activation token cookie |

## Debugging

### Enable Verbose Logging
```bash
PYTHONPATH=. python3 moceansms_auth.py \
  --email "test@gmail.com" \
  2>&1 | tee registration.log
```

### Check Request/Response
Both scripts output detailed request/response logs:
- Full headers
- Request body (JSON)
- Response status and body excerpt
- Extracted data (tokens, OTPs, etc.)

### Test Individual Components
```bash
# Test IMAP extraction only
python3 -c "
from mocean_otp_verify import IMAPEmailExtractor
ex = IMAPEmailExtractor('imap.gmail.com', 'user@gmail.com', 'password')
otp = ex.get_latest_otp()
print(f'OTP: {otp}')
"

# Test OTP API submission
python3 -c "
from mocean_otp_verify import MoceanOTPVerifier
v = MoceanOTPVerifier()
result = v.verify_account_api('123456', 'activation_token_here')
print(result)
"
```

## Cost Optimization

### CAPTCHA Token Reuse
Save ~80% on Anti-Captcha costs:
```bash
# Solve once
RESULT=$(python3 moceansms_auth.py --email user1@gmail.com)
TOKEN=$(echo $RESULT | grep -o '"captchaToken":"[^"]*"')

# Reuse for 5 more registrations
for i in {2..6}; do
  python3 moceansms_auth.py --email "user${i}@gmail.com" --token "$TOKEN"
done
```

### Batch Registration
```bash
#!/bin/bash
for i in {1..10}; do
  python3 moceansms_auth.py \
    --email "batch${i}@soppat.com" \
    --username "user${i}" \
    --verify-otp \
    --email-password "your_gmail_app_password" \
    && echo "✓ Registration $i completed" \
    || echo "✗ Registration $i failed"

  # Spacing between requests
  sleep 5
done
```

## Security

- ✅ TLS 1.2+ for all connections
- ✅ Passwords never logged
- ✅ Activation tokens handled in cookies only
- ✅ Email credentials used for IMAP auth only
- ✅ No plaintext storage of secrets

## Support Files

- `moceansms_auth.py` - Main registration script
- `mocean_otp_verify.py` - OTP verification module
- `.env` - Configuration file
- `SETUP_OTP_VERIFICATION.md` - Detailed setup guide
- `COMPLETE_FLOW.md` - This file
