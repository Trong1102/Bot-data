from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time

# Setup trình duyệt
options = Options()
# options.add_argument("--headless")  # Bỏ ghi chú nếu muốn chạy ẩn

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

base_url = "https://skinbeam.hk/en/event/ongoing"
driver.get(base_url)

wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "cursor-pointer")))

links = []

# Duyệt qua từng phần tử có class "cursor-pointer"
for index in range(20):  # Giới hạn tạm 20 mục để tránh quá tải
    try:
        # Reload lại element list mỗi vòng lặp (DOM sẽ reload sau mỗi back)
        items = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "cursor-pointer")))
        item = items[index]
        driver.execute_script("arguments[0].scrollIntoView(true);", item)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", item)  # Dùng JavaScript click tránh lỗi tương tác

        # Chờ trang mới load
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)

        current_url = driver.current_url
        print(f"✅ {index + 1}. URL:", current_url)
        links.append(current_url)

        driver.back()
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "cursor-pointer")))

    except Exception as e:
        print(f"⚠️ Lỗi ở mục {index + 1}: {e}")
        driver.get(base_url)  # Reload lại trang gốc nếu gặp lỗi
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "cursor-pointer")))

# Lưu kết quả
links = links[2:]
with open("links_click_discovered.json", "w", encoding="utf-8") as f:
    json.dump(links, f, ensure_ascii=False, indent=2)

print("🎉 Đã lưu danh sách link vào links_click_discovered.json")

driver.quit()
