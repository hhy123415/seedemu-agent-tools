"""Register social media tools with explicit input models."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.socialmedia.models import (
    AccountFollowArguments,
    AccountLookupArguments,
    AccountStatusesArguments,
    StatusCreateArguments,
    StatusContextArguments,
    StatusFavouriteArguments,
    StatusReadArguments,
    StatusReblogArguments,
    TimelineReadArguments,
)
from seedemu_tool_service.tools.socialmedia.tools import SocialMediaTools


def register_socialmedia_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Bind operations to the shared runtime backend and registry.

    Create one handler instance and associate each public tool name with its
    bound method. ToolDefinition supplies discovery metadata; arguments_model
    supplies input validation and its schema.
    """
    tools = SocialMediaTools(backend)
    registry.register(
        ToolDefinition(
            name="socialmedia.timeline_read",
            domain="socialmedia",
            description=(
                "Read one public or home timeline page. "
                "Home requires a user token with read:statuses."
            ),
        ),
        handler=tools.timeline_read,
        arguments_model=TimelineReadArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.status_create",
            domain="socialmedia",
            description=(
                "Publish one text post or reply as the token owner; requires write:statuses. "
                "No automatic retries. Reuse the same idempotency_key only for the same post. "
                "If outcome_unknown is true, the write may already have happened."
            ),
        ),
        handler=tools.status_create,
        arguments_model=StatusCreateArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.account_lookup",
            domain="socialmedia",
            description=(
                "Look up a known username or username@domain; requires read:accounts. Does "
                "not resolve unknown remote accounts."
            ),
        ),
        handler=tools.account_lookup,
        arguments_model=AccountLookupArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.account_statuses",
            domain="socialmedia",
            description=(
                "Read one page of an account's posts; private posts require read:statuses and"
                " visibility permission."
            ),
        ),
        handler=tools.account_statuses,
        arguments_model=AccountStatusesArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.status_read",
            domain="socialmedia",
            description=(
                "Read a post by ID; private posts require read:statuses and visibility "
                "permission."
            ),
        ),
        handler=tools.status_read,
        arguments_model=StatusReadArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.status_context",
            domain="socialmedia",
            description=(
                "Read a post's visible ancestors and replies; private posts require "
                "read:statuses."
            ),
        ),
        handler=tools.status_context,
        arguments_model=StatusContextArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.status_favourite",
            domain="socialmedia",
            description=(
                "Favourite a post, or undo with enabled=false; requires write:favourites. No "
                "automatic retries."
            ),
        ),
        handler=tools.status_favourite,
        arguments_model=StatusFavouriteArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.status_reblog",
            domain="socialmedia",
            description=(
                "Boost a post, or undo with enabled=false; requires write:statuses. No "
                "automatic retries."
            ),
        ),
        handler=tools.status_reblog,
        arguments_model=StatusReblogArguments,
    )
    registry.register(
        ToolDefinition(
            name="socialmedia.account_follow",
            domain="socialmedia",
            description=(
                "Follow an account, or unfollow with enabled=false; requires write:follows. "
                "requested=true means pending approval. No automatic retries."
            ),
        ),
        handler=tools.account_follow,
        arguments_model=AccountFollowArguments,
    )
