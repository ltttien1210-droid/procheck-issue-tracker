# ProCheck — Theo dõi lỗi phần mềm

ProCheck là web app tiếng Việt để ghi nhận, xử lý và kiểm thử lại lỗi trong một nhóm phát triển phần mềm. Stack gồm Python 3.11+, Flask, SQLAlchemy, SQL Server và HTML/CSS/JavaScript. Có chế độ SQLite để xem demo và chạy kiểm thử nhanh.

## Nâng cấp từ bản đầu tiên

Dừng ứng dụng, chép đè mã nguồn từ ZIP vào thư mục ProCheck hiện tại, giữ lại tệp `.env` và thư mục `instance/`. Chạy lại `init-db` để tạo bảng `issue_verifications`; lệnh này giữ dữ liệu và tài khoản cũ. Mở lại ứng dụng bằng lệnh `run` đang dùng. Các lượt kiểm thử từ bản cũ vẫn được tính vào thống kê theo lịch sử trạng thái. Phiếu có môi trường và phiên bản xuất hiện từ bản này trở đi.

Ví dụ trên macOS nếu môi trường ảo đang dùng là `.venv312`:

```zsh
./.venv312/bin/python -m flask --app procheck init-db
./.venv312/bin/python -m flask --app procheck run --port 5050
```

## Chạy trên Windows với SQL Server Express

Cài Python 3.11 trở lên, SQL Server Express, SSMS và **Microsoft ODBC Driver 18 for SQL Server**. Mở PowerShell tại thư mục có tệp `requirements.txt`.

### 1. Cài thư viện và tạo khóa phiên

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Dán chuỗi vừa tạo vào `SECRET_KEY` trong `.env`. Mỗi máy dùng một khóa riêng. Tệp `.env` được bỏ qua khi đưa code lên Git.

### 2. Tạo cơ sở dữ liệu

Trong SSMS, kết nối bằng **Windows Authentication**, mở rồi chạy tệp `database/create_database.sql`. Mặc định `.env` trỏ tới `localhost\SQLEXPRESS`. Nếu SSMS đang dùng tên máy chủ khác, thay giá trị `SERVER=` bằng tên đó. Tài khoản Windows chạy ứng dụng cần có quyền trên cơ sở dữ liệu ProCheck.

Cấu hình mẫu dùng mã hóa kết nối và chấp nhận chứng chỉ cục bộ của SQL Server Express. Với máy chủ dùng chung, cấu hình chứng chỉ đáng tin cậy và đặt `TrustServerCertificate=no`. Có thể dùng tài khoản Windows riêng cho tiến trình web, cấp quyền đọc bảng tài khoản, đọc/thêm/sửa bảng báo cáo và đọc/thêm bảng lịch sử và phiếu kiểm thử. Tách quyền tạo bảng và quản lý tài khoản khỏi tiến trình web khi chạy trong môi trường dùng chung.

### 3. Tạo bảng, tài khoản và mở ứng dụng

```powershell
.\.venv\Scripts\python.exe -m flask --app procheck init-db
.\.venv\Scripts\python.exe -m flask --app procheck create-user tien
.\.venv\Scripts\python.exe -m flask --app procheck seed-demo tien
.\.venv\Scripts\python.exe -m flask --app procheck run --host 127.0.0.1
```

Lệnh `create-user` yêu cầu nhập mật khẩu hai lần và ẩn nội dung nhập. Dùng mật khẩu từ 12 đến 128 ký tự. Lệnh `seed-demo` là tùy chọn, thêm một báo cáo mẫu cho mỗi trạng thái và hai kết quả kiểm thử minh họa khi danh sách đang trống.

Mở [http://127.0.0.1:5000](http://127.0.0.1:5000), đăng nhập bằng tài khoản vừa tạo. Cấu hình này phục vụ máy local. Khi tích hợp với máy chủ HTTPS dùng chung, cấu hình tên miền được phép trong `TRUSTED_HOSTS`, bật `SESSION_COOKIE_SECURE=1` và dùng máy chủ WSGI phù hợp.

### Xem nhanh với SQLite

Làm bước 1, đổi `DATABASE_BACKEND=sqlite` trong `.env`, sau đó thực hiện thẳng bước 3. Dữ liệu demo nằm trong `instance/procheck.sqlite`. Hai chế độ dùng cơ sở dữ liệu riêng. Trên macOS hoặc Linux, dùng `python3 -m venv .venv` và thay đường dẫn Python trong lệnh bằng `.venv/bin/python`.

## Cách dùng

1. Bấm **Tạo báo cáo**. Nhập tiêu đề, mô tả, mức độ và tên người xử lý nếu đã phân công.
2. Dùng ô tìm kiếm theo tiêu đề/tên người xử lý hoặc kết hợp bộ lọc mức độ và trạng thái. Bốn ô đầu trang hiển thị tổng báo cáo theo trạng thái.
3. Mở báo cáo và cập nhật trạng thái theo luồng **Mới → Đang xử lý → Chờ kiểm thử → Đã đóng**.
4. Ở trạng thái **Chờ kiểm thử**, chọn **Đạt · Đóng lỗi** hoặc **Chưa đạt · Trả về xử lý**. Nhập môi trường, phiên bản và kết quả thực tế hoặc lý do trả lại. Có thể gửi kiểm thử lại sau khi sửa.
5. Xem lịch sử để biết ai tạo, sửa, chuyển trạng thái và từng kiểm thử trên bản nào. Tên người xử lý là nhãn phân công, có thể nhập tự do. Tài khoản đăng nhập được dùng để ghi người thực hiện thao tác. Các tài khoản tạo bằng CLI có quyền thao tác như nhau trong nhóm.
6. Mở **Tổng quan chất lượng** để xem lỗi mức cao hoặc nghiêm trọng còn mở, phân bố theo mức độ và các phiếu kiểm thử gần đây. Tỷ lệ đạt = số lượt đạt chia cho tổng lượt đạt và trả lại trong toàn bộ lịch sử. Một báo cáo có thể có nhiều lượt kiểm thử.

## Cấu trúc mã nguồn

| Vị trí | Trách nhiệm |
|---|---|
| `procheck/__init__.py` | Khởi tạo Flask, kết nối cơ sở dữ liệu, CSRF, cấu hình cookie và các header HTTP |
| `procheck/models.py` | Bảng tài khoản, báo cáo, lịch sử, phiếu kiểm thử và các quy tắc chuyển trạng thái |
| `procheck/auth.py` | Đăng nhập, đăng xuất, nạp tài khoản và giới hạn số lần thử |
| `procheck/issues.py` | Danh sách, bộ lọc, tạo/sửa, chuyển trạng thái, phiếu kiểm thử và tổng quan |
| `procheck/commands.py` | Lệnh tạo bảng, tạo tài khoản và thêm dữ liệu mẫu |
| `procheck/templates/` và `procheck/static/` | Giao diện Jinja, CSS và JavaScript |
| `database/` và `tests/` | Tệp tạo cơ sở dữ liệu SQL Server và kiểm thử tự động |

Ứng dụng băm mật khẩu bằng scrypt, dùng phiên ký bởi Flask và yêu cầu token CSRF cho biểu mẫu POST. Truy vấn dùng biểu thức SQLAlchemy có tham số. Jinja tự escape dữ liệu trong các template HTML. Khi lưu, số phiên bản báo cáo giúp phát hiện form cũ hoặc hai lượt sửa đồng thời. Thay đổi trên báo cáo, sự kiện lịch sử và phiếu kiểm thử được ghi trong cùng giao dịch. Giới hạn thử đăng nhập áp dụng theo địa chỉ IP trong từng tiến trình Flask.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bộ kiểm thử dùng SQLite tạm để kiểm tra đăng nhập, CSRF, giới hạn số lần thử, tạo/sửa, lọc và phân trang, luồng kiểm thử lại, tổng quan, form cũ và nâng cấp dữ liệu từ bản đầu tiên. Sau khi kết nối SQL Server Express trên máy Windows, có thể xác nhận bằng cách đăng nhập, tạo một báo cáo tiếng Việt, chuyển qua đủ bốn trạng thái rồi truy vấn `SELECT * FROM dbo.issue_verifications;` trong SSMS.

Khi demo, bắt đầu từ lỗi nghiêm trọng, chuyển sang chờ kiểm thử, ghi một lượt **Chưa đạt** ở `v1.0`, sau đó gửi lại và ghi **Đạt** ở `v1.1`. Mở lịch sử để so sánh hai lượt, rồi mở trang tổng quan để xem hai phiếu và tỷ lệ đạt thay đổi.
