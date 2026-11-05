import re
import logging

def constructSeriesTitle(season = None, episode = None, folder: bool = False):
    """
    Constructs a proper title for a series based on the season and episode.

    :param season: The season number or a list of season numbers.
    :param episode: The episode number or a list of episode numbers.
    :param folder: If True, the title will be formatted for a folder name.
    """


    def label(value, prefix):
        if isinstance(value, list):
            values = [n for n in value if isinstance(n, int) and n >= 0]
            if not values:
                return None
            if len(values) == 1:
                return f"{prefix}{values[0]:02}"
            return f"{prefix}{values[0]:02}-{prefix}{values[-1]:02}"
        if isinstance(value, int) and value >= 0:
            return f"{prefix}{value:02}"
        return None

    title_season = label(season, "S")
    title_episode = label(episode, "E")
    if folder and title_season:
        if isinstance(season, list):
            return title_season
        return f"Season {season}"

    if title_season and title_episode:
        return f"{title_season}{title_episode}"
    elif title_season:
        return title_season
    elif title_episode:
        return title_episode
    else:
        return None
    
def cleanTitle(title: str):
    """
    Removes invalid characters from the title.
    """
    title = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "", title)
    return title

def cleanYear(year: str | int):
    """
    Cleans the year listing which can be a string (2023-2024) or an int (2023).
    """
    try:
        if not year:
            return None
        if isinstance(year, str):
            year = re.sub(r"[–—−‐‑]", "-", year)
            year = year.split("-")[0]
            year = year.strip()
            return int(year)
        if type(year) is int:
            return year
        if year and year != "None":
            return int(year)
        else:
            return None
    except Exception as e:
        logging.error(f"Error cleaning year: {e}")
        return None


def opaqueMediaName(name):
    return bool(re.fullmatch(r'(?=.*\d)[0-9a-f]{7,}', name or '', re.IGNORECASE))


def metadataMediaTypes(parsed):
    episodic = parsed.get('season') is not None or parsed.get('episode') is not None
    contextual_series = parsed.get('media_type') == 'series' or episodic
    if parsed.get('media_type') == 'movie':
        return ['movie']
    if parsed.get('file_type_hint') == 'movie':
        return ['movie', 'series'] if contextual_series else ['movie']
    return ['series'] if contextual_series else ['movie']


def parseMediaName(file_name, parent_name="", file_path=""):
    """Repair PTN's empty episode lists and parse absolute anime numbering."""
    import PTN
    parent = PTN.parse(parent_name or "") if not opaqueMediaName(parent_name) else {}
    # Folder hypotheses must not silently supply an episode number for a file.
    parent.pop("season", None)
    parent.pop("episode", None)
    file_data = PTN.parse(file_name)
    parsed = {**parent, **{k: v for k, v in file_data.items()
                          if v is not None and v != []}}
    # Release-group tags and technical brackets must not become the search title.
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", file_name)
    name = re.sub(r"\.[^.]+$", "", name).strip()
    # PTN can remove quality tags but leave separators after an absolute episode.
    # Try both the cleaned filename and PTN's title so quality suffixes need no allowlist.
    for episode_title in (name, file_data.get("title", "")):
        match = re.fullmatch(r"(.+?)\s+[-–—]\s*(\d{1,4})(?:v\d+)?[.\s]*", episode_title, re.IGNORECASE)
        if not match:
            continue
        number = int(match[2])
        if number >= 1900 and number == parsed.get("year"):
            continue
        parsed["title"] = match[1].strip()
        if not file_data.get("episode"):
            parsed["episode"] = number
            parsed["absolute_episode"] = True
        break
    # Episode-only names need a series title from the containing folder/download.
    leading_episode = re.match(
        r"^(?:(?:episode|ep|odcinek|odc)\.?\s*(\d{1,4})\b|S(\d{1,2})E(\d{1,4})\b|(\d{1,4})\s*[-.])",
        name, re.IGNORECASE)
    if leading_episode:
        number = leading_episode[1] or leading_episode[3] or leading_episode[4]
        parsed["episode"] = int(number)
        if leading_episode[2] is not None:
            parsed["season"] = int(leading_episode[2])
        else:
            parsed["absolute_episode"] = True
    if re.search(r"\b(?:movie|film)\s*#?\s*\d+\b", name, re.IGNORECASE):
        parsed["media_type"] = "movie"
        # A film in a season-pack folder must not inherit episode numbering.
        parsed.pop("season", None)
        parsed.pop("episode", None)
    # PTN can take the end of a broadcast range as year and leave the start in title.
    years = re.search(r'(?<!\d)((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})(?!\d)', file_name)
    if years and int(years[1]) <= int(years[2]):
        parsed["year"] = int(years[1])
        parsed["title"] = re.sub(rf'\s+{years[1]}$', '', parsed.get("title", "")).strip()
    for key in ("season", "episode"):
        if parsed.get(key) == []:
            parsed.pop(key)
    if file_data.get("year") and parsed.get("season") is None and parsed.get("episode") is None:
        parsed["file_type_hint"] = "movie"
    candidates = metadataCandidates(file_name, parent_name, file_path, parsed, bool(leading_episode))
    if candidates:
        parsed["metadata_candidates"] = candidates
        parsed["title"] = candidates[0]["title"]
        if candidates[0].get("year"):
            parsed["year"] = candidates[0]["year"]
    return parsed


def metadataCandidates(file_name, parent_name, file_path, parsed, episode_only=False):
    """Bounded title hypotheses, each to be validated by a metadata provider."""
    import PTN
    folders = list(reversed(re.split(r"[/\\]", file_path or "")[:-1]))
    contexts = []
    series_context = False
    for raw, source in [(folder, "folder") for folder in folders] + [(parent_name, "download")]:
        if not raw or opaqueMediaName(raw):
            continue
        context = PTN.parse(raw)
        explicit_season = bool(re.search(r"(?<!\w)(?:s\d{1,2}(?:e\d{1,4})?|seasons?[ ._-]*\d+|sezon[ ._-]*\d+)(?!\w)", raw, re.IGNORECASE))
        if (explicit_season and parsed.get("media_type") != "movie" and not parsed.get("absolute_episode")
                and parsed.get("season") is None
                and isinstance(context.get("season"), int)):
            parsed["season"] = context["season"]
        if explicit_season or re.search(r"\b(?:complete[ ._-]+(?:series|seasons?)|sezon[ ._-]*\d+|season[ ._-]*\d+)\b", raw, re.IGNORECASE):
            series_context = True
        title = context.get("title", "").strip()
        if not title or not re.search(r"[^\W\d_]", title) or re.fullmatch(
            r"(?:season|sezon|s)\s*\d+|[0-9a-f]{16,}|(?:1080|720|2160)p|episodes?|odcinki|anime|movies|series|downloads?|collection|anime collection|ciekawe filmy seriale|specials?|extras?|bonus|ova|batch",
            title, re.IGNORECASE):
            continue
        year = context.get("year")
        years = re.search(r'(?<!\d)((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})(?!\d)', raw)
        if years and int(years[1]) <= int(years[2]):
            year = int(years[1])
            title = re.sub(rf'\s+{years[1]}$', '', title).strip()
        contexts.append({"title": title, "year": year, "source": source})
    explicit_movie = parsed.get("media_type") == "movie"
    if series_context and not explicit_movie:
        parsed["media_type"] = "series"
    file_candidate = {"title": parsed.get("title", ""), "year": parsed.get("year"), "source": "filename"}
    # Complete-series packs often give episodes only descriptive names.
    # Explicit series names in filenames remain authoritative.
    file_key = re.sub(r"\W+", " ", file_candidate["title"]).casefold().strip()
    named_series = any(file_key.startswith(re.sub(r"\W+", " ", c["title"]).casefold().strip()) for c in contexts)
    prefer_context = episode_only or (series_context and not explicit_movie and parsed.get("file_type_hint") != "movie" and not named_series)
    ordered = contexts + ([] if episode_only else [file_candidate]) if prefer_context else [file_candidate] + contexts
    candidates, seen = [], set()
    for candidate in ordered:
        key = (candidate["title"].casefold(), candidate["year"])
        if not candidate["title"] or key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) == 4:
            break
    return candidates
