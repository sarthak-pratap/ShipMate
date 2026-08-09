#!/usr/bin/env bash
set -e

echo "🚀 Importing Zerops project & provisioning services..."
zcli project project-import zerops-project-import.yml

echo "📦 Building & deploying API service..."
zcli push api

echo "📦 Building & deploying Web service..."
zcli push web

echo "📦 Building & deploying Worker service..."
zcli push worker

echo "✅ All services successfully deployed to Zerops!"
