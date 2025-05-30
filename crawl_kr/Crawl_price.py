from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time

options = Options()
# options.add_argument("--headless")  # Mở nếu bạn muốn chạy ngầm
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

# URL chính
driver.get("https://gangnam.museclinic.co.kr/en/pages/category")

# Chờ tab/button hiện ra (⚠️ bạn sửa class selector tại đây nếu cần)
wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "category-btn")))  # thay class nếu cần
tabs = driver.find_elements(By.CLASS_NAME, "category-btn")  # hoặc "cursor-pointer", v.v.

all_results = []

# Lặp từng tab
for i in range(len(tabs)):
    try:
        # Reload lại list do DOM thay đổi sau mỗi click
        tabs = driver.find_elements(By.CLASS_NAME, "category-btn")
        tab = tabs[i]
        tab_name = tab.text.strip()

        # Click tab
        driver.execute_script("arguments[0].scrollIntoView(true);", tab)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", tab)
        time.sleep(1.5)  # Chờ nội dung load

        # Lấy tất cả treatment-card sau khi click
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "treatment-card")))
        cards = driver.find_elements(By.CLASS_NAME, "treatment-card")

        tab_data = []

        for card in cards:
            try:
                name = card.get_attribute("data-name")
                price_block = card.find_element(By.CLASS_NAME, "treatment-price")

                def get_text(class_name):
                    try:
                        return price_block.find_element(By.CLASS_NAME, class_name).text.strip()
                    except:
                        return ""

                tab_data.append({
                    "name": name,
                    "discount": get_text("discount"),
                    "price": get_text("price"),
                    "origin_price": get_text("original-price"),
                    "vat_notice": get_text("vat-notice")
                })

            except Exception as e:
                print("⚠️ Lỗi treatment-card:", e)

        print(f"✅ Tab '{tab_name}' có {len(tab_data)} gói.")
        all_results.append({
            "tab": tab_name,
            "treatments": tab_data
        })

    except Exception as e:
        print(f"❌ Lỗi khi xử lý tab {i}: {e}")

# Lưu dữ liệu
with open("/Users/hehe/Documents/VSC/crawl_kr/price.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("🎉 Đã lưu vào all_treatment_tabs.json")
driver.quit()
# Lưu vào file JSON

