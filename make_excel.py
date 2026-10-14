import os

import config
import excel_store


def main() -> None:
    excel_store.ensure_workbook(config.DATA_XLSX)
    # Regenerate the example row only if the sheet has just headers.
    rows = excel_store.read_all(config.DATA_XLSX, limit=100000)
    if not rows:
        excel_store.append_row(config.DATA_XLSX, {
            "timestamp": "2026-10-14T10:30:00",
            "original_name": "clip.mp4",
            "stored_name": "3f9c1a_clip.mp4",
            "size_bytes": 524288000,
            "mime_type": "video/mp4",
            "mode": "link",
            "url": "http://127.0.0.1:8000/media/3f9c1a_clip.mp4",
            "message_id": "1234567890",
            "status": "sent",
            "error": "",
        })
    print(f"Ready: {os.path.relpath(config.DATA_XLSX)}")


if __name__ == "__main__":
    main()
