# Chatbot Discord - Giá & Khuyến mãi

Dự án này bao gồm một chatbot được triển khai trên Discord, có khả năng cung cấp thông tin về giá và khuyến mãi từ dữ liệu được crawl tự động.

## 📁 Cấu trúc thư mục

- **`Crawl/`**  
  Chứa mã nguồn Python để **crawl dữ liệu** về **giá sản phẩm** và **chương trình khuyến mãi** từ các nguồn khác nhau.

- **`training bot/`**  
  Bao gồm các **file `.txt`** dùng để **huấn luyện chatbot**, nhằm giúp bot hiểu và phản hồi các câu hỏi từ người dùng.

- **`main.py`**  
  Là file chính dùng để **chạy server chatbot** trên **Discord**. Khi chạy file này, bot sẽ hoạt động và tương tác trực tiếp với người dùng trong kênh Discord.

## 🚀 Cách sử dụng

1. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
