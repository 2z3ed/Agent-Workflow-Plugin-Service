"""测试邮箱 IMAP 读取功能"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugins.email.email_fetcher import EmailFetcher

def main():
    fetcher = EmailFetcher()
    try:
        emails = fetcher.fetch_recent_unread(
            limit=5,
            lookback_days=30,
            only_unread=True,
        )
        print(f"✅ 成功读取到 {len(emails)} 封未读邮件")
        for i, email in enumerate(emails[:3], 1):
            print(f"   {i}. {email.get('subject', '')} (来自 {email.get('sender', '')})")
        if len(emails) > 3:
            print(f"   ... 还有 {len(emails)-3} 封")
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())