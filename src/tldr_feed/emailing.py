import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any

import markdown

from .models import AppConfig, RunRecord


def send_email_report(config: AppConfig, report_paths: dict[str, str], run: RunRecord) -> bool:
    if not config.email or not config.email.smtp_host:
        print("Email settings not configured. Skipping email.")
        return False
        
    if not config.email.email_to:
        print("No recipients configured. Skipping email.")
        return False

    print(f"Preparing to email reports to {config.email.email_to}...")

    html_styles = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { border-bottom: 2px solid #eaecef; padding-bottom: 0.3em; margin-top: 1.5em; }
        h2 { border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; margin-top: 1.2em; }
        h3 { margin-top: 1em; }
        a { color: #0366d6; text-decoration: none; }
        a:hover { text-decoration: underline; }
        blockquote { padding: 0 1em; color: #6a737d; border-left: 0.25em solid #dfe2e5; margin: 0 0 16px 0; }
        hr { border: 0; background-color: #e1e4e8; height: 1px; margin: 24px 0; }
        img { max-width: 100%; box-sizing: border-box; }
    </style>
    """

    try:
        if config.email.smtp_port == 465:
            server = smtplib.SMTP_SSL(config.email.smtp_host, config.email.smtp_port)
        else:
            server = smtplib.SMTP(config.email.smtp_host, config.email.smtp_port)
            server.starttls()
            
        if config.email.smtp_username and config.email.smtp_password:
            server.login(config.email.smtp_username, config.email.smtp_password)
            
        success_count = 0

        for report_type, path in report_paths.items():
            if report_type == "json":
                continue
            
            md_file = Path(path)
            if not md_file.exists():
                continue
                
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                continue

            msg = EmailMessage()
            
            # Use dynamic subject based on report type, week, and dates
            title_prefix = "Papers" if report_type == "paper" else "News"
            week_str = run.requested_week.replace("-", " ") 
            date_str = f"{run.window_start} to {run.window_end}"
            msg['Subject'] = f"Weekly Research TLDR: {title_prefix} - {week_str} ({date_str})"
            msg['From'] = config.email.email_from
            msg['To'] = ", ".join(config.email.email_to)

            images_to_embed = {}
            img_pattern = re.compile(r'!\[.*?\]\(([^)]+\.png)\)')
            for match in img_pattern.finditer(content):
                img_filename = match.group(1)
                img_path = md_file.parent / img_filename
                if img_path.exists():
                    images_to_embed[img_filename] = img_path

            # Convert markdown to html
            html_content = markdown.markdown(content, extensions=['tables', 'fenced_code'])

            # Replace local src attributes with cid: references
            cids = {}
            for img_filename, img_path in images_to_embed.items():
                cid = make_msgid(domain=config.email.email_from.split('@')[-1])
                cids[img_filename] = (cid, img_path)
                html_content = html_content.replace(f'src="{img_filename}"', f'src="cid:{cid[1:-1]}"')

            final_html = f"<!DOCTYPE html><html><head>{html_styles}</head><body>{html_content}</body></html>"
            msg.add_alternative(final_html, subtype='html')

            for img_filename, (cid, img_path) in cids.items():
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                msg.get_payload()[0].add_related(
                    img_data, 
                    maintype='image', 
                    subtype='png', 
                    cid=cid
                )

            print(f"Sending {report_type} email...")
            server.send_message(msg)
            success_count += 1

        server.quit()
        if success_count > 0:
            print(f"Successfully sent {success_count} emails!")
            return True
        else:
            print("No reports found to email.")
            return False

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
