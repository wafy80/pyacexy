#!/bin/bash

# Script per pubblicare pyacexy su GitHub
# Repository: wafy80/pyacexy

set -e

echo "=== Pubblicazione pyacexy su GitHub ==="
echo ""

# Controlla se siamo nella directory corretta
if [ ! -f "setup.py" ] || [ ! -d "pyacexy" ]; then
    echo "❌ Errore: Esegui questo script dalla directory /home/wafy/src/acexy/pyacexy"
    exit 1
fi

echo "✅ Directory corretta verificata"
echo ""

# Controlla se git è inizializzato
if [ ! -d ".git" ]; then
    echo "❌ Errore: Repository git non inizializzato"
    exit 1
fi

echo "✅ Repository git verificato"
echo ""

# Verifica branch
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "⚠️  Branch attuale: $current_branch (dovrebbe essere main)"
    read -p "Vuoi continuare comunque? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📋 Stato del repository:"
git log --oneline -3
echo ""

# Aggiungi remote se non esiste
if ! git remote | grep -q "origin"; then
    echo "➕ Aggiunta remote origin..."
    git remote add origin https://github.com/wafy80/pyacexy.git
    echo "✅ Remote aggiunto"
else
    echo "✅ Remote origin già esistente"
    git remote -v
fi

echo ""
echo "🚀 Pronto per il push!"
echo ""
echo "Opzioni:"
echo "1. Push normale (richiederà le credenziali GitHub)"
echo "2. Mostra il comando da eseguire manualmente"
echo "3. Annulla"
echo ""
read -p "Scegli un'opzione (1-3): " choice

case $choice in
    1)
        echo ""
        echo "Esecuzione push..."
        echo "ℹ️  Ti verrà chiesto username e password (usa un Personal Access Token come password)"
        echo ""
        git push -u origin main
        echo ""
        echo "✅ Repository pubblicato con successo!"
        echo "🌐 Visita: https://github.com/wafy80/pyacexy"
        ;;
    2)
        echo ""
        echo "📝 Esegui manualmente questo comando:"
        echo ""
        echo "    git push -u origin main"
        echo ""
        echo "🔑 Note:"
        echo "  - Username: wafy80"
        echo "  - Password: usa un Personal Access Token da https://github.com/settings/tokens"
        echo "  - Oppure configura SSH: https://docs.github.com/en/authentication/connecting-to-github-with-ssh"
        ;;
    3)
        echo "Operazione annullata"
        exit 0
        ;;
    *)
        echo "❌ Opzione non valida"
        exit 1
        ;;
esac
