# MoceanSMS Authentication Automation

Production-ready authentication flow with support for proxies, CAPTCHA solving, and complete logging.

## 📋 Features

✅ **Signup** - Create new account with automatic CAPTCHA solving  
✅ **OTP Verification** - Verify email via OTP code  
✅ **Sign In** - Login with credentials after account activation  
✅ **Proxy Support** - HTTP and SOCKS5 proxies  
✅ **Structured Logging** - Clear, timestamped output  
✅ **Error Handling** - Robust error recovery  
✅ **Production Ready** - Clean, maintainable code  

## 🚀 Quick Start

### Single Step: Signup Only
```bash
python3 signup.py --email user@example.com --username myuser
```

### Single Step: Sign In
```bash
python3 signin.py --username myuser --password SecurePassword123!
```

### Single Step: Verify OTP
```bash
python3 verify_otp.py --otp 123456 --token <activation_token>
```

### Complete Flow
```bash
python3 authenticate.py \
  --email user@example.com \
  --username myuser \
  --otp 123456 \
  --proxy socks5://user:pass@host:port
```

## 📚 Detailed Usage

### 1. Signup (Create Account)

```bash
python3 signup.py \
  --email wkrish@example.com \
  --username kripant \
  --password SecurePassword123! \
  --proxy socks5://njTBtEIYDd60_custom:2938637@change5.owlproxy.com:7778
```

**Output:**
```
[14:30:15] [INFO ] SIGNUP FLOW STARTED
[14:30:15] [INFO ] Email: wkrish@example.com
[14:30:20] [✓    ] CAPTCHA solved: 1.CaJMeUPBM...
[14:30:25] [✓    ] Signup successful!
[14:30:25] [INFO ] Token: 3067%7CkH7ofQjhW3AOPUQd2uDc...
```

**Options:**
- `--email` (required) - Email address
- `--username` (required) - Username (max 15 chars, alphanumeric)
- `--password` - Password (default: SecurePassword123!)
- `--proxy` - Proxy URL (http://... or socks5://...)
- `--captcha` - Pre-solved CAPTCHA token (skip solving)
- `--random` - Generate random email/username

### 2. Verify OTP

After signup, user receives OTP via email.

```bash
python3 verify_otp.py \
  --otp 123456 \
  --token 3067%7CkH7ofQjhW3AOPUQd2uDcogCR3eox... \
  --proxy socks5://...
```

**Options:**
- `--otp` (required) - 6-digit OTP code from email
- `--token` (required) - Activation token from signup
- `--proxy` - Proxy URL

### 3. Sign In

After OTP verification, account is activated and can sign in.

```bash
python3 signin.py \
  --username kripant \
  --password SecurePassword123! \
  --proxy socks5://...
```

**Options:**
- `--username` (required) - Username
- `--password` (required) - Password
- `--proxy` - Proxy URL

### 4. Complete Flow

Run all three steps automatically:

```bash
python3 authenticate.py \
  --email user@example.com \
  --username myuser \
  --password SecurePassword123! \
  --otp 123456 \
  --proxy socks5://...
```

**Or with random credentials:**
```bash
python3 authenticate.py --random --otp 123456 --proxy socks5://...
```

## 🔐 Proxy Configuration

### HTTP Proxy
```bash
--proxy http://user:pass@proxy.com:8080
```

### SOCKS5 Proxy (Recommended)
```bash
--proxy socks5://user:pass@proxy.com:7778
```

**Example (OWLProxy):**
```bash
--proxy socks5://njTBtEIYDd60_custom_zone_MY_st__city_sid_56716521_time_90:2938637@change5.owlproxy.com:7778
```

## 🔑 Environment Variables

Create `.env` file in the script directory:

```bash
ANTICAPTCHA_KEY=your_api_key_here
SITE_KEY=0x4AAAAAABkK8iPAGoGsGhNf
```

## 📊 Output Format

All scripts output JSON for easy parsing:

```json
{
  "success": true,
  "email": "user@example.com",
  "username": "myuser",
  "activation_token": "3067%7CkH7ofQjhW3AOPUQd2uDc..."
}
```

## ⚠️ Error Handling

**429 Error** (Too Many Registrations):
- Rate limit from server due to multiple signup attempts
- Solution: Wait 30-60 minutes before retrying with different email/username
- Or: Use proxy with different IP address

**CAPTCHA Failure**:
- Anti-Captcha API key may be rate-limited
- Solution: Use different CAPTCHA service or API key

**Timeout**:
- Proxy or server connection slow
- Solution: Increase timeout or use different proxy

## 📝 Script Details

### signup.py
- **Purpose**: Create new account
- **Time**: ~25-30 seconds (includes CAPTCHA solving)
- **Return**: activation_token for OTP verification

### verify_otp.py
- **Purpose**: Verify OTP code
- **Time**: ~5 seconds
- **Tries**: Multiple endpoints automatically

### signin.py
- **Purpose**: Sign in after account activation
- **Time**: ~20-25 seconds (includes CAPTCHA solving)
- **Return**: Session status

### authenticate.py
- **Purpose**: Complete flow (Signup → OTP → Signin)
- **Time**: ~60 seconds + user OTP input time
- **Return**: Summary of all three steps

## 🛠️ Troubleshooting

### "ANTICAPTCHA_KEY not set"
→ Set in `.env` or environment variable

### "Signup failed: 429"
→ Rate limited by server, wait 1 hour or use different proxy

### "Request timeout"
→ Proxy or network issue, try different proxy or direct connection

### "OTP verification failed on all endpoints"
→ Invalid OTP or activation token, check both values

### "Signin failed: 500"
→ Account not fully activated yet, ensure OTP verification completed

## 📞 Support

For issues:
1. Check error message in logs
2. Verify proxy connectivity
3. Ensure credentials are correct
4. Try without proxy (if not required)
5. Check ANTICAPTCHA_KEY is valid

---

**Status**: ✅ Production Ready  
**Last Updated**: 2026-04-30  
**Version**: 2.0 (Refactored & Enhanced)
