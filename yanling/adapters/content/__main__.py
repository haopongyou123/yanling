"""内容适配器 CLI — 手动录入发布记录 / 查看统计.

用法:
    python3 -m yanling.adapters.content record \\
        --article_id 7412345678901234567 \\
        --platform juejin \\
        --date 2026-05-14 \\
        --title "文章标题" \\
        --topics AI,编程

    python3 -m yanling.adapters.content status
    python3 -m yanling.adapters.content set-user-id <juejin_user_id>
"""

from __future__ import annotations

import argparse
import json
import sys

from yanling.adapters.content import (
    ContentMonitor, FeedbackCollector, PublishedTracker,
    PlatformStatsScraper,
)
from yanling.adapters.content.scraper import PublishedArticle, set_juejin_user_id


def cmd_record(args: argparse.Namespace):
    """记录一条发布。"""
    tracker = PublishedTracker()
    tracker.load()
    tracker.add(PublishedArticle(
        article_id=args.article_id,
        platform=args.platform,
        date=args.date,
        title=args.title or "",
        topics=args.topics.split(",") if args.topics else [],
    ))
    tracker.save()
    print(f"✅ 已记录: [{args.platform}] {args.article_id} ({args.date})")


def cmd_status(args: argparse.Namespace):
    """查看当前追踪状态。"""
    tracker = PublishedTracker()
    tracker.load()
    print(f"已追踪文章: {tracker.count}")
    for a in tracker.articles:
        stats_str = ""
        if a.stats:
            stats_str = f" views={a.stats.get('views', 0)} likes={a.stats.get('likes', 0)}"
        print(f"  [{a.platform}] {a.date} {a.title or a.article_id}{stats_str}")

    # 反馈统计
    feedback = FeedbackCollector()
    import asyncio
    asyncio.run(feedback.start())
    stats = feedback.topic_statistics()
    if stats.get("total_entries", 0):
        print(f"\n反馈数据: {stats['total_entries']} 条, {stats['topic_count']} 个主题")
        for topic, data in stats.get("topics", {}).items():
            print(f"  {topic}: avg={data['avg']} views={data['views']}")

    # 内容监视器
    monitor = ContentMonitor()
    asyncio.run(monitor.start())
    print(f"\n检测到发布内容: {monitor.total_detected} 篇")
    dist = monitor.topic_distribution
    if dist:
        print("主题分布:")
        for topic, count in sorted(dist.items(), key=lambda x: -x[1])[:5]:
            print(f"  {topic}: {count}次")


def cmd_set_user_id(args: argparse.Namespace):
    """设置掘金用户 ID。"""
    set_juejin_user_id(args.user_id)
    print(f"✅ 掘金用户 ID 已设置为: {args.user_id}")
    print("   建议加入 ~/.bashrc: export JUJIN_USER_ID={}".format(args.user_id))


def main():
    parser = argparse.ArgumentParser(description="内容适配器工具")
    sub = parser.add_subparsers()

    p_record = sub.add_parser("record", help="记录一条发布")
    p_record.add_argument("--article_id", required=True)
    p_record.add_argument("--platform", default="juejin")
    p_record.add_argument("--date", required=True)
    p_record.add_argument("--title", default="")
    p_record.add_argument("--topics", default="")
    p_record.set_defaults(func=cmd_record)

    p_status = sub.add_parser("status", help="查看追踪状态")
    p_status.set_defaults(func=cmd_status)

    p_uid = sub.add_parser("set-user-id", help="设置掘金用户 ID")
    p_uid.add_argument("user_id")
    p_uid.set_defaults(func=cmd_set_user_id)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
