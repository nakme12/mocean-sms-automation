'use strict';

const Anticaptcha = require("anticaptcha");

/**
 * Captcha Solver Module
 * Handles Turnstile (Cloudflare) challenge resolution via Anti-Captcha.
 */
async function solveTurnstile(apiKey, targetUrl, siteKey) {
  console.log('[Solver] Initializing Anti-Captcha...');
  const ac = new Anticaptcha(apiKey);
  
  try {
    console.log('[Solver] Submitting Turnstile task to worker...');
    
    // TurnstileProxyless is used because we are handling cookies/headers ourselves in middleware
    const token = await ac.solveTurnstileProxyless(targetUrl, siteKey);
    
    if (!token) {
      throw new Error('Received empty token from solver service.');
    }

    console.log('[Solver] Challenge solved! Token length:', token.length);
    return token;
  } catch (err) {
    console.error('[Solver] Error during CAPTCHA resolution:', err.message);
    throw err;
  }
}

module.exports = { solveTurnstile };