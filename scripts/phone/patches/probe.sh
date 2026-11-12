#!/data/data/com.termux/files/usr/bin/bash
R=/data/data/com.termux/files/usr/lib/node_modules/dsh-termux/node_modules/@deepseek-ai
echo "=== instructions filenames ==="
grep -oE '"[A-Za-z0-9._-]+\.md"' "$R/dsh-agent-instructions/lib/index.js" | sort -u | head -20
echo "=== 现有 AGENTS.md ==="
ls -l ~/AGENTS.md ~/.dsh/AGENTS.md "$HOME/dsh日常工作区/AGENTS.md" 2>/dev/null
echo "=== 装 python-pptx / python-docx ==="
pip install --quiet python-pptx python-docx 2>&1 | tail -4
python -c "import pptx,docx;print('PPTX_DOCX_OK',pptx.__version__)" 2>&1 | tail -3
