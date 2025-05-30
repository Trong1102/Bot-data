import json
import requests
from bs4 import BeautifulSoup

def get_clean_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        # Xoá các thẻ không cần thiết
        for tag in soup(["script", "style", "meta", "noscript", "head", "link"]):
            tag.decompose()

        # Lấy phần thân trang
        body = soup.body
        if not body:
            body = soup  # fallback nếu không có thẻ <body>

        # Lấy text, bỏ khoảng trắng thừa
        text = body.get_text(separator="\n", strip=True)

        # Lọc bỏ dòng trống
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = "\n".join(lines)

        return cleaned_text

    except Exception as e:
        return f"❌ Lỗi: {e}"

all_promotions = []

with open("/Users/hehe/Documents/VSC/links_click_discovered.json", "r", encoding="utf-8") as f:
    links = json.load(f)

for url in links:  # links là danh sách URL đã lọc
    print(f"📥 Đang xử lý: {url}")
    text = get_clean_text(url)
    all_promotions.append({
        "url": url,
        "text": text
    })

# Ghi ra file JSON
with open("clean_promotions.json", "w", encoding="utf-8") as f:
    json.dump(all_promotions, f, ensure_ascii=False, indent=2)

print("🎉 Đã lưu tất cả vào clean_promotions.json")
