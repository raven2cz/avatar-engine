#!/usr/bin/env python3
"""
Avatar MCP Tools
================

Example MCP server providing tools for avatar application.
These tools allow the AI to interact with your avatar system.

Usage:
    python mcp_tools.py

Configure in config.yaml:
    mcp_servers:
      avatar-tools:
        command: "python"
        args: ["mcp_tools.py"]

Author: raven2cz
License: MIT
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

# Try to import MCP SDK
try:
    from mcp.server import Server, InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, ServerCapabilities, ToolsCapability
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    print("Warning: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("avatar.mcp")


# ============================================================================
# Avatar Tools Implementation
# ============================================================================

class AvatarTools:
    """
    Collection of tools for avatar control.
    
    These tools can be called by the AI to perform actions
    in your avatar application.
    """
    
    def __init__(self):
        self.api_url = os.environ.get("AVATAR_API_URL", "http://localhost:8000/api")
        self.current_emotion = "neutral"
        self.speaking = False
    
    async def speak(self, text: str, emotion: str = "neutral", speed: float = 1.0) -> Dict[str, Any]:
        """
        Make avatar speak text with emotion.
        
        Args:
            text: Text to speak
            emotion: Emotion (neutral, happy, sad, angry, surprised)
            speed: Speech speed (0.5-2.0)
        """
        logger.info(f"Avatar speaks: '{text}' (emotion: {emotion}, speed: {speed})")
        
        self.current_emotion = emotion
        self.speaking = True
        
        # In real implementation, call your avatar API here
        # response = await httpx.post(f"{self.api_url}/speak", json={...})
        
        return {
            "success": True,
            "text": text,
            "emotion": emotion,
            "speed": speed,
            "timestamp": datetime.now().isoformat()
        }
    
    async def set_emotion(self, emotion: str) -> Dict[str, Any]:
        """
        Set avatar emotion without speaking.
        
        Args:
            emotion: Emotion to set
        """
        valid_emotions = ["neutral", "happy", "sad", "angry", "surprised", "thinking"]
        
        if emotion.lower() not in valid_emotions:
            return {
                "success": False,
                "error": f"Invalid emotion. Valid: {valid_emotions}"
            }
        
        self.current_emotion = emotion.lower()
        logger.info(f"Avatar emotion set to: {self.current_emotion}")
        
        return {
            "success": True,
            "emotion": self.current_emotion
        }
    
    async def gesture(self, gesture_name: str, intensity: float = 1.0) -> Dict[str, Any]:
        """
        Perform a gesture.
        
        Args:
            gesture_name: Name of gesture (wave, nod, shake_head, point, thumbs_up)
            intensity: Gesture intensity (0.0-1.0)
        """
        valid_gestures = ["wave", "nod", "shake_head", "point", "thumbs_up", "think"]
        
        if gesture_name.lower() not in valid_gestures:
            return {
                "success": False,
                "error": f"Invalid gesture. Valid: {valid_gestures}"
            }
        
        logger.info(f"Avatar gesture: {gesture_name} (intensity: {intensity})")
        
        return {
            "success": True,
            "gesture": gesture_name.lower(),
            "intensity": min(1.0, max(0.0, intensity))
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current avatar status."""
        return {
            "success": True,
            "status": {
                "emotion": self.current_emotion,
                "speaking": self.speaking,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    async def play_animation(self, animation_name: str) -> Dict[str, Any]:
        """
        Play a predefined animation.
        
        Args:
            animation_name: Name of animation to play
        """
        logger.info(f"Playing animation: {animation_name}")
        
        return {
            "success": True,
            "animation": animation_name,
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# System Tools
# ============================================================================

class SystemTools:
    """
    System interaction tools.
    """
    
    async def get_time(self) -> Dict[str, Any]:
        """Get current time and date."""
        now = datetime.now()
        return {
            "success": True,
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "day_of_week": now.strftime("%A"),
            "timestamp": now.isoformat()
        }
    
    async def run_command(self, command: str) -> Dict[str, Any]:
        """
        Run a shell command (with safety restrictions).
        
        Args:
            command: Command to run
        """
        # Safety: Only allow specific safe commands
        allowed_prefixes = ["ls", "pwd", "date", "whoami", "echo", "cat"]
        
        cmd_parts = command.split()
        if not cmd_parts or cmd_parts[0] not in allowed_prefixes:
            return {
                "success": False,
                "error": f"Command not allowed. Allowed: {allowed_prefixes}"
            }
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode('utf-8'),
                "stderr": stderr.decode('utf-8'),
                "returncode": process.returncode
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Command timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================================
# MCP Server
# ============================================================================

def create_mcp_server() -> 'Server':
    """Create MCP server with all tools registered."""
    if not HAS_MCP:
        raise ImportError("MCP SDK not installed")
    
    server = Server("avatar-tools")
    avatar = AvatarTools()
    system = SystemTools()
    
    @server.list_tools()
    async def list_tools():
        """List available tools."""
        return [
            Tool(
                name="avatar_speak",
                description="Trigger avatar's text-to-speech and lip-sync animation. Use ONLY when user explicitly requests the avatar to speak aloud, for TTS output, or for voice announcements. Do NOT use for regular text responses.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text for avatar to speak aloud via TTS"
                        },
                        "emotion": {
                            "type": "string",
                            "description": "Emotion: neutral, happy, sad, angry, surprised",
                            "default": "neutral"
                        },
                        "speed": {
                            "type": "number",
                            "description": "Speech speed (0.5-2.0)",
                            "default": 1.0
                        }
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="avatar_emotion",
                description="Change avatar's facial expression/mood. Use when user explicitly asks the avatar to show an emotion or change its visual mood.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "description": "Emotion to display: neutral, happy, sad, angry, surprised, thinking"
                        }
                    },
                    "required": ["emotion"]
                }
            ),
            Tool(
                name="avatar_gesture",
                description="Trigger avatar body animation (wave, nod, etc). Use when user explicitly requests a physical gesture or body movement.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "gesture_name": {
                            "type": "string",
                            "description": "Gesture: wave, nod, shake_head, point, thumbs_up, think"
                        },
                        "intensity": {
                            "type": "number",
                            "description": "Gesture intensity (0.0-1.0)",
                            "default": 1.0
                        }
                    },
                    "required": ["gesture_name"]
                }
            ),
            Tool(
                name="avatar_status",
                description="Get current avatar state (emotion, speaking status). Use for diagnostics or when user asks about avatar's current state.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="avatar_animation",
                description="Play a predefined avatar animation sequence. Use when user requests a specific animation by name.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "animation_name": {
                            "type": "string",
                            "description": "Name of animation to play"
                        }
                    },
                    "required": ["animation_name"]
                }
            ),
            Tool(
                name="system_time",
                description="Get current system time, date and day of week. Use when user asks about current time or date.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="system_command",
                description="Run a safe shell command (ls, pwd, date, whoami, echo, cat only). Use only when user explicitly requests to run a system command.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to run"
                        }
                    },
                    "required": ["command"]
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]):
        """Handle tool calls."""
        try:
            if name == "avatar_speak":
                result = await avatar.speak(
                    text=arguments["text"],
                    emotion=arguments.get("emotion", "neutral"),
                    speed=arguments.get("speed", 1.0)
                )
            elif name == "avatar_emotion":
                result = await avatar.set_emotion(arguments["emotion"])
            elif name == "avatar_gesture":
                result = await avatar.gesture(
                    gesture_name=arguments["gesture_name"],
                    intensity=arguments.get("intensity", 1.0)
                )
            elif name == "avatar_status":
                result = await avatar.get_status()
            elif name == "avatar_animation":
                result = await avatar.play_animation(arguments["animation_name"])
            elif name == "system_time":
                result = await system.get_time()
            elif name == "system_command":
                result = await system.run_command(arguments["command"])
            else:
                result = {"success": False, "error": f"Unknown tool: {name}"}
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            return [TextContent(type="text", text=json.dumps(error_result))]
    
    return server


async def main():
    """Run MCP server."""
    if not HAS_MCP:
        print("Error: MCP SDK not installed. Run: pip install mcp")
        sys.exit(1)

    logger.info("Starting Avatar MCP Server...")

    server = create_mcp_server()

    # Create initialization options for MCP 1.x
    init_options = InitializationOptions(
        server_name="avatar-tools",
        server_version="1.0.0",
        capabilities=ServerCapabilities(
            tools=ToolsCapability()
        )
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
