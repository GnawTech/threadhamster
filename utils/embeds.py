# utils/embeds.py
from typing import Any, Optional

import discord


def create_status_embed(
    target_name: str, config: dict[str, Any] | None
) -> discord.Embed:
    """
    Creates a beautiful status embed for a channel/guild.

    Args:
        target_name: Name of the target (e.g., #general).
        config: Configuration dictionary.

    Returns:
        discord.Embed: The formatted embed.
    """
    embed = discord.Embed(
        title=f"Konfiguration: {target_name}",
        color=discord.Color.blue() if config else discord.Color.light_gray(),
        description="Aktuelle Einstellungen für diesen Bereich."
        if config
        else "Keine spezifischen Einstellungen gefunden (Nutzt Standard).",
    )

    if config:
        ls = config.get("lifespan", 0)
        ls_str = f"{ls} Tage" if ls > 0 else "Unendlich (Deaktiviert)"

        embed.add_field(name="📅 Lebensdauer", value=ls_str, inline=True)
        embed.add_field(
            name="🧵 Auto-Thread",
            value="✅ An" if config.get("auto_thread") else "❌ Aus",
            inline=True,
        )
        embed.add_field(
            name="🔒 Thread-Only",
            value="✅ An" if config.get("thread_only") else "❌ Aus",
            inline=True,
        )
        embed.add_field(
            name="👁️ Spoiler-Only",
            value="✅ An" if config.get("spoiler_only") else "❌ Aus",
            inline=True,
        )

        if config.get("manually_archived"):
            embed.add_field(
                name="⚠️ Status",
                value="Manuell archiviert (Ignore Keepalive)",
                inline=False,
            )
    else:
        embed.add_field(
            name="Info",
            value="Verwende `/manage aktion:Setup`, um Regeln zu definieren.",
            inline=False,
        )

    embed.set_footer(text="ThreadHamster UCA System")
    return embed


def create_success_embed(title: str, description: str) -> discord.Embed:
    """Creates a standard success embed."""
    return discord.Embed(
        title=f"✅ {title}", description=description, color=discord.Color.green()
    )


def create_error_embed(title: str, description: str) -> discord.Embed:
    """Creates a standard error embed."""
    return discord.Embed(
        title=f"❌ {title}", description=description, color=discord.Color.red()
    )
