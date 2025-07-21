#!/bin/bash
echo "🔍 Latest bot activity (last 20 lines):"
docker logs --tail=20 magic_frame_bot | tail -10
echo ""
echo "❌ Any errors in recent logs:"
docker logs --tail=50 magic_frame_bot 2>&1 | grep -E "(ERROR|CRITICAL|Exception|Error)" | tail -5 || echo "✅ No recent errors found"
