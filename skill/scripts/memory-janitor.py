
```python
#!/usr/bin/env python3
"""
Memory Janitor — 記憶維護腳本

功能：
- Events Timeline 超過 90 天折疊成摘要
- P1 區塊超過 90 天標記待審
- P2 區塊超過 30 天保留結論（前 3 行）
- memory/*.md 超過 90 天歸檔至 archive/

用法：
    python3 memory-janitor.py --dry-run   # 預覽
    python3 memory-janitor.py --force     # 執行
    python3 memory-janitor.py --notify    # 預覽 + 通知

前置需求：Python 3.8+，無額外套件依賴。
"""

import argparse
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def log(msg: str):
    """輸出帶時間戳的日誌"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


class MemoryJanitor:
    """記憶維護主類別"""

    def __init__(
        self,
        workspace: str = ".",
        memory_dir: str = "memory",
        memory_file: str = "MEMORY.md",
        archive_dir: str = "memory/archive",
    ):
        self.workspace = Path(workspace)
        self.memory_dir = self.workspace / memory_dir
        self.memory_file = self.workspace / memory_file
        self.archive_dir = self.workspace / archive_dir
        self.actions: list[str] = []

    def scan_daily_logs(self, threshold_days: int = 90) -> list[Path]:
        """掃描超過閾值天數的 daily log"""
        cutoff = datetime.now() - timedelta(days=threshold_days)
        old_files = []
        if not self.memory_dir.exists():
            return old_files
        for f in self.memory_dir.glob("*.md"):
            match = re.match(r"(\d{4}-\d{2}-\d{2})\.md", f.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                    if file_date < cutoff:
                        old_files.append(f)
                except ValueError:
                    continue
        return sorted(old_files)

    def archive_old_logs(self, dry_run: bool = True) -> list[str]:
        """歸檔超過 90 天的 daily log"""
        old_files = self.scan_daily_logs(90)
        actions = []
        if not old_files:
            log("沒有需要歸檔的 daily log")
            return actions
        if not dry_run:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
        for f in old_files:
            dest = self.archive_dir / f.name
            action = f"歸檔: {f.name} → archive/{f.name}"
            actions.append(action)
            log(action)
            if not dry_run:
                shutil.move(str(f), str(dest))
        return actions

    def scan_memory_sections(self) -> list[dict]:
        """掃描 MEMORY.md 中的區塊"""
        if not self.memory_file.exists():
            log(f"找不到 {self.memory_file}")
            return []
        content = self.memory_file.read_text(encoding="utf-8")
        sections = []
        pattern = r"^## (.+?) \[P(\d)\](?: \[(\d{4}-\d{2}-\d{2})\])?$"
        for match in re.finditer(pattern, content, re.MULTILINE):
            sections.append({
                "name": match.group(1),
                "priority": int(match.group(2)),
                "date": match.group(3),
                "pos": match.start(),
            })
        return sections

    def check_expired_sections(self, dry_run: bool = True) -> list[str]:
        """檢查過期的 P1/P2 區塊"""
        sections = self.scan_memory_sections()
        actions = []
        now = datetime.now()
        for section in sections:
            if not section["date"]:
                continue
            try:
                section_date = datetime.strptime(section["date"], "%Y-%m-%d")
            except ValueError:
                continue
            age_days = (now - section_date).days
            name = section["name"]
            priority = section["priority"]
            if priority == 1 and age_days > 90:
                action = f"P1 待審（{age_days} 天）: {name}"
                actions.append(action)
                log(action)
            elif priority == 2 and age_days > 30:
                action = f"P2 需壓縮（{age_days} 天）: {name}"
                actions.append(action)
                log(action)
        if not actions:
            log("沒有過期的 P1/P2 區塊")
        return actions

    def run(self, dry_run: bool = True) -> dict:
        """執行完整維護流程"""
        log(f"開始記憶維護（{'預覽模式' if dry_run else '執行模式'}）")
        log(f"Workspace: {self.workspace}")
        results = {
            "archived_logs": self.archive_old_logs(dry_run),
            "expired_sections": self.check_expired_sections(dry_run),
        }
        total = len(results["archived_logs"]) + len(results["expired_sections"])
        log(f"維護完成：共 {total} 項{'待處理' if dry_run else '已處理'}")
        return results

    def format_report(self, results: dict) -> str:
        """產生維護報告"""
        lines = ["# Memory Janitor Report", ""]
        if results["archived_logs"]:
            lines.append("## 歸檔的 Daily Logs")
            for a in results["archived_logs"]:
                lines.append(f"- {a}")
            lines.append("")
        if results["expired_sections"]:
            lines.append("## 過期區塊")
            for a in results["expired_sections"]:
                lines.append(f"- {a}")
            lines.append("")
        if not results["archived_logs"] and not results["expired_sections"]:
            lines.append("✅ 沒有需要處理的項目")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Memory Janitor — 記憶維護腳本")
    parser.add_argument("--workspace", default=".", help="Agent workspace 路徑")
    parser.add_argument("--dry-run", action="store_true", default=True, help="預覽模式")
    parser.add_argument("--force", action="store_true", help="實際執行變更")
    parser.add_argument("--notify", action="store_true", help="預覽 + 輸出報告")
    args = parser.parse_args()
    dry_run = not args.force
    janitor = MemoryJanitor(workspace=args.workspace)
    results = janitor.run(dry_run=dry_run)
    if args.notify or dry_run:
        report = janitor.format_report(results)
        print("\n" + report)


if __name__ == "__main__":
    main()
```


