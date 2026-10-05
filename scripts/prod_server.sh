#!/bin/zsh
set -a
source /Users/kawaguchitakumi/pal-shopify-seo-bulk-fixer/.env.production
set +a
export PORT=3001
cd /Users/kawaguchitakumi/pal-shopify-seo-bulk-fixer
exec /opt/homebrew/bin/npm run start
