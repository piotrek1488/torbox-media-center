import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TORBOX_API_KEY'] = 'offline-test-placeholder'
os.environ['MOUNT_METHOD'] = 'strm'
os.environ['ENABLE_METADATA'] = 'false'
with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)
    os.environ['MOUNT_PATH'] = str(Path(tmp) / 'media')
    from functions.databaseFunctions import insertData, clearDatabase, closeAllDatabases
    from functions.stremFilesystemFunctions import runStrm
    from functions.torboxFunctions import process_file, DownloadType
    item = {'id': 1, 'name': 'Sample Movie', 'hash': 'sample'}
    file = {'id': 2, 'short_name': 'Sample.Movie.2024.mp4', 'name': 'Sample.Movie.2024.mp4', 'size': 100, 'mimetype': 'video/mp4'}
    data = process_file(item, file, DownloadType.torrent)
    assert data and data['file_id'] == 2
    runStrm()
    files = list(Path(os.environ['MOUNT_PATH']).rglob('*.strm'))
    assert len(files) == 1, files
    assert files[0].read_text() == data['download_link']
    assert clearDatabase('torrents')[0]
    runStrm()
    assert not list(Path(os.environ['MOUNT_PATH']).rglob('*.strm'))
    assert closeAllDatabases()[0]
print('PASS: process media, TinyDB persistence, STRM content, stale-file cleanup')
