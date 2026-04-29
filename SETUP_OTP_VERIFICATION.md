# MoceanSMS OTP Verification Setup Guide

## Installation

### 1. Install Playwright (for automated browser)
```bash
pip install playwright
playwright install chromium
```

### 2. Verify all dependencies
```bash
# Check curl_cffi
python3 -c "from curl_cffi import requests; print('✓ curl_cffi')"

# Check anticaptchaofficial
python3 -c "from anticaptchaofficial.turnstileproxyless import turnstileProxyless; print('✓ anticaptchaofficial')"

# Check playwright
python3 -c "from playwright.async_api import async_playwright; print('✓ playwright')"
```

## Configuration

### Email Setup (Gmail Recommended)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Create App Password**:
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Select "App passwords"
   - Choose "Mail" and "Windows Computer"
   - Google will generate a 16-character password
   - **Use this 16-character password** (not your Gmail password)

### For Other Email Providers
- **Outlook**: Use app passwords (https://account.live.com/slpassport)
- **Yahoo**: Use app passwords (https://login.yahoo.com)
- **ProtonMail**: Requires Bridge or OAuth

## Usage

### Full Automated Registration + OTP Verification

```bash
python3 moceansms_auth.py \
  --email "your_email@gmail.com" \
  --password "YourMoceanPassword" \
  --username "username123" \
  --mobile "60133251752" \
  --api-key "your_anticaptcha_key" \
  --verify-otp \
  --email-password "your_app_password_16_chars"
```

### Step-by-Step Breakdown

#### Step 1: Register Account (without OTP)
```bash
python3 moceansms_auth.py \
  --email "test@gmail.com" \
  --username "testuser" \
  --api-key "your_anticaptcha_key"
```

This will:
- ✅ Solve Turnstile CAPTCHA automatically
- ✅ Submit registration form with proxy rotation
- ✅ Output `activation_token` in response
- 📧 Trigger OTP email to be sent

#### Step 2: Verify OTP (automatic)
```bash
python3 moceansms_auth.py \
  --email "test@gmail.com" \
  --username "testuser" \
  --api-key "your_anticaptcha_key" \
  --verify-otp \
  --email-password "your_gmail_app_password"
```

This will:
- ✅ Do Step 1 (registration)
- 📧 Retrieve OTP from email inbox
- 🤖 Automate OTP entry on verify page
- ✅ Complete account activation

## Command-Line Arguments

### Registration Options
- `--name`: Full name (default: from .env)
- `--email`: Registration email address
- `--username`: Account username (max 15 characters)
- `--password`: Account password
- `--mobile`: Mobile number
- `--api-key`: Anti-Captcha API key
- `--sitekey`: Turnstile sitekey
- `--token`: Reuse existing Turnstile token (saves cost)
- `--proxy`: Use specific proxy (or "disable" for no proxy)

### OTP Verification Options
- `--verify-otp`: Enable automatic OTP verification
- `--email-password`: Email app password (required if using --verify-otp)
- `--imap-server`: IMAP server (default: imap.gmail.com)

## Response Format

### Registration Only
```json
{
  "success": true,
  "status": 200,
  "activation_token": "3045%7Cu1NMGnx9EsL...",
  "otp_verified": false,
  "stage": "complete",
  "error": null
}
```

### With OTP Verification
```json
{
  "success": true,
  "status": 200,
  "activation_token": "3045%7Cu1NMGnx9EsL...",
  "otp_verified": true,
  "stage": "otp_verified",
  "error": null
}
```

## Troubleshooting

### "Too Many Attempts" Error
- Built-in 60-second backoff automatically activates
- Script retries up to 3 times with delays
- If still failing, wait 5-10 minutes before trying new email

### OTP Not Found in Email
1. Check email provider's spam folder
2. Verify IMAP credentials
3. Ensure app password (not main password) for Gmail
4. Try manual email check while script runs

### Playwright Issues
```bash
# Reinstall Playwright
rm -rf ~/.cache/ms-playwright
playwright install chromium
```

### IMAP Connection Failed
1. Verify email and password
2. Check IMAP is enabled in email settings
3. For Gmail: ensure "Less secure app access" enabled or use app password
4. For Outlook: enable IMAP in account settings

## Advanced Usage

### Reuse Turnstile Token (Save Cost)
```bash
# First run - solves CAPTCHA
RESULT=$(python3 moceansms_auth.py --email test1@gmail.com)
TOKEN=$(echo $RESULT | grep -o '"captchaToken":"[^"]*"' | cut -d'"' -f4)

# Second run - reuses token (no CAPTCHA cost)
python3 moceansms_auth.py --email test2@gmail.com --token "$TOKEN"
```

### Batch Registration with OTP
```bash
#!/bin/bash
for i in {1..5}; do
  python3 moceansms_auth.py \
    --email "batch${i}@soppat.com" \
    --username "batchuser${i}" \
    --verify-otp \
    --email-password "your_app_password" \
    || echo "Registration $i failed"
  sleep 10  # Rate limit pause between registrations
done
```

### Custom IMAP Server
```bash
python3 moceansms_auth.py \
  --email "user@yourdomain.com" \
  --verify-otp \
  --email-password "your_password" \
  --imap-server "imap.yourdomain.com"
```

## Architecture

### Signup Flow
1. **Registration** (`moceansms_auth.py`)
   - Proxy rotation (random from pool)
   - Turnstile CAPTCHA solving (Anti-Captcha API)
   - Form submission with Next.js Server Action format
   - Returns: `activation_token` in cookie

2. **OTP Verification** (`mocean_otp_verify.py`)
   - **Email Retrieval** (IMAP)
     - Connect to email server
     - Poll for latest MoceanSMS email
     - Extract 6-digit OTP via regex
     - Fallback: Extract activation link

   - **Browser Automation** (Playwright)
     - Launch Chromium headless browser
     - Set activation token cookie
     - Navigate to `/signup/verify`
     - Fill 6 OTP input fields with human-like delays
     - Click verify button
     - Confirm success

## Security Notes

- ✅ Email passwords stored locally only
- ✅ Activation tokens used for cookies (not stored permanently)
- ✅ IMAP connection via SSL/TLS
- ✅ Playwright runs headless (no visible browser)
- ✅ No credentials logged to output (only tokens)

**Never commit email passwords to git!**

## Cost Optimization

### Anti-Captcha Token Reuse
- Cost per CAPTCHA: ~$0.05 (approx)
- With token reuse: Solve once, use for multiple registrations
- Save up to 80% on CAPTCHA costs

Example:
```bash
# Solve CAPTCHA once
python3 moceansms_auth.py --email reg1@gmail.com > result1.json
TOKEN=$(python3 -c "import json; print(json.load(open('result1.json'))['body'].split('captchaToken')[1])")

# Reuse for 5 more registrations (saves 5x cost)
for i in {2..6}; do
  python3 moceansms_auth.py --email "reg${i}@gmail.com" --token "$TOKEN"
done
```

## Support

For issues with:
- **CAPTCHA**: Check Anti-Captcha dashboard for API errors
- **Email**: Verify IMAP credentials and enable less secure access
- **Browser**: Reinstall Playwright and Chromium
- **Proxies**: Test with `curl` to verify proxy connectivity
