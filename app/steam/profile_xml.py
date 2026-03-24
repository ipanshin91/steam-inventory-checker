from __future__ import annotations

import logging
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from app.core.models import AccountBanStatus, AccountExistsStatus
from app.steam.client import SteamHttpClient
from app.steam.exceptions import ParseError

logger = logging.getLogger(__name__)

_PROFILE_URL = 'https://steamcommunity.com/id/{vanity}/?xml=1'


@dataclass
class ProfileData:
    """Intermediate result of a Steam profile XML fetch."""

    vanity_name: str
    steam_id64: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    exists_status: AccountExistsStatus = AccountExistsStatus.unknown
    ban_status: AccountBanStatus = AccountBanStatus.unknown
    profile_is_public: bool = False
    privacy_state: str = 'private'


class ProfileXmlFetcher:
    """Fetches and parses the Steam community profile XML endpoint."""

    def __init__(self, client: SteamHttpClient) -> None:
        self._client = client

    async def fetch(self, vanity: str, proxy: str | None = None) -> ProfileData:
        """Fetch profile data for the given vanity name."""
        url = _PROFILE_URL.format(vanity=vanity)
        logger.debug(f'Fetching profile XML: {url}')
        xml_text = await self._client.get_text(url, proxy=proxy)
        return _parse(xml_text, vanity)


def _parse(xml_text: str, vanity: str) -> ProfileData:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ParseError(f'Malformed profile XML for {vanity}') from exc

    if root.find('error') is not None:
        logger.debug(f'Profile not found: {vanity}')
        return ProfileData(
            vanity_name=vanity,
            exists_status=AccountExistsStatus.not_found,
        )

    steam_id64 = root.findtext('steamID64')
    display_name = root.findtext('steamID')
    privacy = root.findtext('privacyState', 'private')
    vac_banned = root.findtext('vacBanned', '0') == '1'

    logger.debug(
        f'Profile fetched: vanity={vanity} id64={steam_id64} privacy={privacy} vac={vac_banned}'
    )

    return ProfileData(
        vanity_name=vanity,
        steam_id64=steam_id64,
        display_name=display_name,
        profile_url=f'https://steamcommunity.com/id/{vanity}',
        exists_status=AccountExistsStatus.exists,
        ban_status=AccountBanStatus.vac_banned if vac_banned else AccountBanStatus.not_banned,
        profile_is_public=(privacy == 'public'),
        privacy_state=privacy,
    )
