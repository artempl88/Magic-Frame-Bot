#!/bin/bash

echo "=== Starting Admin Panel Regression Test ==="
echo "Test started at: $(date)"
echo "Monitoring logs for errors during admin button testing..."
echo ""

# Function to check for new errors in logs
check_logs() {
    echo "=== Checking logs at $(date) ==="
    docker logs --tail=20 magic_frame_bot 2>&1 | grep -E "(ERROR|CRITICAL|Exception|Error)" || echo "No errors found"
    echo ""
}

# Export the function so it can be used
export -f check_logs

echo "Use 'check_logs' command to check for recent errors"
echo "Or run: docker logs --tail=50 magic_frame_bot | grep -E '(ERROR|CRITICAL|Exception)'"
echo ""
echo "ADMIN BUTTONS TO TEST:"
echo "===========================================:"
echo "1.  📊 Statistics"
echo "2.  🔄 Refresh Statistics" 
echo "3.  📊 Detailed Statistics"
echo "4.  📥 Export Statistics"
echo "5.  📢 Broadcast Message"
echo "6.  🎁 Give Credits"
echo "7.  💰 API Balance Check"
echo "8.  💾 Backup Management"
echo "9.  ➕ Create Backup"
echo "10. 📁 List Backups"
echo "11. 📊 Backup Stats"
echo "12. 🧹 Cleanup Backups"
echo "13. 💰 Price Management"
echo "14. 📊 View Current Prices"
echo "15. ✏️ Edit Prices"
echo "16. 💳 YooKassa Settings"
echo "17. 📈 Price History"
echo "18. 🧩 UTM Analytics"
echo "19. ◀️ Navigation buttons"
echo ""
echo "Access admin panel with: /admin"
echo "===========================================:"
