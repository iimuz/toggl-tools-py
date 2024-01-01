"""サマリーを出力する."""
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Self

import requests
from pydantic import BaseModel

_logger = logging.getLogger(__name__)


class _TimeEntry(BaseModel):
    name: str

    start: str
    stop: str
    duration: int

    project_id: int
    tag_ids: list[int]


class _Project(BaseModel):
    project_id: int

    name: str


class _Tag(BaseModel):
    tag_id: int

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
            # 時間表記としては下記のような形式になることを想定している
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
        _logger.info(response)

        entries: list[_TimeEntry] = []
        for entry in response.json():
            time_entry = _TimeEntry(
                name=entry["description"],
                start=entry["start"],
                stop=entry["stop"],
                duration=entry["duration"],
                project_id=entry["project_id"],
                tag_ids=entry["tag_ids"],
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

    def get_tags(self: Self) -> list[_Tag]:
        """タグ一覧を取得する."""
        response = requests.get(
            f"{self._API_BASE_URL}/me/tags",
            auth=(self._api_key, "api_token"),
            timeout=10,
        )

        tags: list[_Tag] = []
        for entry in response.json():
            tag = _Tag(
                tag_id=entry["id"],
                name=entry["name"],
            )
            tags.append(tag)

        return tags


@dataclass
class _TagDuration:
    project_id: int
    tag_id: int

    duration: int


class _Durations:
    EXCLUDE_TAG_IDS: ClassVar = [
        int(v)
        for v in os.environ.get("TOGGL_EXCLUDE_TAG_IDS", "").split(",")
        if v != ""
    ]

    def __init__(self: Self) -> None:
        pass

    def calc_tag_durations(
        self: Self, time_entries: list[_TimeEntry]
    ) -> list[_TagDuration]:
        """プロジェクトごと、かつタグごとの総和時間を返す."""
        durations: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for entry in time_entries:
            for tag_id in entry.tag_ids:
                if tag_id in self.EXCLUDE_TAG_IDS:
                    continue

                durations[entry.project_id][tag_id] += entry.duration

        return [
            _TagDuration(project_id=project_id, tag_id=tag_id, duration=duration)
            for project_id, entry in durations.items()
            for tag_id, duration in entry.items()
        ]


class _MarkdownTablePrinter:
    def __init__(self: Self) -> None:
        pass

    def display(
        self: Self,
        durations: list[_TagDuration],
        projects: list[_Project],
        tags: list[_Tag],
    ) -> None:
        project_names = {v.project_id: v.name for v in projects}
        tag_names = {v.tag_id: v.name for v in tags}

        # プロジェクトとタグで分離するためにdictを利用する
        duration_hash: dict[int, dict[int, _TagDuration]] = defaultdict(
            lambda: defaultdict(
                lambda: _TagDuration(project_id=0, tag_id=0, duration=0)
            )
        )
        for duration in durations:
            duration_hash[duration.project_id][duration.tag_id] = duration

        # プロジェクトごとの経過時間を算出
        project_durations: dict[int, int] = defaultdict(int)
        for duration in durations:
            project_durations[duration.project_id] += duration.duration

        print("| Project | Tag | Duration |")
        print("| :------ | :-- | -------: |")
        for project_id in duration_hash:
            project_name = project_names[project_id]
            project_duration = (
                round(project_durations[project_id] / 3600 * 4) / 4
            )  # 0.25刻みに修正
            print(f"| {project_name} | - | {project_duration} |")

            for tag_id, duration in duration_hash[project_id].items():
                tag_name = tag_names[tag_id]
                time_value = round(duration.duration / 3600 * 4) / 4  # 0.25刻みに修正
                print(f"| {project_name} | {tag_name} | {time_value} |")


def _main() -> None:
    """スクリプトのエントリポイント."""
    toggl_service = _ToggleService(api_key=None)
    start_date = datetime.fromisoformat("2023-10-10T00:00:00+09:00")
    for index in range(2):
        current_date = start_date + timedelta(days=index)
        end_date = current_date + timedelta(days=1)
        time_entries = toggl_service.get_time_entries(current_date, end_date)
        time_entries = sorted(time_entries, key=lambda x: x.start)
        project_list = toggl_service.get_projects()
        tags_list = toggl_service.get_tags()

        durations = _Durations()
        tag_durations = durations.calc_tag_durations(time_entries=time_entries)

        _logger.info("start date: %s", current_date.strftime("%Y-%m-%d"))
        printer = _MarkdownTablePrinter()
        printer.display(durations=tag_durations, projects=project_list, tags=tags_list)


if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.DEBUG)
        _main()
    except Exception:
        _logger.exception("Unhandled exception occurred.")
        sys.exit(1)
