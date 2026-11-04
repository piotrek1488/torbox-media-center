from library.http import api_http_client, general_http_client, requestWrapper
import httpx
from enum import Enum
from library.torbox import TORBOX_API_KEY
from library.app import SCAN_METADATA
from functions.mediaFunctions import constructSeriesTitle, cleanTitle, cleanYear, parseMediaName
from library.metadata import search as search_metadata
from functions.databaseFunctions import insertData
import os
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from functools import lru_cache
from threading import Lock

_no_match_lock = Lock()


@lru_cache(maxsize=512)
def warn_no_match(title, year, is_series):
    logging.warning("No metadata match for %s; keeping filename metadata.", title)


class DownloadType(Enum):
    torrent = "torrents"
    usenet = "usenet"
    webdl = "webdl"

class IDType(Enum):
    torrents = "torrent_id"
    usenet = "usenet_id"
    webdl = "web_id"

ACCEPTABLE_MIME_TYPES = [
    "video/x-matroska",
    "video/mp4",
]

def process_file(item, file, type):
    """Process a single file and return the processed data"""
    if not file.get("mimetype").startswith("video/") or file.get("mimetype") not in ACCEPTABLE_MIME_TYPES:
        logging.debug(f"Skipping file {file.get('short_name')} with mimetype {file.get('mimetype')}")
        return None
    
    data = {
        "item_id": item.get("id"),
        "type": type.value,
        "folder_name": item.get("name"),
        "DEBUG_name": item.get("name"),
        "DEBUG_hash": item.get("hash"),
        "DEBUG_file_name": file.get("short_name"),
        "folder_hash": item.get("hash"),
        "file_id": file.get("id"),
        "file_name": file.get("short_name"),
        "file_size": file.get("size"),
        "file_mimetype": file.get("mimetype"),
        "path": file.get("name"),
        "download_link": f"https://api.torbox.app/v1/api/{type.value}/requestdl?token={TORBOX_API_KEY}&{IDType[type.value].value}={item.get('id')}&file_id={file.get('id')}&redirect=true",
        "extension": os.path.splitext(file.get("short_name"))[-1],              
    }
    title_data = parseMediaName(file.get("short_name"), item.get("name"), file.get("name"))

    if item.get("name") == item.get("hash"):
        item["name"] = title_data.get("title", file.get("short_name"))

    metadata, _, _ = searchMetadata(title_data.get("title", file.get("short_name")), title_data, file.get("short_name"), f"{item.get('name')} {file.get('short_name')}", item.get("hash"), item.get("name"))
    data.update(metadata)
    logging.debug(data)
    insertData(data, type.value)
    return data

def getUserDownloads(type: DownloadType):
    offset = 0
    limit = 1000

    file_data = []
    
    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "bypass_cache": True,
        }
        try:
            response = api_http_client.get(f"/{type.value}/mylist", params=params)
        except Exception as e:
            logging.error(f"Error fetching {type.value} at offset {offset}: {e}")
            return None, False, f"Error fetching {type.value} at offset {offset}: {e}"
        if response.status_code != 200:
            return None, False, f"Error fetching {type.value} at offset {offset}. {response.status_code}"
        try:
            data = response.json().get("data", [])
        except Exception as e:
            logging.error(f"Error parsing {type.value} at offset {offset}: {e}")
            logging.error(f"Response: {response.text}")
            return None, False, f"Error parsing {type.value} at offset {offset}. {e}"
        if not data:
            break
        file_data.extend(data)
        offset += limit
        if len(data) < limit:
            break

    if not file_data:
        return None, True, f"No {type.value} found."
    
    logging.debug(f"Fetched {len(file_data)} {type.value} items from API.")
    
    files = []
    
    # Get the number of CPU cores for parallel processing
    max_workers = int(multiprocessing.cpu_count() * 2 - 1)
    logging.info(f"Processing files with {max_workers} parallel threads")
    
    # Collect all files to process
    files_to_process = []
    for item in file_data:
        if not item.get("cached", False):
            continue
        for file in item.get("files", []):
            files_to_process.append((item, file))
    
    # Process files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_file, item, file, type): (item, file) 
            for item, file in files_to_process
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            try:
                data = future.result()
                if data:
                    files.append(data)
            except Exception as e:
                item, file = future_to_file[future]
                logging.error(f"Error processing file {file.get('short_name', 'unknown')}: {e}")
                logging.error(traceback.format_exc())
            
    return files, True, f"{type.value.capitalize()} fetched successfully."

def searchMetadata(query: str, title_data: dict, file_name: str, full_title: str, hash: str, item_name: str):
    # Season-pack folders supply title/year when episode filenames omit them.
    parsed = {**parseMediaName(file_name, item_name),
              **{k: v for k, v in title_data.items() if v is not None and v != []}}
    season, episode = parsed.get("season"), parsed.get("episode")
    if parsed.get("media_type") == "movie":
        season = episode = None
    is_series = parsed.get("media_type") == "series" or season is not None or episode is not None
    title = cleanTitle(parsed.get("title") or query or item_name or "Unknown")
    year = cleanYear(parsed.get("year"))
    base_metadata = {
        "metadata_title": title,
        "metadata_link": None,
        "metadata_mediatype": "series" if is_series else "movie",
        "metadata_image": None,
        "metadata_backdrop": None,
        "metadata_years": year,
        "metadata_season": season,
        "metadata_episode": episode,
        "metadata_filename": file_name,
        "metadata_rootfoldername": item_name or title,
    }
    if is_series:
        base_metadata["metadata_foldername"] = constructSeriesTitle(
            season=season if season is not None else 1, folder=True)
    if not SCAN_METADATA:
        return base_metadata, False, "Metadata scanning is disabled."
    try:
        data = None
        selected = None
        candidates = parsed.get("metadata_candidates") or [{"title": title, "year": year, "source": "filename"}]
        for candidate in candidates:
            data = search_metadata(candidate["title"], cleanYear(candidate.get("year")), is_series)
            if data:
                selected = candidate
                break
        if not data:
            with _no_match_lock:
                warn_no_match(title, year, is_series)
            return base_metadata, False, "No metadata match."
        title = cleanTitle(data["title"])
        year = data["year"]
        root = f"{title} ({year})" if year else title
        extension = os.path.splitext(file_name)[-1]
        if is_series:
            numbering = constructSeriesTitle(season=season, episode=episode)
            # Unnumbered episodes must retain distinct names rather than all becoming S01.
            filename = f"{title} {numbering}{extension}" if episode is not None and numbering else file_name
        else:
            filename = f"{root}{extension}"
        base_metadata.update({
            "metadata_title": title,
            "metadata_years": year,
            "metadata_filename": filename,
            "metadata_rootfoldername": root,
            "metadata_link": data["link"],
            "metadata_provider": data.get("provider", "tmdb"),
            "metadata_query": selected["title"],
            "metadata_query_source": selected["source"],
            "metadata_image": data["image"],
            "metadata_backdrop": data["backdrop"],
        })
        return base_metadata, True, "Metadata found."
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        # Never log request headers or token-bearing exception details.
        logging.warning("Metadata lookup failed for %s; check token, connectivity and response. Keeping filename metadata.", title)
        return base_metadata, False, "Metadata lookup failed."

def getDownloadLink(url: str):
    response = requestWrapper(general_http_client, "GET", url)
    if response.status_code == httpx.codes.TEMPORARY_REDIRECT or response.status_code == httpx.codes.PERMANENT_REDIRECT or response.status_code == httpx.codes.FOUND:
        return response.headers.get('Location')
    return url

def downloadFile(url: str, size: int, offset: int = 0):
    headers = {
        "Range": f"bytes={offset}-{offset + size - 1}",
        **general_http_client.headers,
    }
    response = requestWrapper(general_http_client, "GET", url, headers=headers)
    if response.status_code == httpx.codes.OK:
        return response.content
    elif response.status_code == httpx.codes.PARTIAL_CONTENT:
        return response.content
    else:
        logging.error(f"Error downloading file: {response.status_code}")
        raise Exception(f"Error downloading file: {response.status_code}")
    
