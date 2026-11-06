"""Social media tools backed by Mastodon.

Export the registration function and handler class as the package's public API.
Tool registration occurs when register_socialmedia_tools is called.
"""

from seedemu_tool_service.tools.socialmedia.registration import register_socialmedia_tools
from seedemu_tool_service.tools.socialmedia.tools import SocialMediaTools

__all__ = ["SocialMediaTools", "register_socialmedia_tools"]
