# -*- coding: utf-8 -*-
"""
YouTube 近期视频爬取脚本
=======================
参考仓库: https://github.com/ShaoQiBNU/YouTube_get_video

功能: 爬取指定 YouTube 账号最近 3 天发布的视频标题与链接，
      输出结构化 JSON 到 OUTPUT/YY_MM_DD/youtube.json

支持两种模式:
  模式A — YouTube Data API v3 (推荐, 需要 API Key)
  模式B — yt-dlp 纯本地爬取 (无需 API Key)

======================================================================
依赖安装
======================================================================

  # 模式A (推荐): 需要 YouTube Data API v3 Key
  pip install google-api-python-client yt-dlp

  # 模式B: 无需 API Key, 仅需 yt-dlp
  pip install yt-dlp

  # 一次性安装全部依赖 (两种模式都可用):
  pip install google-api-python-client yt-dlp

======================================================================
配置说明
======================================================================

  【必须配置】CHANNEL_URLS — 添加要爬取的 YouTube 频道主页链接

  CHANNEL_URLS = [
      "https://www.youtube.com/@OpenAI",              # @handle 格式
      "https://www.youtube.com/c/GoogleDevelopers",    # /c/ 自定义名格式
      "https://www.youtube.com/channel/UCxxxx",        # /channel/ ID格式
  ]

  【可选配置】YOUTUBE_API_KEY — YouTube Data API v3 密钥
    不填则自动使用模式B (yt-dlp)
    申请步骤:
      1. 访问 https://console.cloud.google.com/apis/credentials
      2. 创建项目 → 创建 API Key
      3. 启用 "YouTube Data API v3"
      4. 将 Key 粘贴到下方 YOUTUBE_API_KEY 变量中

  【可选配置】DAYS_BACK — 回溯天数, 默认 3
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── 第三方库导入 ────────────────────────────────────────────────────
# google-api-python-client: YouTube Data API v3 客户端 (模式A必需)
#   pip install google-api-python-client
try:
    from googleapiclient.discovery import build as build_youtube_client
except ImportError:
    build_youtube_client = None  # 未安装则模式A不可用

# yt-dlp: YouTube 视频元数据爬取库 (模式B必需, 模式A中用于解析频道ID)
#   pip install yt-dlp
try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ════════════════════════════════════════════════════════════════════
# 配置区 — 修改下方变量即可
# ════════════════════════════════════════════════════════════════════

# 【可选】YouTube Data API v3 Key
#   不填写则自动使用 yt-dlp 模式 (无需 API Key)
#   申请地址: https://console.cloud.google.com/apis/credentials
#   需启用 "YouTube Data API v3"
YOUTUBE_API_KEY = ""  # <-- 在此粘贴你的 API Key

# 【必须】要爬取的 YouTube 频道主页链接
#   支持三种格式:
#     https://www.youtube.com/@handle          例: @OpenAI
#     https://www.youtube.com/c/自定义名       例: /c/GoogleDevelopers
#     https://www.youtube.com/channel/UCxxxx   例: /channel/UC_x5XG1OV2P6uZZ5FSM9Ttw
#   在下方列表中添加更多频道链接:
CHANNEL_URLS = [
    # "https://www.youtube.com/@OpenAI",
]

# 【可选】回溯天数, 默认 3 (即爬取最近 3 天的视频)
DAYS_BACK = 3


# ════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════

def _cutoff_date(days: int = DAYS_BACK) -> datetime:
    """计算回溯截止日期 (UTC 当日零点减去 days 天)"""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=days)


def _parse_upload_date(date_str: str) -> datetime:
    """将 'YYYYMMDD' 或 'YYYY-MM-DD' 解析为 UTC datetime"""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    clean = date_str.replace("-", "")[:8]
    if len(clean) < 8:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime(int(clean[:4]), int(clean[4:6]), int(clean[6:8]), tzinfo=timezone.utc)


def _format_date(date_str: str) -> str:
    """将 'YYYYMMDD' 格式化为 'YYYY-MM-DD'"""
    if len(date_str) >= 8:
        return date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:8]
    return date_str


def _ensure_videos_url(channel_url: str) -> str:
    """确保频道 URL 指向 /videos 页面 (yt-dlp 需要此路径获取完整元数据)"""
    url = channel_url.rstrip("/")
    if url.endswith("/videos"):
        return url
    return url + "/videos"


def _resolve_channel_id(channel_url: str) -> Optional[str]:
    """
    将频道 URL 解析为频道 ID (UC... 格式)

    策略:
      1. URL 中已包含 /channel/UCxxxx → 直接提取
      2. 否则使用 yt-dlp 解析频道 ID
    """
    m = re.search(r"/channel/(UC[\w-]{22,})", channel_url)
    if m:
        return m.group(1)

    if yt_dlp is None:
        print("  警告: 无法解析频道 ID: " + channel_url)
        print("  请安装 yt-dlp (pip install yt-dlp) 或使用 /channel/UCxxxx 格式链接")
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if info:
                channel_id = info.get("channel_id") or info.get("id")
                if channel_id and channel_id.startswith("UC"):
                    return channel_id
    except Exception as e:
        print("  警告: yt-dlp 解析频道 ID 失败: " + str(e))

    return None


# ════════════════════════════════════════════════════════════════════
# 模式A: YouTube Data API v3 (需要 YOUTUBE_API_KEY)
# ════════════════════════════════════════════════════════════════════

def _fetch_recent_videos_api(channel_url: str, cutoff: datetime) -> list[dict]:
    """
    使用 YouTube Data API v3 获取频道的近期视频

    流程:
      1. 解析频道 URL → 频道 ID
      2. channels.list → 获取 uploadsPlaylistId
      3. playlistItems.list → 获取近期视频 ID
      4. videos.list → 获取精确发布时间用于日期过滤

    比参考仓库中的 search.list 方案更省配额
    """
    if build_youtube_client is None:
        print("  错误: google-api-python-client 未安装, 请运行 pip install google-api-python-client")
        return []

    if not YOUTUBE_API_KEY:
        print("  错误: YOUTUBE_API_KEY 未设置")
        return []

    youtube = build_youtube_client("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    # Step 1: 解析频道 ID
    channel_id = _resolve_channel_id(channel_url)
    if not channel_id:
        print("  无法解析频道 ID, 跳过")
        return []

    # Step 2: 获取上传播放列表 ID
    ch_response = youtube.channels().list(
        part="contentDetails,snippet",
        id=channel_id,
    ).execute()

    items = ch_response.get("items", [])
    if not items:
        print("  未找到频道: " + channel_id)
        return []

    channel_title = items[0]["snippet"]["title"]
    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print("  频道: " + channel_title)

    # Step 3-4: 获取近期视频元数据
    results: list[dict] = []
    next_page_token = None
    past_cutoff = False

    while not past_cutoff:
        pl_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token,
        ).execute()

        video_ids = []
        for item in pl_response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId", "")
            if video_id:
                video_ids.append(video_id)

        if not video_ids:
            break

        vid_response = youtube.videos().list(
            part="snippet",
            id=",".join(video_ids),
        ).execute()

        for vid in vid_response.get("items", []):
            published_at = vid["snippet"]["publishedAt"]
            pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            if pub_dt < cutoff:
                past_cutoff = True
                continue

            results.append({
                "channel": vid["snippet"].get("channelTitle", channel_title),
                "title": vid["snippet"]["title"].strip(),
                "url": "https://www.youtube.com/watch?v=" + vid["id"],
                "upload_date": published_at[:10],
            })

        next_page_token = pl_response.get("nextPageToken")
        if not next_page_token:
            break

    return results


# ════════════════════════════════════════════════════════════════════
# 模式B: yt-dlp 纯本地爬取 (无需 API Key)
# ════════════════════════════════════════════════════════════════════

def _fetch_recent_videos_ytdlp(channel_url: str, cutoff: datetime) -> list[dict]:
    """
    使用 yt-dlp 爬取频道近期视频 (无需 API Key)

    使用 /videos 页面 + 非扁平模式获取 upload_date
    遇到超出回溯日期的视频时提前终止
    """
    if yt_dlp is None:
        print("  错误: yt-dlp 未安装, 请运行 pip install yt-dlp")
        return []

    videos_url = _ensure_videos_url(channel_url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "playlistend": 30,       # 只扫描最近30个上传 (3天足够)
        "skip_download": True,
        # 不使用 extract_flat — 需要获取 upload_date, 只有完整元数据模式才包含
    }

    results: list[dict] = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(videos_url, download=False)

        if info is None:
            print("  警告: 未获取到数据: " + channel_url)
            return results

        channel_name = info.get("channel", info.get("uploader", "未知"))
        print("  频道: " + channel_name)

        entries = info.get("entries") or []

        for entry in entries:
            if entry is None:
                continue

            upload_date_raw = entry.get("upload_date", "")
            if not upload_date_raw:
                continue

            pub_time = _parse_upload_date(upload_date_raw)

            if pub_time < cutoff:
                # 视频按最新排序, 遇到超出日期的可提前退出
                break

            video_id = entry.get("id", "")
            title = entry.get("title", "").strip()

            url = entry.get("webpage_url", "")
            if not url and video_id:
                url = "https://www.youtube.com/watch?v=" + video_id

            results.append({
                "channel": channel_name,
                "title": title,
                "url": url,
                "upload_date": _format_date(upload_date_raw),
            })

    return results


# ════════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════════

def main():
    # Fix Windows console encoding for Chinese output
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not CHANNEL_URLS:
        print("错误: CHANNEL_URLS 为空")
        print("  请在脚本中添加 YouTube 频道链接, 例如:")
        print('  CHANNEL_URLS = ["https://www.youtube.com/@OpenAI"]')
        sys.exit(1)

    # 自动选择模式
    use_api = bool(YOUTUBE_API_KEY) and build_youtube_client is not None
    if use_api:
        print("模式: YouTube Data API v3")
    elif yt_dlp is not None:
        print("模式: yt-dlp (无 API Key)")
    else:
        print("错误: 无可用爬取方式")
        print("  请安装至少一种依赖:")
        print("    pip install google-api-python-client yt-dlp   (模式A)")
        print("    pip install yt-dlp                             (模式B)")
        sys.exit(1)

    # 创建输出目录 OUTPUT/YY_MM_DD/
    today = datetime.now()
    date_dir = today.strftime("%y_%m_%d")   # 例如 26_07_08

    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "OUTPUT", date_dir
    )
    os.makedirs(output_dir, exist_ok=True)

    cutoff = _cutoff_date()
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    print("爬取 " + cutoff_str + " 至今的视频 (最近 " + str(DAYS_BACK) + " 天) ...\n")

    # 逐频道爬取
    all_videos: list[dict] = []

    for url in CHANNEL_URLS:
        print("  来源: " + url)

        if use_api:
            videos = _fetch_recent_videos_api(url, cutoff)
        else:
            videos = _fetch_recent_videos_ytdlp(url, cutoff)

        print("    -> 找到 " + str(len(videos)) + " 个视频\n")
        all_videos.extend(videos)

    # 保存为 youtube.json
    file_date = today.strftime("%y%m%d")  # e.g. 260708
    output_file = os.path.join(output_dir, file_date + "youtube.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, ensure_ascii=False, indent=2)

    print("完成 — " + str(len(all_videos)) + " 个视频已保存到 " + output_file)


if __name__ == "__main__":
    main()