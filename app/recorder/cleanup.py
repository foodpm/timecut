"""循环录像清理 - 按保留天数清理旧文件"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from config import settings
from database import get_session, Recording

logger = logging.getLogger("timecut.cleanup")


class RecordingCleaner:
    """按保留天数清理过期录像"""

    def __init__(self):
        self._tz = ZoneInfo(settings.tz)

    def clean(self) -> int:
        days = settings.recording_retention_days
        cutoff = datetime.now(self._tz) - timedelta(days=days)
        session = get_session()
        deleted_count = 0
        try:
            expired = (
                session.query(Recording)
                .filter(Recording.start_time < cutoff)
                .all()
            )
            for rec in expired:
                file_path = settings.recordings_dir / rec.file_path
                try:
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"删除过期文件: {file_path}")
                    session.delete(rec)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"删除失败 {file_path}: {e}")
            self._clean_empty_dirs(settings.recordings_dir)
            session.commit()
            if deleted_count > 0:
                logger.info(f"清理完成，共删除 {deleted_count} 个过期录像文件")
        except Exception as e:
            session.rollback()
            logger.error(f"清理过程出错: {e}")
        finally:
            session.close()
        return deleted_count

    @staticmethod
    def _clean_empty_dirs(root: Path):
        for dirpath in sorted(root.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    if not any(dirpath.iterdir()):
                        dirpath.rmdir()
                except Exception:
                    pass
