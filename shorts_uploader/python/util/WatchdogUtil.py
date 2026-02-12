import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


def _handler(callback):
    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            if event.src_path.endswith(".mp4"):
                print(f"새 영상 감지: {event.src_path}")
                callback(event.src_path)

    return _Handler()


def start_watching(watch_dir, on_event):
    os.makedirs(watch_dir, exist_ok=True)
    observer = Observer()
    observer.schedule(_handler(on_event), watch_dir, recursive=True)
    observer.start()
    print(f"폴더 감시 시작: {watch_dir}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
