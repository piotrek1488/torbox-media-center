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


def parseMediaName(file_name, parent_name=""):
    """Repair PTN's empty episode lists and parse absolute anime numbering."""
    import PTN
    parent = PTN.parse(parent_name or "")
    file_data = PTN.parse(file_name)
    parsed = {**parent, **{k: v for k, v in file_data.items()
                          if v is not None and v != []}}
    # Release-group tags and technical brackets must not become the search title.
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", file_name)
    name = re.sub(r"\.[^.]+$", "", name).strip()
    match = re.fullmatch(r"(.+?)\s+-\s+(\d{1,4})(?:v\d+)?\s*", name, re.IGNORECASE)
    if match and not file_data.get("episode"):
        parsed["title"] = match[1].strip()
        parsed["episode"] = int(match[2])
        parsed["absolute_episode"] = True
    if re.search(r"\b(?:movie|film)\s*#?\s*\d+\b", name, re.IGNORECASE):
        parsed["media_type"] = "movie"
        # A film in a season-pack folder must not inherit episode numbering.
        parsed.pop("season", None)
        parsed.pop("episode", None)
    for key in ("season", "episode"):
        if parsed.get(key) == []:
            parsed.pop(key)
    return parsed
