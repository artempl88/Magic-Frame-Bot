from aiohttp import web
import json
from datetime import datetime

async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "magic-frame-bot"
    }, status=200)
