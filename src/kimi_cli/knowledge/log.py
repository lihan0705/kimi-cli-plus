from datetime import datetime
from pathlib import Path
from uuid import UUID


class LogManager:
    def __init__(self, root: Path):
        self.root = root
        self.log_file = root / "log.md"
        self.archive_dir = root / "log_archive"
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Initialize the log file with a header if it doesn't exist."""
        if not self.log_file.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self.log_file.write_text("# Knowledge Base Activity Log\n\n")

    def _get_last_entry_date(self) -> datetime | None:
        """Get the date of the last entry in the log file, or file mtime if no entries."""
        if not self.log_file.exists():
            return None

        content = self.log_file.read_text().splitlines()
        # Look for the last line starting with "- ["
        for line in reversed(content):
            if line.startswith("- ["):
                try:
                    # Format: - [YYYY-MM-DD HH:MM:SS]
                    date_str = line[3:22]
                    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

        # Fallback to file modification time
        return datetime.fromtimestamp(self.log_file.stat().st_mtime)

    def check_rotation(self):
        """Rotate the log file if it belongs to a previous week."""
        last_date = self._get_last_entry_date()
        if not last_date:
            return

        now = datetime.now()
        now_iso = now.isocalendar()
        last_iso = last_date.isocalendar()

        # Compare (year, week)
        if (now_iso[0], now_iso[1]) != (last_iso[0], last_iso[1]):
            self._rotate(last_date)

    def _rotate(self, last_date: datetime):
        """Perform the actual rotation."""
        iso_year, iso_week, _ = last_date.isocalendar()
        # Requirement: log_archive/{YYYY}/{MM}/week-{WW}.md
        # Using the month of the last entry
        year_str = str(iso_year)
        month_str = last_date.strftime("%m")
        week_str = f"{iso_week:02d}"

        archive_path = self.archive_dir / year_str / month_str / f"week-{week_str}.md"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Move current log.md to archive
        if self.log_file.exists():
            # If multiple rotations happen (e.g. system down for weeks),
            # we might want to append if the archive already exists,
            # but usually it won't if we rotate correctly.
            # Using rename for simplicity as per "Move log.md"
            if archive_path.exists():
                # Append if it exists (safety)
                with archive_path.open("a") as f:
                    f.write("\n" + self.log_file.read_text())
                self.log_file.unlink()
            else:
                self.log_file.rename(archive_path)

        # Start fresh
        self._ensure_log_file()

    def append(self, action: str, title: str, doc_id: UUID | None = None):
        """Append an action to the log, rotating if necessary."""
        self.check_rotation()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_id_str = str(doc_id) if doc_id else ""
        line = f"- [{timestamp}] {action}: {title} ({doc_id_str})\n"

        with self.log_file.open("a") as f:
            f.write(line)
