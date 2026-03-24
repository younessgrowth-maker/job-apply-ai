#!/bin/bash
# Lance claude-code-proxy pour utiliser l'abonnement Max comme API
# Le proxy expose http://127.0.0.1:4523 (compatible SDK Anthropic)

echo "Démarrage du Claude Max Proxy sur http://127.0.0.1:4523 ..."
echo "Ctrl+C pour arrêter"
echo ""

cd ~/tools/claude-code-proxy
REQUIRE_AUTH=false exec node dist/index.js
