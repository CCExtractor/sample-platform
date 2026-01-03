#!/bin/bash
# Post-deployment health check
# Exit codes: 0 = healthy, 1 = unhealthy (triggers rollback)
#
# This script verifies the deployment was successful by checking:
# 1. The /health endpoint (if available)
# 2. Fallback: the root endpoint responds with 2xx/3xx

set -e

# Configuration
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"
FALLBACK_URL="${FALLBACK_URL:-http://127.0.0.1/}"
MAX_RETRIES="${MAX_RETRIES:-6}"
RETRY_DELAY="${RETRY_DELAY:-5}"

echo "=== Post-deployment health check ==="
echo "Timestamp: $(date -Iseconds)"
echo "Health URL: $HEALTH_URL"
echo "Max retries: $MAX_RETRIES"
echo "Retry delay: ${RETRY_DELAY}s"

# Wait for application to start
echo ""
echo "Waiting for application to initialize..."
sleep 3

# Check health endpoint with retries
echo ""
echo "--- Health check ---"
for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i/$MAX_RETRIES..."

    # Try the /health endpoint first (use -L to follow HTTP->HTTPS redirects)
    HTTP_CODE=$(curl -sL -o /tmp/health_response.json -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        echo "✓ Health check passed (HTTP $HTTP_CODE)"
        echo ""
        echo "Response:"
        cat /tmp/health_response.json 2>/dev/null | python3 -m json.tool 2>/dev/null || cat /tmp/health_response.json
        echo ""
        echo "=== Deployment verified successfully ==="
        exit 0
    elif [ "$HTTP_CODE" = "404" ]; then
        # Health endpoint doesn't exist, try fallback (use -L to follow redirects)
        echo "Health endpoint not found, trying fallback URL..."
        HTTP_CODE=$(curl -sL -o /dev/null -w "%{http_code}" "$FALLBACK_URL" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 400 ]; then
            echo "✓ Fallback check passed (HTTP $HTTP_CODE)"
            echo ""
            echo "=== Deployment verified successfully (using fallback) ==="
            exit 0
        fi
    elif [ "$HTTP_CODE" = "503" ]; then
        echo "Health check returned unhealthy (HTTP 503)"
        echo "Response:"
        cat /tmp/health_response.json 2>/dev/null || echo "(no response body)"
    fi

    if [ "$i" -lt "$MAX_RETRIES" ]; then
        echo "Health check returned HTTP $HTTP_CODE, retrying in ${RETRY_DELAY}s..."
        sleep "$RETRY_DELAY"
    fi
done

echo ""
echo "=== HEALTH CHECK FAILED ==="
echo "Health check failed after $MAX_RETRIES attempts"
echo "Last HTTP code: $HTTP_CODE"
echo "Last response:"
cat /tmp/health_response.json 2>/dev/null || echo "(no response)"
echo ""
echo "Deployment verification FAILED - rollback recommended"
exit 1
