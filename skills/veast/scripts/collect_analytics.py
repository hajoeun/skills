#!/usr/bin/env python3
"""YouTube Analytics data collection and quantitative analysis.

Combines youtube_client.py + analyzer.py from the original veast project.
No pydantic dependency — uses plain dicts + json.

External dependencies (pip install):
  google-api-python-client google-auth google-auth-oauthlib
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manage_project import (  # noqa: E402
    load_history,
    load_project,
    save_project,
    start_phase,
)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str) -> Path:
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    return Path(path_str).resolve()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANALYTICS_API_SERVICE = "youtubeAnalytics"
ANALYTICS_API_VERSION = "v2"
DATA_API_SERVICE = "youtube"
DATA_API_VERSION = "v3"

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

PERIOD_DAYS = {"72h": 3, "1w": 7, "4w": 28}
ANALYSIS_CONTEXT_FILENAME = "analysis_context.md"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def load_credentials(token_path: str | None = None):
    """Load OAuth credentials from token file and refresh if expired."""
    # Lazy import — only needed when actually collecting
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path_str = token_path or os.environ.get("YOUTUBE_TOKEN_PATH")
    if not path_str:
        raise ValueError(
            "YouTube token path required. "
            "Set YOUTUBE_TOKEN_PATH or pass --token-path."
        )

    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"YouTube token file not found: {path}")

    creds = Credentials.from_authorized_user_file(str(path), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")

    return creds


# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------


def _date_range(published_at: datetime, period: str) -> tuple[str, str]:
    """Calculate start and end date strings for the Analytics API."""
    start = published_at.date()
    end = start + timedelta(days=PERIOD_DAYS[period])
    return start.isoformat(), end.isoformat()


def _format_duration(seconds: int) -> str:
    """Format seconds as MM:SS string."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


# ---------------------------------------------------------------------------
# YouTube Analytics API
# ---------------------------------------------------------------------------


def get_video_analytics(creds, video_id: str, published_at: datetime, period: str) -> dict:
    """Fetch core analytics metrics."""
    from googleapiclient.discovery import build

    start_date, end_date = _date_range(published_at, period)
    service = build(ANALYTICS_API_SERVICE, ANALYTICS_API_VERSION, credentials=creds)

    response = (
        service.reports()
        .query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
            filters=f"video=={video_id}",
        )
        .execute()
    )

    rows = response.get("rows", [])
    row = rows[0] if rows else []
    result = {
        "views": row[0] if len(row) > 0 else 0,
        "estimated_minutes_watched": row[1] if len(row) > 1 else 0,
        "avg_view_duration": row[2] if len(row) > 2 else 0,
        "subscribers_gained": row[3] if len(row) > 3 else 0,
        "subscribers_lost": row[4] if len(row) > 4 else 0,
    }

    # Fetch views by traffic source (useful for traffic analysis)
    try:
        ctr_response = (
            service.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views",
                dimensions="insightTrafficSourceType",
                filters=f"video=={video_id}",
            )
            .execute()
        )
        result["views_by_traffic"] = sum(
            r[1] for r in ctr_response.get("rows", [])
        )
    except Exception:
        pass

    # Note: thumbnail impressions and CTR (impressionClickThroughRate) are
    # not available through the YouTube Analytics Reporting API.
    # They are only visible in YouTube Studio.
    # We mark impressions as None to signal manual input is needed.
    result["impressions"] = None

    return result


def get_retention_curve(creds, video_id: str) -> dict[str, float]:
    """Fetch audience retention curve."""
    from googleapiclient.discovery import build

    service = build(ANALYTICS_API_SERVICE, ANALYTICS_API_VERSION, credentials=creds)

    response = (
        service.reports()
        .query(
            ids="channel==MINE",
            startDate="2005-01-01",
            endDate="2099-12-31",
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        )
        .execute()
    )

    curve = {}
    for row in response.get("rows", []):
        pct_position = round(row[0] * 100, 1)
        retention_pct = round(row[1] * 100, 1)
        curve[str(pct_position)] = retention_pct

    return curve


def get_traffic_sources(creds, video_id: str, published_at: datetime, period: str) -> dict[str, int]:
    """Fetch traffic source breakdown."""
    from googleapiclient.discovery import build

    start_date, end_date = _date_range(published_at, period)
    service = build(ANALYTICS_API_SERVICE, ANALYTICS_API_VERSION, credentials=creds)

    response = (
        service.reports()
        .query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views",
            dimensions="insightTrafficSourceType",
            filters=f"video=={video_id}",
        )
        .execute()
    )

    return {row[0]: row[1] for row in response.get("rows", [])}


def get_video_details(creds, video_id: str) -> dict:
    """Fetch video statistics from YouTube Data API."""
    from googleapiclient.discovery import build

    service = build(DATA_API_SERVICE, DATA_API_VERSION, credentials=creds)

    response = (
        service.videos()
        .list(part="statistics,snippet,contentDetails", id=video_id)
        .execute()
    )

    items = response.get("items", [])
    if not items:
        return {"likes": 0, "comment_count": 0, "view_count": 0}

    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})
    return {
        "likes": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
        "title": snippet.get("title", ""),
        "published_at": snippet.get("publishedAt", ""),
        "duration": content.get("duration", ""),
        "channel_title": snippet.get("channelTitle", ""),
    }


def get_comments(creds, video_id: str, max_results: int = 100) -> list[str]:
    """Fetch top-level comment texts for sentiment analysis."""
    from googleapiclient.discovery import build

    service = build(DATA_API_SERVICE, DATA_API_VERSION, credentials=creds)

    comments: list[str] = []
    page_token = None

    while len(comments) < max_results:
        per_page = min(100, max_results - len(comments))
        request = service.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=per_page,
            order="relevance",
            textFormat="plainText",
            pageToken=page_token,
        )

        try:
            response = request.execute()
        except Exception:
            break

        for item in response.get("items", []):
            text = (
                item.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
                .get("textDisplay", "")
            )
            if text:
                comments.append(text)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return comments


def collect_all(creds, video_id: str, published_at: datetime, period: str) -> tuple[dict, list, dict]:
    """Collect all YouTube data. Returns (metrics, comments, raw_responses)."""
    raw: dict = {}

    analytics = get_video_analytics(creds, video_id, published_at, period)
    raw["analytics"] = analytics

    retention = get_retention_curve(creds, video_id)
    raw["retention_curve"] = retention

    traffic = get_traffic_sources(creds, video_id, published_at, period)
    raw["traffic_sources"] = traffic

    details = get_video_details(creds, video_id)
    raw["video_details"] = details

    comments = get_comments(creds, video_id)
    raw["comments_count_fetched"] = len(comments)

    # Calculate average retention
    avg_retention = None
    if retention:
        values = list(retention.values())
        avg_retention = round(sum(values) / len(values), 1)

    # Build metrics dict
    # Fallback to Data API view_count when Analytics API returns 0
    views = analytics.get("views", 0)
    if views == 0:
        views = details.get("view_count", 0)

    views_key = f"views_{period}"
    metrics = {
        "views_72h": None, "views_1w": None, "views_4w": None,
        "ctr": analytics.get("ctr"),
        "retention_rate": avg_retention,
        "avg_view_duration": _format_duration(analytics.get("avg_view_duration", 0)),
        "impressions": analytics.get("impressions"),
        "likes": details.get("likes"),
        "comment_count": details.get("comment_count"),
        "subscribers_gained": analytics.get("subscribers_gained"),
        "subscribers_lost": analytics.get("subscribers_lost"),
        "traffic_sources": traffic if traffic else None,
        "retention_curve": retention if retention else None,
    }
    metrics[views_key] = views

    return metrics, comments, raw


# ---------------------------------------------------------------------------
# Quantitative analysis
# ---------------------------------------------------------------------------


def analyze_retention(metrics: dict, channel_avg_retention: float | None = None) -> dict:
    """Analyze retention curve for drop-offs and high-retention points."""
    result = {
        "avg_retention": metrics.get("retention_rate"),
        "vs_channel_avg": None,
        "drop_off_points": [],
        "high_retention_points": [],
    }

    if channel_avg_retention is not None and metrics.get("retention_rate") is not None:
        diff = round(metrics["retention_rate"] - channel_avg_retention, 1)
        result["vs_channel_avg"] = {
            "channel_avg": channel_avg_retention,
            "this_video": metrics["retention_rate"],
            "diff_pp": diff,
        }

    curve = metrics.get("retention_curve") or {}
    if not curve:
        return result

    sorted_points = sorted(curve.items(), key=lambda x: float(x[0]))
    for i in range(1, len(sorted_points)):
        prev_pct, prev_val = sorted_points[i - 1]
        curr_pct, curr_val = sorted_points[i]
        drop = prev_val - curr_val
        if drop > 5.0:
            result["drop_off_points"].append({
                "position_pct": curr_pct,
                "retention_before": prev_val,
                "retention_after": curr_val,
                "drop_pp": round(drop, 1),
            })

    for pct, val in sorted_points:
        if val > 80.0 and float(pct) > 0:
            result["high_retention_points"].append({"position_pct": pct, "retention": val})

    return result


def analyze_ctr(metrics: dict, title: str, history: dict) -> dict:
    """Analyze CTR performance vs channel average."""
    insights = history.get("insights", {})
    channel_avg_ctr = insights.get("avg_ctr")

    result = {
        "ctr": metrics.get("ctr"),
        "impressions": metrics.get("impressions"),
        "channel_avg_ctr": channel_avg_ctr,
        "vs_channel_avg": None,
        "title_strategy": None,
    }

    if metrics.get("ctr") is not None and channel_avg_ctr is not None:
        diff = round(metrics["ctr"] - channel_avg_ctr, 1)
        result["vs_channel_avg"] = {"diff_pp": diff, "above_avg": diff > 0}

    # Detect title strategy
    if any(c.isdigit() for c in title):
        result["title_strategy"] = "with_numbers"
    elif "?" in title:
        result["title_strategy"] = "question_format"
    elif "어떻게" in title or "하는 법" in title or "방법" in title:
        result["title_strategy"] = "how_to"
    else:
        result["title_strategy"] = "other"

    return result


def analyze_traffic(metrics: dict) -> dict:
    """Analyze traffic source distribution."""
    sources = metrics.get("traffic_sources") or {}
    total = sum(sources.values()) if sources else 0

    result = {
        "sources": {},
        "top_source": None,
        "subscriber_ratio": None,
        "total_views_by_source": total,
    }

    if not sources or total == 0:
        return result

    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        result["sources"][source] = {
            "count": count,
            "pct": round(count / total * 100, 1),
        }

    top = max(sources, key=sources.get)
    result["top_source"] = {
        "name": top,
        "count": sources[top],
        "pct": round(sources[top] / total * 100, 1),
    }

    sub_count = sources.get("SUBSCRIBER", 0)
    result["subscriber_ratio"] = round(sub_count / total * 100, 1)

    return result


# ---------------------------------------------------------------------------
# analysis_context.md generation
# ---------------------------------------------------------------------------


def generate_analysis_context_md(
    project: dict, metrics: dict,
    retention_analysis: dict, ctr_analysis: dict, traffic_analysis: dict,
    comments: list[str], history: dict,
) -> str:
    """Generate Korean markdown context for Claude Code analysis."""
    views = metrics.get("views_4w") or metrics.get("views_1w") or metrics.get("views_72h") or 0
    period = "4w" if metrics.get("views_4w") else ("1w" if metrics.get("views_1w") else "72h")

    # Channel avg views
    avg_views = None
    videos = history.get("videos", [])
    if videos:
        all_views = []
        for v in videos:
            m = v.get("metrics", {})
            vw = m.get("views_4w") or m.get("views_1w") or m.get("views_72h")
            if vw is not None:
                all_views.append(vw)
        if all_views:
            avg_views = round(sum(all_views) / len(all_views))

    # Retention drop-off
    drop_offs = retention_analysis.get("drop_off_points", [])
    drop_lines = []
    if drop_offs:
        for dp in drop_offs[:5]:
            drop_lines.append(
                f"- 영상 {dp['position_pct']}% 지점: "
                f"{dp['retention_before']}% → {dp['retention_after']}% "
                f"(-{dp['drop_pp']}%p)"
            )
    else:
        drop_lines.append("- 급격한 이탈 구간 없음")

    # High retention
    high_points = retention_analysis.get("high_retention_points", [])
    high_lines = []
    if high_points:
        for hp in high_points[:5]:
            high_lines.append(f"- 영상 {hp['position_pct']}% 지점: {hp['retention']}%")
    else:
        high_lines.append("- 특별히 높은 리텐션 구간 없음")

    # Retention curve samples
    curve = metrics.get("retention_curve") or {}
    curve_lines = []
    if curve:
        for pt in ["1.0", "5.0", "10.0", "20.0", "30.0", "40.0", "50.0",
                    "60.0", "70.0", "80.0", "90.0", "100"]:
            if pt in curve:
                curve_lines.append(f"  {pt}%: {curve[pt]}%")

    # Traffic
    traffic_sources = traffic_analysis.get("sources", {})
    traffic_lines = [f"- {s}: {d['count']:,}회 ({d['pct']}%)" for s, d in traffic_sources.items()]

    # Comments
    comment_lines = [f"{i+1}. {c}" for i, c in enumerate(comments)]

    # Channel history
    insights = history.get("insights", {})
    channel_avg_ctr = insights.get("avg_ctr")
    channel_avg_retention = insights.get("avg_retention_rate")
    top_topics = insights.get("top_performing_topics", [])

    guest = project.get("meta", {}).get("guest")
    title = guest["name"] if guest and isinstance(guest, dict) else project["id"]

    subs_gained = metrics.get("subscribers_gained") or 0
    subs_lost = metrics.get("subscribers_lost") or 0

    return f"""# Analysis Context: {project['id']}

> 이 파일은 `collect_analytics.py`로 자동 생성된 분석 컨텍스트입니다.
> `/video analyze` 스킬로 review.md를 생성할 때 사용됩니다.

## 영상 정보

- **프로젝트**: {project['id']}
- **유형**: {project['type']}
- **제목/게스트**: {title}
- **Video ID**: {project.get('meta', {}).get('youtube_video_id') or 'N/A'}
- **수집 시점**: {period}

## 핵심 지표

| 지표 | 값 |
|------|-----|
| 조회수 ({period}) | {views:,} |
| 채널 평균 조회수 | {f'{avg_views:,}' if avg_views else 'N/A'} |
| CTR | {metrics.get('ctr') or 'N/A'}% |
| 채널 평균 CTR | {channel_avg_ctr or 'N/A'}% |
| 평균 시청 시간 | {metrics.get('avg_view_duration') or 'N/A'} |
| 시청 지속률 | {metrics.get('retention_rate') or 'N/A'}% |
| 채널 평균 리텐션 | {channel_avg_retention or 'N/A'}% |
| 노출수 | {metrics.get('impressions') or 'N/A'} |
| 좋아요 | {metrics.get('likes') or 'N/A'} |
| 댓글 수 | {metrics.get('comment_count') or 'N/A'} |
| 구독자 순증 | +{subs_gained - subs_lost} |

## 리텐션 분석 (자동)

### 리텐션 커브 (샘플)
{chr(10).join(curve_lines) if curve_lines else '- 데이터 없음'}

### 주요 이탈 구간
{chr(10).join(drop_lines)}

### 높은 리텐션 구간
{chr(10).join(high_lines)}

## CTR 분석 (자동)

- 제목 전략: {ctr_analysis.get('title_strategy', 'N/A')}
- 채널 평균 대비: {ctr_analysis.get('vs_channel_avg', {}).get('diff_pp', 'N/A') if ctr_analysis.get('vs_channel_avg') else 'N/A'}%p

## 트래픽 소스

{chr(10).join(traffic_lines) if traffic_lines else '- 데이터 없음'}
- 구독자 의존도: {traffic_analysis.get('subscriber_ratio', 'N/A')}%

## 원본 댓글 ({len(comments)}개)

{chr(10).join(comment_lines) if comment_lines else '- 댓글 없음'}

## 채널 히스토리

- 채널 평균 CTR: {channel_avg_ctr or 'N/A'}%
- 채널 평균 리텐션: {channel_avg_retention or 'N/A'}%
- 상위 토픽: {', '.join(top_topics) if top_topics else 'N/A'}
- 누적 영상 수: {len(videos)}개

---

> **다음 단계**: `/video analyze`를 실행하여 이 데이터를 기반으로 review.md를 생성하세요.
"""


# ---------------------------------------------------------------------------
# Collection pipeline
# ---------------------------------------------------------------------------


def run_collect(project_dir: Path, period: str, token_path: str | None = None) -> Path:
    """Full collection pipeline: collect → analyze → save context."""
    project = load_project(project_dir)

    video_id = project.get("meta", {}).get("youtube_video_id")
    if not video_id:
        print("Error: youtube_video_id not set in project.json", file=sys.stderr)
        sys.exit(1)

    # Determine published_at
    filming_date = project.get("meta", {}).get("filming_date")
    if filming_date:
        published_at = datetime.fromisoformat(filming_date)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
    else:
        published_at = datetime.fromisoformat(project["created_at"])
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

    # Load credentials and collect
    creds = load_credentials(token_path)
    print(f"Collecting {period} data for video {video_id}...")
    metrics, comments, raw_responses = collect_all(creds, video_id, published_at, period)

    # Save raw responses
    raw_path = project_dir / f"analytics_{period}.json"
    raw_path.write_text(
        json.dumps(raw_responses, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Raw data saved: {raw_path.name}")

    # Load history for analysis
    history = load_history()

    # Run quantitative analyses
    channel_avg_retention = history.get("insights", {}).get("avg_retention_rate")
    retention_analysis = analyze_retention(metrics, channel_avg_retention)

    guest = project.get("meta", {}).get("guest")
    title = guest["name"] if guest and isinstance(guest, dict) else project["id"]
    ctr_analysis = analyze_ctr(metrics, title, history)

    traffic_analysis = analyze_traffic(metrics)

    # Generate context markdown
    context_md = generate_analysis_context_md(
        project, metrics, retention_analysis, ctr_analysis,
        traffic_analysis, comments, history,
    )

    context_path = project_dir / ANALYSIS_CONTEXT_FILENAME
    context_path.write_text(context_md, encoding="utf-8")
    print(f"  Analysis context saved: {context_path.name}")

    # Start phase 6
    project = start_phase(project, 6)
    save_project(project, project_dir)

    return context_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect YouTube Analytics data and generate analysis context"
    )
    parser.add_argument("--project-dir", required=True, help="Project directory path")
    parser.add_argument(
        "--period", required=True, choices=["72h", "1w", "4w"],
        help="Collection period"
    )
    parser.add_argument("--token-path", help="Path to YouTube OAuth token file")

    args = parser.parse_args()

    project_dir = _validate_path(args.project_dir)
    context_path = run_collect(project_dir, args.period, args.token_path)
    print(f"\nDone. Next: /video analyze")


if __name__ == "__main__":
    main()
