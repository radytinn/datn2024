import streamlit as st
from streamlit_option_menu import option_menu
import easyocr
from PIL import Image
import pandas as pd
import numpy as np
import hashlib
import mysql.connector
import re
import cv2  # Import OpenCV for image processing
import spacy  # Import spaCy for NLP


# Tải mô hình spaCy cho tiếng Anh
nlp = spacy.load("en_core_web_sm")

# Kết nối cơ sở dữ liệu
try:
    mydb = mysql.connector.connect(
        user='root',
        host='localhost',
        password='12345',
        auth_plugin='mysql_native_password'
    )
    mycursor = mydb.cursor()
    mycursor.execute('CREATE DATABASE IF NOT EXISTS vnexcard_db')
    mycursor.execute('USE vnexcard_db')

    # Tạo bảng USERS
    mycursor.execute("""
        CREATE TABLE IF NOT EXISTS USERS (
            ID INT AUTO_INCREMENT PRIMARY KEY,
            USERNAME VARCHAR(50) UNIQUE,
            EMAIL VARCHAR(100),
            PASSWORD_HASH VARCHAR(255)
        )
    """)
    # Tạo bảng BUSINESS_CARD
    mycursor.execute("""
        CREATE TABLE IF NOT EXISTS BUSINESS_CARD (
            ID INT AUTO_INCREMENT PRIMARY KEY,
            USER_ID INT,
            NAME VARCHAR(50),
            DESIGNATION VARCHAR(100),
            COMPANY_NAME VARCHAR(100),
            CONTACT VARCHAR(35),
            EMAIL VARCHAR(100),
            WEBSITE VARCHAR(100),
            ADDRESS TEXT,
            PINCODE VARCHAR(10),
            FOREIGN KEY (USER_ID) REFERENCES USERS(ID)
        )
    """)
    mydb.commit()
except mysql.connector.Error as e:
    st.error(f"Kết nối cơ sở dữ liệu thất bại: {e}")

# Hàm mã hóa mật khẩu
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Hàm xác minh thông tin người dùng
def verify_user(username, password):
    hashed_password = hash_password(password)
    mycursor.execute("SELECT * FROM USERS WHERE USERNAME = %s AND PASSWORD_HASH = %s", (username, hashed_password))
    return mycursor.fetchone()

# Hàm đăng ký người dùng
def register_user(username, email, password):
    try:
        hashed_password = hash_password(password)
        mycursor.execute("INSERT INTO USERS (USERNAME, EMAIL, PASSWORD_HASH) VALUES (%s, %s, %s)",
                         (username, email, hashed_password))
        mydb.commit()
        return True
    except mysql.connector.Error as e:
        st.error(f"Lỗi khi đăng ký: {e}")
        return False

# Hàm tiền xử lý hình ảnh
def preprocess_image(image):
    # Chuyển đổi ảnh sang dạng xám
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Cải thiện độ tương phản (bằng cách áp dụng histogram equalization)
    equalized = cv2.equalizeHist(gray)
    # Lọc ảnh để giảm nhiễu (sử dụng Gaussian blur)
    blurred = cv2.GaussianBlur(equalized, (5, 5), 0)
    return blurred

# Hàm xử lý kết quả OCR
def extracted_text(result):
    ext_dic = {
        'Name': [],
        'Designation': [],
        'Company name': [],
        'Contact': [],
        'Email': [],
        'Website': [],
        'Address': []
    }

    # Lấy tên và chức danh từ kết quả OCR
    ext_dic['Name'].append(result[0])
    ext_dic['Designation'].append(result[1])

    for m in range(2, len(result)):
        # Nếu là số điện thoại
        if result[m].startswith('+') or (result[m].replace('-', '').isdigit() and '-' in result[m]):
            ext_dic['Contact'].append(result[m])

        # Nếu là email
        elif '@' in result[m] and '.com' in result[m]:
            ext_dic['Email'].append(result[m].lower())

        # Nếu là website
        elif 'www' in result[m].lower():
            ext_dic['Website'].append(result[m].lower())

        # Nếu là tên công ty
        elif re.match(r'^[A-Za-z]', result[m]):
            if not any(char.isdigit() for char in result[m]) and len(result[m].split()) <= 3:
                ext_dic['Company name'].append(result[m])
            else:
                ext_dic['Address'].append(result[m])

        # Nếu là địa chỉ
        else:
            ext_dic['Address'].append(re.sub(r'[,;]', '', result[m]))

    # Xử lý dữ liệu để ghép các giá trị lại thành chuỗi
    for key, value in ext_dic.items():
        if len(value) > 0:
            ext_dic[key] = [' '.join(value)]  # Ghép các giá trị thành chuỗi
        else:
            ext_dic[key] = ['NA']  # Gán 'NA' nếu không có dữ liệu

    return ext_dic

# Hàm sử dụng spaCy để phân tích văn bản và trích xuất thông tin
def extract_entities_from_text(text):
    doc = nlp(text)
    entities = {'PERSON': [], 'ORG': [], 'GPE': [], 'PHONE': [], 'EMAIL': []}

    # Duyệt qua các thực thể nhận diện được từ spaCy
    for ent in doc.ents:
        if ent.label_ == 'PERSON':
            entities['PERSON'].append(ent.text)
        elif ent.label_ == 'ORG':
            entities['ORG'].append(ent.text)
        elif ent.label_ == 'GPE':  # Địa điểm (geopolitical entity)
            entities['GPE'].append(ent.text)
        elif ent.label_ == 'PHONE':  # Số điện thoại (nếu được nhận diện)
            entities['PHONE'].append(ent.text)
        elif ent.label_ == 'EMAIL':  # Email
            entities['EMAIL'].append(ent.text)
    
    # Trả về các thực thể nhận diện được
    return entities


@st.cache_resource
def load_image_reader():
    return easyocr.Reader(['en','vi'], model_storage_directory=".")

reader = load_image_reader()

# Quản lý trạng thái đăng nhập
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>VNEXCARD - Đăng nhập/Đăng ký</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Đăng nhập", "Đăng ký"])

    # Tab Đăng nhập
    with tab1:
        st.markdown("### Đăng nhập")
        login_username = st.text_input("Tên người dùng")
        login_password = st.text_input("Mật khẩu", type="password")
        if st.button("Đăng nhập"):
            user = verify_user(login_username, login_password)
            if user:
                st.session_state.logged_in = True
                st.session_state.current_user = login_username
                st.success(f"Chào mừng {login_username}!")
                st.stop()
            else:
                st.error("Tên người dùng hoặc mật khẩu không chính xác!")

    # Tab Đăng ký
    with tab2:
        st.markdown("### Đăng ký")
        register_username = st.text_input("Tên người dùng", key="register_username")
        register_email = st.text_input("Email", key="register_email")
        register_password = st.text_input("Mật khẩu", type="password", key="register_password")
        confirm_password = st.text_input("Xác nhận mật khẩu", type="password", key="register_confirm_password")
        if st.button("Đăng ký"):
            if register_password != confirm_password:
                st.error("Mật khẩu không khớp!")
            else:
                if register_user(register_username, register_email, register_password):
                    st.success("Đăng ký thành công! Bạn có thể đăng nhập ngay bây giờ.")

if st.session_state.logged_in:
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/de/HCMUT_official_logo.png/594px-HCMUT_official_logo.png", width=150)
        st.sidebar.success(f"Đăng nhập dưới tên: {st.session_state.current_user}")
        if st.sidebar.button("Đăng xuất"):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.stop()

    selected = option_menu(
        menu_title="Chức năng",
        options=["Trang chủ", "Tải lên ảnh", "Liên hệ"],
        icons=["house", "cloud-upload", "envelope"],
        default_index=0
    )

    if selected == "Trang chủ":
        st.markdown("<h1 style='text-align: center;'>Chào mừng đến với VNEXCARD</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>VNEXCARD là công cụ nhận dạng danh thiếp thông minh, giúp bạn tự động hóa và quản lý thông tin liên lạc một cách hiệu quả.</p>", unsafe_allow_html=True)

    if selected == "Tải lên ảnh":
        st.markdown("### Tải lên hình ảnh danh thiếp")
        images = st.file_uploader("Chọn ảnh", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
        if images:
            all_dfs = []
            for idx, image in enumerate(images):
                input_image = Image.open(image)
                st.image(input_image, caption=f"Hình ảnh {idx+1}: {image.name}", width=350)
                # Chuyển ảnh thành mảng NumPy và tiền xử lý
                np_image = np.array(input_image)
                preprocessed_image = preprocess_image(np_image)

                # Nhận diện văn bản từ ảnh đã tiền xử lý
                result = reader.readtext(np.array(input_image), detail=0)
                ext_text = extracted_text(result)
                df = pd.DataFrame(ext_text)
                all_dfs.append(df)
                st.dataframe(df)

                st.markdown("### Chỉnh sửa dữ liệu:")
                edited_data = {}

                # Cho phép người dùng chỉnh sửa dữ liệu
                for idx, column in enumerate(df.columns):
                    key_value = f"{column}_{idx}_{df[column].iloc[0]}_{idx}"  # Tạo key duy nhất cho mỗi trường
                    edited_data[column] = st.text_input(f"Chỉnh sửa {column}", value=df[column].iloc[0], key=key_value)

                st.write("### Dữ liệu đã chỉnh sửa:")
                st.write(edited_data)
                

               # Cập nhật dữ liệu khi người dùng nhấn nút "Lưu thay đổi"
                if st.button(f"Lưu thay đổi cho ảnh ", key=f"save_button_{idx}_{image.name}"):
                    updated_df = pd.DataFrame(edited_data, index=[0])  # Chuyển thành DataFrame mới

                    # Kiểm tra chỉ mục và cấu trúc DataFrame trước khi cập nhật
                    if idx < len(all_dfs):
                        st.write(f"Cập nhật chỉ mục {idx} trong all_dfs...")
                        if all_dfs[idx].shape[1] == updated_df.shape[1]:  # Kiểm tra cấu trúc có khớp không
                            all_dfs[idx] = updated_df  # Cập nhật DataFrame tại idx
                        else:
                            st.write("Cảnh báo: Cấu trúc DataFrame không khớp, đang thêm DataFrame mới.")
                            all_dfs.append(updated_df)  # Thêm DataFrame mới nếu cấu trúc không khớp
                    else:
                        st.write(f"Đã cập nhập dữ liệu mới.")
                        all_dfs.append(updated_df)  # Thêm DataFrame mới nếu idx không hợp lệ

            # Tạo tệp CSV từ các DataFrame đã cập nhật
            final_df = pd.concat(all_dfs, ignore_index=True)
            csv_data = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Tải xuống kết quả (CSV)",
                data=csv_data,
                file_name="result_ocr_updated.csv",
                mime="text/csv"
            )

    if selected == "Liên hệ":
        st.markdown("<h2 style='text-align: center;'>Liên hệ với chúng tôi</h2>", unsafe_allow_html=True)
        st.write("- **Email:** anh.huynh@hcmut.edu.vn")
        st.write("- **GitHub:** [Visit GitHub](http://dte.dee.hcmut.edu.vn/)")
        st.write("- **LinkedIn:** [Visit LinkedIn](http://www.linkedin.com/)")

        st.markdown(
            """
            <div style="text-align: center;">
<img src="https://hcmut.edu.vn/img/nhanDienThuongHieu/bk_name_vi.png" alt="Logo" width="500" height="auto">                
            </div>
            """, unsafe_allow_html=True)