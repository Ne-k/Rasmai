from bs4 import BeautifulSoup
from typing import List, Dict, Tuple, Any
from urllib.parse import urljoin
import re
import logging

from rasmai.config import BROWSER_USER_AGENT, get_maimai_base_url, region_supported, unsupported_region_text
from rasmai.storage.models import PlayerInfo
from rasmai.scraping.scraper.session import PacedSession, SessionRejected, cookie_jar_to_header, download_image_base64
from rasmai.security import read_sega_id_token

logger = logging.getLogger(__name__)


def parse_nameplate_url(html: str, base_url: str) -> str:
    """The address of the name plate the player has on, from a maimai DX NET page, or "".

    The collection page's SETTING box shows the plate in use first, as ``img.w_396.m_r_10``;
    any other page that shows a plate at all is read for its first one.

    :param html: The page.
    :type html: str
    :param base_url: The region's maimai DX NET address, for a relative ``src``.
    :type base_url: str
    :rtype: str
    """
    soup = BeautifulSoup(html or "", 'html.parser')
    image = soup.select_one('img.w_396.m_r_10[src*="/img/NamePlate/"]') or soup.select_one('img[src*="/img/NamePlate/"]')
    src = str(image.get('src') or '').strip() if image else ''
    return src if not src or src.startswith('http') else f"{base_url}{src}"


class ProfilePages:
    """Logging in and reading the player's own profile page."""

    def _parse_official_player_info(self, html: str, region: str) -> Tuple[PlayerInfo, str]:
        soup = BeautifulSoup(html, 'html.parser')
        block = soup.select_one('.see_through_block')
        if block is None:
            raise ValueError('Player page did not contain expected profile content')

        player = PlayerInfo()
        base_url = get_maimai_base_url(region)

        icon_element = block.select_one('img.w_112')
        if icon_element and icon_element.get('src'):
            icon_src = icon_element.get('src', '').strip()
            player.icon_url = icon_src if icon_src.startswith('http') else f"{base_url}{icon_src}"

        name_element = block.select_one('.name_block')
        if name_element:
            player.name = name_element.get_text(strip=True)

        rating_element = block.select_one('.rating_block')
        if rating_element:
            rating_text = rating_element.get_text(strip=True)
            try:
                player.rating = int(rating_text)
            except ValueError:
                pass

        title_element = block.select_one('.trophy_block')
        if title_element:
            player.dan = title_element.get_text(strip=True)
            player.title = player.dan
            class_name = title_element.get('class', [])
            class_value = ' '.join(class_name) if isinstance(class_name, list) else str(class_name)
            if 'trophy_Rainbow' in class_value:
                player.title_type = 'rainbow'
            elif 'trophy_Gold' in class_value:
                player.title_type = 'gold'
            elif 'trophy_Silver' in class_value:
                player.title_type = 'silver'
            elif 'trophy_Bronze' in class_value:
                player.title_type = 'bronze'
            else:
                player.title_type = 'normal'

        stars_element = block.select_one('.p_l_10.f_l.f_14')
        if stars_element:
            stars_text = stars_element.get_text(strip=True)
            stars_match = re.search(r'[×x](\d+)', stars_text)
            if stars_match:
                player.stars = int(stars_match.group(1))

        play_count_element = block.select_one('.t_r.f_12')
        if play_count_element:
            play_count_text = play_count_element.get_text(' ', strip=True)
            play_count_regex = {
                'jp': re.compile(r'現バージョンプレイ回数[：:]\s*([\d,]+)'),
                'intl': re.compile(r'play count of current version[：:]\s*([\d,]+)', re.IGNORECASE),
                'cn': re.compile(r'当前版本的游玩次数[：:]\s*([\d,]+)'),
            }.get(region, re.compile(r'play count of current version[：:]\s*([\d,]+)', re.IGNORECASE))
            total_play_count_regex = {
                'jp': re.compile(r'累計プレイ回数[：:]\s*([\d,]+)'),
                'intl': re.compile(r'maimaiDX total play count[：:]\s*([\d,]+)', re.IGNORECASE),
                'cn': re.compile(r'舞萌DX的累计游玩次数[：:]\s*([\d,]+)'),
            }.get(region, re.compile(r'maimaiDX total play count[：:]\s*([\d,]+)', re.IGNORECASE))

            version_match = play_count_regex.search(play_count_text)
            total_match = total_play_count_regex.search(play_count_text)
            if version_match:
                player.version_play_count = int(version_match.group(1).replace(',', ''))
            if total_match:
                player.total_play_count = int(total_match.group(1).replace(',', ''))

        rank_elements = block.select('img.h_35.f_l')
        if len(rank_elements) >= 2:
            course_src = rank_elements[0].get('src', '').strip()
            class_src = rank_elements[1].get('src', '').strip()
            player.course_rank_url = course_src if course_src.startswith('http') else f"{base_url}{course_src}"
            player.class_rank_url = class_src if class_src.startswith('http') else f"{base_url}{class_src}"

        player.nameplate_url = parse_nameplate_url(html, base_url)
        return player, player.icon_url

    def _read_nameplate(self, session: PacedSession, region: str) -> str:
        """The plate the player has on, from the collection page; "" when it cannot be read.

        The profile page does not show the plate (other scrapers read it from here too), so
        this is one more page, read only on a full read.

        :param session: The signed-in maimai session.
        :type session: PacedSession
        :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
        :type region: str
        :rtype: str
        """
        base_url = get_maimai_base_url(region)
        try:
            html = self._fetch_official_html(session, f"{base_url}/maimai-mobile/collection/nameplate/", f"{base_url}/maimai-mobile/")
        except Exception as error:
            logger.info(f"Name plate page not read: {error}")
            return ""
        return parse_nameplate_url(html, base_url)

    def _login_and_fetch_official_profile(self, token: str, region: str) -> PlayerInfo:
        if not region_supported(region):
            # a region with no sign-in: refuse before anything is sent anywhere
            raise ValueError(unsupported_region_text(region))
        session = PacedSession()
        session.headers.update({'User-Agent': BROWSER_USER_AGENT})
        if region == "jp":
            self._sign_in_japan(session, token)
        else:
            self._sign_in_international(session, token)
        base_url = get_maimai_base_url(region)
        player_url = f'{base_url}/maimai-mobile/playerData/'
        player_response = session.get(
            player_url,
            headers={'Referer': f'{base_url}/maimai-mobile/'},
            allow_redirects=False,
            timeout=30,
        )
        if player_response.is_redirect and region != "jp":
            # the gateway took the token but the site sent the session back out: it was expired or already used
            raise SessionRejected("maimai didn't accept that session - it's probably expired or already used. Grab a fresh one and run /login again.")
        if player_response.status_code != 200:
            raise ValueError(f'Failed to fetch player data: HTTP {player_response.status_code}')
        player, icon_url = self._parse_official_player_info(player_response.text, region)
        player.avatar_base64 = download_image_base64(icon_url, cookie_jar_to_header(session))
        player.icon_url = icon_url
        player.region = region
        self._official_session = session
        self._official_cookie_header = cookie_jar_to_header(session)
        return player

    def _sign_in_international(self, session: PacedSession, token: str) -> None:
        """Replay the international Aime gateway's session cookie, which signs `session` in to maimaidx-eng.com.

        :param session: The session to sign in.
        :type session: PacedSession
        :param token: The saved sign-in, ``cookie://`` and the gateway's ``clal`` cookie.
        :type token: str
        """
        sanitized_token = token.strip()
        if not sanitized_token.startswith('cookie://'):
            raise ValueError("Official profile token must start with 'cookie://'.")
        cookie_value = sanitized_token[len('cookie://'):].strip().removeprefix('clal=')
        if not cookie_value:
            raise ValueError('Cookie token is empty.')
        login_url = 'https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/'
        session.cookies.set('clal', cookie_value, domain='lng-tgk-aime-gw.am-all.net')
        response = session.get(login_url, allow_redirects=False, timeout=30)
        if response.status_code != 302:
            logger.warning(f"Gateway refused the saved session: HTTP {response.status_code}, "
                           f"{len(response.text)} bytes, content-type {response.headers.get('Content-Type', '?')}")
            raise SessionRejected(f"maimai no longer accepts the saved sign-in (gateway answered HTTP {response.status_code}); run /login again.")
        redirect_url = response.headers.get('Location', '')
        if not redirect_url:
            raise SessionRejected('maimai answered without a redirect; run /login again.')
        session.get(redirect_url, allow_redirects=False, timeout=30)

    def _sign_in_japan(self, session: PacedSession, token: str) -> None:
        """Sign `session` in to maimaidx.jp with the account's SEGA ID, then open its Aime card.

        maimaidx.jp hands out a form token as the ``_t`` cookie on its sign-in page. Posting the SEGA ID
        and password with it answers with a redirect to the account's Aime list when they are right, and
        opening a card from that list is what the rest of the site reads from. The flow is the one other
        open-source Japan trackers use, Tomomai among them.

        :param session: The session to sign in.
        :type session: PacedSession
        :param token: The saved sign-in, from `sega_id_token`.
        :type token: str
        """
        credentials = read_sega_id_token(token)
        if credentials is None:
            raise SessionRejected("A Japan account signs in with its SEGA ID; run /login again to link it.")
        sega_id, password, aime = credentials
        base_url = get_maimai_base_url("jp")
        home = f'{base_url}/maimai-mobile/'
        page = session.get(home, timeout=30)
        if page.status_code >= 500:
            raise ValueError(f"maimaidx.jp could not show its sign-in page: HTTP {page.status_code}")
        form_token = session.cookies.get('_t') or ''
        if not form_token:
            field = BeautifulSoup(page.text or '', 'html.parser').select_one('input[name="token"]')
            form_token = str(field.get('value') or '') if field else ''
        if not form_token:
            # seen when the site is busy or turning sign-ins away for a while: not the player's doing
            raise ValueError("maimaidx.jp did not hand out a sign-in form; it may be busy, try again in a few minutes")
        answer = session.post(
            f'{base_url}/maimai-mobile/submit/',
            data={'segaId': sega_id, 'password': password, 'token': form_token},
            headers={'Referer': home},
            allow_redirects=False,
            timeout=30,
        )
        if answer.status_code >= 500:
            raise ValueError(f"maimaidx.jp could not sign in right now: HTTP {answer.status_code}")
        if answer.status_code not in (301, 302, 303) or '/aimeList/' not in answer.headers.get('Location', ''):
            raise SessionRejected("maimaidx.jp did not accept the SEGA ID and password; run /login again with the right ones.")
        chosen = session.get(f'{base_url}/maimai-mobile/aimeList/submit/?idx={aime}', headers={'Referer': home},
                             allow_redirects=False, timeout=30)
        if chosen.status_code >= 500:
            raise ValueError(f"maimaidx.jp could not open the Aime card: HTTP {chosen.status_code}")
        onward = chosen.headers.get('Location', '') if chosen.is_redirect else ''
        if chosen.status_code >= 400 or '/error/' in onward or '/aimeList/' in onward:
            raise SessionRejected(f"maimaidx.jp has no Aime card {aime + 1} on this SEGA ID; run /login again and pick another.")
        if onward:
            # the card is opened by the page it sends on to, which hands out the session the rest reads with
            session.get(urljoin(home, onward), headers={'Referer': home}, allow_redirects=True, timeout=30)

    def fetch_official_player_profile(self, token: str, region: str = "intl") -> PlayerInfo:
        return self._login_and_fetch_official_profile(token, region)

    def fetch_official_check(self, token: str, region: str = "intl", with_areas: bool = True) -> Tuple[PlayerInfo, List[Dict[str, Any]]]:
        """Sign in and read the profile, the recent-plays page and, unless told not to, the map pages.

        Enough to tell whether the stored scores are still current (play count, rating,
        any play not yet recorded) at a fraction of a full read's cost. The map pages ride
        along because each reading of an area's distance, paired with the play count, is
        what the plays-to-next-reward estimate is measured from; a failure there is logged
        and the check still answers.

        :param token: The saved maimai session.
        :type token: str
        :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
        :type region: str
        :rtype: Tuple[PlayerInfo, List[Dict[str, Any]]]
        """
        self.region = region
        player = self._login_and_fetch_official_profile(token, region)
        session = getattr(self, "_official_session", None)
        if session is None:
            raise ValueError("Official session was not preserved after login")
        base_url = get_maimai_base_url(region)
        recent_html = self._fetch_official_html(session, f"{base_url}/maimai-mobile/record/", f"{base_url}/maimai-mobile/")
        self.player = player
        self.recent_songs = self._parse_official_recent_songs(recent_html, region)
        self.enrich_recent_play_judgements(self.recent_songs, region)
        if with_areas:
            try:
                self.fetch_official_areas(region)
            except Exception as error:
                logger.info(f"Map pages not read during the check: {error}")
        return player, self.recent_songs
