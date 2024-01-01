"""行動ログを整形して出力する."""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Self

import requests
from pydantic import BaseModel

_logger = logging.getLogger(__name__)


class _TimeEntry(BaseModel):
    """togglの時間記録データを表す."""

    name: str

    start: str
    stop: str

    project_id: int


class _Project(BaseModel):
    """togglのプロジェクトデータを表す."""

    project_id: int

    name: str


class _ToggleService:
    """Togglサービスへ接続しデータを取得する."""

    _API_BASE_URL = "https://api.track.toggl.com/api/v9"

    def __init__(self: Self, api_key: str | None = None) -> None:
        if api_key is None:
            self._api_key = os.environ.get("TOGGL_API_KEY", "")
        else:
            self._api_key = api_key

    def get_time_entries(
        self: Self, start_date: datetime, end_date: datetime
    ) -> list[_TimeEntry]:
        """Entryを取得する."""
        params = {
            # 時間記述は下記のような形式になることを想定している
            # - "start_date": "2023-09-12T00:00:00.0000+09:00",
            "start_date": start_date.isoformat(timespec="milliseconds"),
            "end_date": end_date.isoformat(timespec="milliseconds"),
        }
        response = requests.get(
            f"{self._API_BASE_URL}/me/time_entries",
            auth=(self._api_key, "api_token"),
            params=params,
            timeout=10,
        )

        entries: list[_TimeEntry] = []
        for entry in response.json():
            time_entry = _TimeEntry(
                name=entry["description"],
                start=entry["start"],
                stop=entry["stop"],
                project_id=entry["project_id"],
            )
            entries.append(time_entry)

        return entries

    def get_projects(self: Self) -> list[_Project]:
        """Project一覧を取得する."""
        response = requests.get(
            f"{self._API_BASE_URL}/me/projects",
            auth=(self._api_key, "api_token"),
            timeout=10,
        )

        projects = []
        for project in response.json():
            data = _Project(
                project_id=project["id"],
                name=project["name"],
            )
            projects.append(data)

        return projects


class _MarkdownListPrinter:
    """Markdownのリスト形式で結果を標準出力する."""

    def __init__(self: Self) -> None:
        pass

    def display(
        self: Self, time_entries: list[_TimeEntry], projects: list[_Project]
    ) -> None:
        project_dict = {p.project_id: p for p in projects}

        for entry in time_entries:
            project_name = project_dict[entry.project_id].name
            dt_tz = datetime.fromisoformat(entry.start).astimezone(
                timezone(timedelta(hours=9))
            )
            time_str = dt_tz.strftime("%H:%M")
            print(f"- {time_str} {project_name} {entry.name}")
        last_entry = time_entries[-1]
        dt_tz = datetime.fromisoformat(
            last_entry.stop.replace("Z", "+00:00")
        ).astimezone(timezone(timedelta(hours=9)))
        time_str = dt_tz.strftime("%H:%m")
        print(f"- {time_str} 終了")


def _main() -> None:
    """スクリプトのエントリポイント."""
    toggl_service = _ToggleService(api_key=None)
    time_entries = toggl_service.get_time_entries(
        datetime.fromisoformat("2023-10-10T00:00:00+09:00"),
        datetime.fromisoformat("2023-10-11T00:00:00+09:00"),
    )
    time_entries = sorted(time_entries, key=lambda x: x.start)

    project_list = toggl_service.get_projects()

    printer = _MarkdownListPrinter()
    printer.display(time_entries=time_entries, projects=project_list)


if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.DEBUG)
        _main()
    except Exception:
        _logger.exception("Unhandled exception occurred.")
        sys.exit(1)
