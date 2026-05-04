import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- CONSTANTS ---
FOLDER_ID = '0AHdnucXOxMoCUk9PVA'
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file'] 

# --- HELPER FUNCTIONS FOR FORMATTING ---
def format_cell_value(val):
    if pd.isna(val):
        return ""
    
    str_val = str(val).strip()
    
    if str_val.lower() == 'nan':
        return ""
        
    try:
        float_val = float(str_val)
        if float_val.is_integer():
            return str(int(float_val))
        else:
            return str(float_val)
    except ValueError:
        return str_val

def format_currency(val_str):
    if "$" in val_str:
        return val_str 
    try:
        clean_num = val_str.replace(",", "")
        f_val = float(clean_num)
        if f_val.is_integer():
            return f"${int(f_val):,}"
        else:
            return f"${f_val:,.2f}"
    except ValueError:
        return val_str 

# --- GOOGLE DRIVE FUNCTIONS ---
@st.cache_resource
def authenticate_drive():
    creds_info = st.secrets["connections"]["gsheets"] 
    
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=DRIVE_SCOPES
    )
    service = build('drive', 'v3', credentials=creds)
    return service

def upload_to_drive(file, service):
    file_metadata = {
        'name': file.name,
        'parents': [FOLDER_ID]
    }
    media = MediaIoBaseUpload(
        file, 
        mimetype=file.type, 
        resumable=True
    )
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return uploaded_file.get('id')

# 1. SETUP & CONNECTION
st.set_page_config(page_title="Client Reporting Portal", layout="wide")

# --- CELEBRATION TRIGGER ---
if st.session_state.get('show_celebration', False):
    st.balloons()  
    st.session_state['show_celebration'] = False

conn = st.connection("gsheets", type=GSheetsConnection)

# 2. GET USER IDENTITY (From URL)
params = st.query_params
user_token = params.get("token", None)

if not user_token:
    st.error("⛔ Access Denied. No token provided.")
    st.stop()

# --- THE ROUTER ---
# 3. READ DIRECTORY TO FIND THE USER'S COUNTY
try:
    df_directory = conn.read(worksheet="Directory", ttl="10m")
    df_directory['Token'] = df_directory['Token'].astype(str)
except Exception as e:
    st.error("⛔ Google API Error: Could not read the 'Directory' tab. Please check your sheet names or wait a moment if rate-limited.")
    st.stop()

user_info = df_directory[df_directory['Token'] == user_token]
if user_info.empty:
    st.error("⛔ Invalid Token. Please check your link or the Directory tab.")
    st.stop()

current_client_name = user_info['Client'].iloc[0]
user_county = user_info['County'].iloc[0] 

# 4. LOAD THE DATA SAFELY
try:
    df_raw = conn.read(worksheet=f"{user_county}_Data", ttl="10m", keep_default_na=False, header=None)
except Exception as e:
    st.error(f"⛔ Google API Error: Could not find the tab named '{user_county}_Data' or the app is rate-limited.")
    st.stop()

headers = df_raw.iloc[3] 

df_data = df_raw.iloc[4:].copy() 
df_data.columns = headers
df_data = df_data.reset_index(drop=True)
df_data['Token'] = df_data['Token'].astype(str)

try:
    df_config = conn.read(worksheet=f"{user_county}_Config", ttl="10m")
except Exception as e:
    st.error(f"⛔ Google API Error: Could not find the tab named '{user_county}_Config' or the app is rate-limited.")
    st.stop()

# 5. FIND THE USER'S ROW 
user_row_index = df_data[df_data['Token'] == str(user_token)].index
if user_row_index.empty:
    st.error(f"⛔ Token found in Directory, but missing from {user_county}_Data sheet!")
    st.stop()

user_row_index = user_row_index[0] 


# --- GLOBAL PROGRESS & DYNAMIC SIDEBAR LABELS ---
tab_display_dict = {}

# Progress counter ignores file_uploads
all_progress_questions = df_config[~df_config['Type'].isin(['subheader', 'readonly', 'file_upload'])]
total_overall_questions = len(all_progress_questions)
filled_overall_questions = 0

tabs = df_config['Tab'].unique()

for t in tabs:
    t_questions = all_progress_questions[all_progress_questions['Tab'] == t]
    t_total = len(t_questions)
    t_filled = 0
    
    for idx, row in t_questions.iterrows():
        col_name = row['Column Name']
        if col_name in df_data.columns:
            val = format_cell_value(df_data.at[user_row_index, col_name])
            if val != "":
                t_filled += 1
                filled_overall_questions += 1
    
    if t_total > 0 and t_filled == t_total:
        tab_display_dict[t] = f"✅ ~~{t}~~"  
    else:
        tab_display_dict[t] = t         

overall_percent = int((filled_overall_questions / total_overall_questions) * 100) if total_overall_questions > 0 else 100


# 6. SIDEBAR NAVIGATION
if user_county == "OC":
    sidebar_icon = "🍊"
else:
    sidebar_icon = "🏙️"

st.sidebar.title(f"{sidebar_icon} {current_client_name}")

top_sidebar_placeholder = st.sidebar.container()

selected_tab = st.sidebar.radio("Navigate", tabs, format_func=lambda x: tab_display_dict[x])

st.sidebar.markdown("---")

overall_progress_html = f"""
<div style="background-color: #eef6fc; border: 1px solid #cde0f5; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
    <div style="font-weight: bold; color: #1C83E1; margin-bottom: 5px;">🏆 Overall Progress:</div>
    <div style="font-size: 13px; color: #444444; margin-bottom: 10px; display: flex; justify-content: space-between;">
        <span>{filled_overall_questions} of {total_overall_questions} answered</span>
        <span style="font-weight: bold; color: #1C83E1;">{overall_percent}%</span>
    </div>
    <div style="background-color: #d0d7e2; border-radius: 10px; width: 100%; height: 10px;">
        <div style="background-color: #1C83E1; border-radius: 10px; height: 100%; width: {overall_percent}%;"></div>
    </div>
</div>
"""
st.sidebar.markdown(overall_progress_html, unsafe_allow_html=True)


# --- SECTION PROGRESS TRACKER LOGIC ---
tab_questions = df_config[df_config['Tab'] == selected_tab]

# Section progress also ignores file_uploads
section_progress_questions = tab_questions[~tab_questions['Type'].isin(['subheader', 'readonly', 'file_upload'])]
total_questions = len(section_progress_questions)
filled_questions = 0

for index, row in section_progress_questions.iterrows():
    col_name = row['Column Name']
    if col_name in df_data.columns:
        val = format_cell_value(df_data.at[user_row_index, col_name])
        if val != "":
            filled_questions += 1

progress_percent = int((filled_questions / total_questions) * 100) if total_questions > 0 else 100

top_sidebar_placeholder.markdown("### 📍 Currently Editing:")
top_sidebar_placeholder.info(f"**{selected_tab}**")

section_progress_html = f"""
<div style="background-color: #eef6fc; border: 1px solid #cde0f5; border-radius: 8px; padding: 15px; margin-bottom: 10px;">
    <div style="font-weight: bold; color: #1C83E1; margin-bottom: 5px;">📊 Section Progress:</div>
    <div style="font-size: 13px; color: #444444; margin-bottom: 10px; display: flex; justify-content: space-between;">
        <span>{filled_questions} of {total_questions} answered</span>
        <span style="font-weight: bold; color: #1C83E1;">{progress_percent}%</span>
    </div>
    <div style="background-color: #d0d7e2; border-radius: 10px; width: 100%; height: 10px;">
        <div style="background-color: #1C83E1; border-radius: 10px; height: 100%; width: {progress_percent}%;"></div>
    </div>
</div>
"""
top_sidebar_placeholder.markdown(section_progress_html, unsafe_allow_html=True)


# 7. DYNAMIC FORM GENERATOR
st.markdown(f"<h1 style='margin-top: 0px; padding-top: 0px;'>{selected_tab}</h1>", unsafe_allow_html=True)
    
if 'Tab Description' in df_config.columns:
    descriptions = tab_questions['Tab Description'].dropna().unique()
    if len(descriptions) > 0 and str(descriptions[0]).strip() != "":
        st.markdown(f"<p style='color: #444444; margin-top: -15px; margin-bottom: 20px;'>{str(descriptions[0])}</p>", unsafe_allow_html=True)

# --- CSS FOR CARD LAYOUT & BUTTONS ---
st.markdown("""
    <style>
        .stApp { background-color: #f0f2f6 !important; }
        [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #e0e6ed !important; }
        [data-testid="stHeader"] { background-color: #ffffff !important; }
        
        [data-testid="stForm"] {
            background-color: #ffffff !important; 
            border-radius: 12px !important;
            border: 1px solid #e0e6ed !important; 
            box-shadow: 0px 8px 24px rgba(0, 0, 0, 0.04) !important;
            padding: 30px !important;
        }

        div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] {
            border: 1px solid #e0e6ed !important; border-radius: 6px !important; transition: all 0.2s ease-in-out;
        }
        div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within, div[data-baseweb="select"]:focus-within {
            border-color: #1C83E1 !important; box-shadow: 0 0 8px rgba(28, 131, 225, 0.3) !important;
        }
        div[data-baseweb="input"] input:placeholder-shown, div[data-baseweb="textarea"] textarea:placeholder-shown {
            background-color: #ffffff !important;
        }
        div[data-baseweb="input"] input:not(:placeholder-shown), div[data-baseweb="textarea"] textarea:not(:placeholder-shown) {
            background-color: #f0f2f6 !important;
        }
        
        /* Main Save Buttons (Top/Bottom) */
        [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
            background-color: #1C83E1 !important; color: #ffffff !important; border: none !important;
        }
        [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"]:hover {
            background-color: #1565C0 !important; color: #ffffff !important;
        }
        
        /* Quick Save Buttons (Small & Tightly Spaced) */
        [data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"] {
            background-color: #1C83E1 !important; 
            color: #ffffff !important; 
            border: none !important;
            padding: 2px 14px !important;
            min-height: 28px !important;
            width: auto !important;
            margin-top: -10px !important;
            margin-bottom: -5px !important;
        }
        [data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"] p {
            font-size: 0.85em !important;
        }
        [data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"]:hover {
            background-color: #1565C0 !important; 
            color: #ffffff !important;
        }
        
        /* UPDATED: Shrink the Native File Uploader Drop-Zone AND Button */
        [data-testid="stFileUploadDropzone"] {
            padding: 10px 15px !important; 
            min-height: auto !important;
        }
        [data-testid="stFileUploader"] button {
            padding: 2px 14px !important;
            min-height: 28px !important;
            font-size: 0.85em !important;
        }
        [data-testid="stFileUploader"] small {
            font-size: 0.8em !important;
        }
    </style>
""", unsafe_allow_html=True)

with st.form(key='dynamic_form'):

    submitted_top = st.form_submit_button("💾 Save Progress", key="save_top", type="primary", use_container_width=True)
    
    st.write("") 
    
    user_responses = {}
    quick_saves = [] 
    is_first_item = True  

    for i, (index, row) in enumerate(tab_questions.iterrows()):
        col_name = row['Column Name']
        label = row['Label']
        input_type = row['Type']
        is_financial = "Expenditure" in selected_tab or "Budget" in selected_tab or "💲" in selected_tab
        
        if input_type == 'subheader':
            if not is_first_item:
                st.markdown("<hr style='margin-top: 25px; margin-bottom: 15px; border-color: #e0e6ed;'>", unsafe_allow_html=True) 
            st.markdown(f"<h3 style='margin-top: 0px; margin-bottom: 10px;'>{label}</h3>", unsafe_allow_html=True)
            is_first_item = False
            continue 
            
        if col_name in df_data.columns:
            raw_current_val = df_data.at[user_row_index, col_name]
        else:
            raw_current_val = ""
            
        clean_current_val = format_cell_value(raw_current_val)

        display_label = str(label).replace("**", "").strip()
        
        if "•" in display_label:
            parts = display_label.split("•")
            formatted_label = f"**{parts[0].strip()}**\n" 
            for part in parts[1:]:
                if part.strip(): 
                    formatted_label += f"* **{part.strip()}**\n" 
            st.markdown(formatted_label)
        else:
            formatted_parts = []
            for line in display_label.split('\n'):
                if line.strip(): 
                    formatted_parts.append(f"**{line.strip()}**")
            st.markdown("  \n\n".join(formatted_parts))

        if 'Previous_Col' in row and pd.notna(row['Previous_Col']):
            prev_col_name = str(row['Previous_Col']).strip()
            if prev_col_name in df_data.columns:
                raw_prev_val = df_data.at[user_row_index, prev_col_name]
                clean_prev_val = format_cell_value(raw_prev_val)
                if clean_prev_val != "" and input_type != 'readonly':
                    has_line_breaks = '\n' in clean_prev_val
                    separator = "<br>" if has_line_breaks else " "
                    display_prev_text = clean_prev_val.replace('\n', '<br>')
                    if is_financial:
                        display_prev = format_currency(clean_prev_val)
                        st.markdown(f"<div style='color: #444444; font-size: 0.85em; margin-top: -10px; margin-bottom: 5px;'>💰 <b>Last Year's Total:</b>{separator}{display_prev}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='color: #444444; font-size: 0.85em; margin-top: -10px; margin-bottom: 5px;'>🗓️ <b>Last year's response:</b>{separator}{display_prev_text}</div>", unsafe_allow_html=True)

        if 'JLHA_Col' in df_config.columns and 'JLHA_Col' in row and pd.notna(row['JLHA_Col']):
            jlha_col_name = str(row['JLHA_Col']).strip()
            if jlha_col_name in df_data.columns:
                raw_jlha_val = df_data.at[user_row_index, jlha_col_name]
                clean_jlha_val = format_cell_value(raw_jlha_val)
                if clean_jlha_val != "" and input_type != 'readonly':
                    has_line_breaks = '\n' in clean_jlha_val
                    separator = "<br>" if has_line_breaks else " "
                    display_jlha_text = clean_jlha_val.replace('\n', '<br>')
                    if is_financial:
                        display_jlha = format_currency(clean_jlha_val)
                        st.markdown(f"<div style='color: #444444; font-size: 0.85em; margin-top: -5px; margin-bottom: 5px;'>🐟 <b>JLHA Expenses:</b>{separator}{display_jlha}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='color: #444444; font-size: 0.85em; margin-top: -5px; margin-bottom: 5px;'>🐟 <b>JLHA Expenses:</b>{separator}{display_jlha_text}</div>", unsafe_allow_html=True)

        if input_type == 'text':
             user_responses[col_name] = st.text_input(label="hidden_label", label_visibility="collapsed", value=clean_current_val, placeholder=" ", key=col_name)
             
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label="hidden_label", label_visibility="collapsed", value=clean_current_val, placeholder=" ", key=col_name)
             
        elif input_type == 'file_upload':
             if clean_current_val != "":
                 st.markdown(f"<div style='font-size: 0.85em; margin-bottom: 10px; padding: 10px; background-color: #f0f2f6; border-radius: 6px;'>📎 <b>Current File:</b> <a href='{clean_current_val}' target='_blank'>View Uploaded Document</a><br><span style='color: #666; font-size: 0.9em;'>Upload a new file below to overwrite the current one.</span></div>", unsafe_allow_html=True)
             user_responses[col_name] = st.file_uploader(label="hidden_label", label_visibility="collapsed", key=col_name)
             
        elif input_type == 'readonly':
             display_text = clean_current_val
             if display_text == "" and 'Previous_Col' in row and pd.notna(row['Previous_Col']):
                 prev_col_name = str(row['Previous_Col']).strip()
                 if prev_col_name in df_data.columns:
                     display_text = format_cell_value(df_data.at[user_row_index, prev_col_name])
             
             if display_text == "":
                 display_text = "*None*"
                 
             display_text = re.sub(r'(?i)(\d+\s*BMPs completed:)', r'<u>**\1**</u>', display_text)
             display_text = re.sub(r'(?i)(BMPs in progress:)', r'<u>**\1**</u>', display_text)
             display_text = display_text.replace('\n', '  \n')
             
             st.markdown(display_text, unsafe_allow_html=True)
                 
        elif input_type == 'dropdown':
            options_str = str(row['Options']) if pd.notna(row['Options']) else ""
            options = [opt.strip() for opt in options_str.split(',')]
            try:
                current_index = options.index(clean_current_val)
            except ValueError:
                current_index = 0
            user_responses[col_name] = st.selectbox(label="hidden_label", label_visibility="collapsed", options=options, index=current_index, key=col_name)
            
        elif input_type == 'number':
            try:
                if clean_current_val == "":
                    num_val = None
                else:
                    num_val = float(clean_current_val)
                    if num_val.is_integer():
                        num_val = int(num_val)
            except ValueError:
                num_val = None
            user_responses[col_name] = st.number_input(label="hidden_label", label_visibility="collapsed", value=num_val, placeholder=" ", key=col_name)
            
        elif input_type == 'checkbox':
            is_checked = True if str(clean_current_val).lower() == 'true' else False
            user_responses[col_name] = st.checkbox(label="Check if Yes", value=is_checked, key=col_name)
            
        elif input_type == 'date':
             user_responses[col_name] = st.text_input(label="hidden_label", label_visibility="collapsed", value=clean_current_val, placeholder=" ", key=col_name)
        
        # --- PEEK-AHEAD LOGIC FOR THE QUICK SAVE BUTTON ---
        if input_type not in ['subheader', 'readonly']:
            hide_quick_save = False
            
            if i < len(tab_questions) - 1:
                next_type = tab_questions.iloc[i+1]['Type']
                if next_type == 'file_upload':
                    hide_quick_save = True
                    
            if not hide_quick_save:
                qs = st.form_submit_button("💾 Quick Save", key=f"qs_{col_name}", type="secondary")
                quick_saves.append(qs)
            
        is_first_item = False 
    
    submitted_bottom = st.form_submit_button("💾 Save Progress", key="save_bottom", type="primary", use_container_width=True)
    
    if submitted_top or submitted_bottom or any(quick_saves):
        headers_list = list(headers)
        final_responses = {}
        drive_service = None
        needs_drive = False
        
        questions_to_save = tab_questions[~tab_questions['Type'].isin(['subheader', 'readonly'])]
        
        for index, row in questions_to_save.iterrows():
            col = row['Column Name']
            if row['Type'] == 'file_upload' and user_responses.get(col) is not None:
                needs_drive = True
                break
                
        if needs_drive:
            try:
                with st.spinner("Authenticating secure connection to Google Drive..."):
                    drive_service = authenticate_drive()
            except Exception as e:
                st.error("⛔ Could not connect to Google Drive. Please contact support.")
                st.stop()
                
        for index, row in questions_to_save.iterrows():
            col = row['Column Name']
            q_type = row['Type']
            raw_val = user_responses.get(col)
            
            if q_type == 'file_upload':
                if raw_val is not None:
                    with st.spinner(f"Uploading file for '{row['Label']}'..."):
                        try:
                            file_id = upload_to_drive(raw_val, drive_service)
                            final_responses[col] = f"https://drive.google.com/file/d/{file_id}/view"
                        except Exception as e:
                            st.error(f"⛔ Failed to upload '{raw_val.name}'. Error: {str(e)}")
                            final_responses[col] = df_data.at[user_row_index, col] 
                else:
                    final_responses[col] = df_data.at[user_row_index, col]
            else:
                final_responses[col] = raw_val

        new_filled_questions = 0
        for col, val in final_responses.items():
            if col in section_progress_questions['Column Name'].values:
                if format_cell_value(val) != "":
                    new_filled_questions += 1
                
        if new_filled_questions == total_questions and filled_questions < total_questions and total_questions > 0:
            st.session_state['show_celebration'] = True
        
        for col, new_val in final_responses.items():
            df_data.at[user_row_index, col] = new_val
            if col in headers_list:
                col_idx = headers_list.index(col)
                df_raw.iat[user_row_index + 4, col_idx] = new_val
        
        new_cols = []
        seen = set()
        for c in df_raw.iloc[0]:
            c_str = str(c) if pd.notna(c) else ""
            if c_str.strip() == "" or c_str.lower() == "nan":
                c_str = ""
            while c_str in seen:
                c_str += " "
            seen.add(c_str)
            new_cols.append(c_str)
            
        df_raw.columns = new_cols
        df_to_save = df_raw.iloc[1:].copy()
        
        try:
            with st.spinner("Saving data to Google Sheets..."):
                conn.update(worksheet=f"{user_county}_Data", data=df_to_save)
                st.cache_data.clear()
            st.success(f"✅ Saved data for {selected_tab}!")
            st.rerun()
        except Exception as e:
            st.error("⛔ Google API Error: Could not save data. The app may be rate-limited. Please wait a minute and try again.")
