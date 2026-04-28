import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

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

# 1. SETUP & CONNECTION
st.set_page_config(page_title="Client Reporting Portal", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. GET USER IDENTITY (From URL)
params = st.query_params
user_token = params.get("token", None)

if not user_token:
    st.error("⛔ Access Denied. No token provided.")
    st.stop()

# --- THE ROUTER ---
# 3. READ DIRECTORY TO FIND THE USER'S COUNTY
df_directory = conn.read(worksheet="Directory", ttl=0)
df_directory['Token'] = df_directory['Token'].astype(str)

user_info = df_directory[df_directory['Token'] == user_token]
if user_info.empty:
    st.error("⛔ Invalid Token. Please check your link or the Directory tab.")
    st.stop()

current_client_name = user_info['Client'].iloc[0]
user_county = user_info['County'].iloc[0] 

# 4. LOAD THE DATA SAFELY
df_raw = conn.read(worksheet=f"{user_county}_Data", ttl=0, keep_default_na=False, header=None)

headers = df_raw.iloc[3] 

df_data = df_raw.iloc[4:].copy() 
df_data.columns = headers
df_data = df_data.reset_index(drop=True)
df_data['Token'] = df_data['Token'].astype(str)

df_config = conn.read(worksheet=f"{user_county}_Config", ttl=0)

# 5. FIND THE USER'S ROW 
user_row_index = df_data[df_data['Token'] == str(user_token)].index
if user_row_index.empty:
    st.error(f"⛔ Token found in Directory, but missing from {user_county}_Data sheet!")
    st.stop()

user_row_index = user_row_index[0] 


# --- GLOBAL PROGRESS & DYNAMIC SIDEBAR LABELS ---
tab_display_dict = {}
all_actionable_questions = df_config[~df_config['Type'].isin(['subheader', 'readonly'])]
total_overall_questions = len(all_actionable_questions)
filled_overall_questions = 0

tabs = df_config['Tab'].unique()

for t in tabs:
    t_questions = all_actionable_questions[all_actionable_questions['Tab'] == t]
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
        tab_display_dict[t] = f"✅ {t}"  
    else:
        tab_display_dict[t] = t         

overall_percent = int((filled_overall_questions / total_overall_questions) * 100) if total_overall_questions > 0 else 100


# 6. SIDEBAR NAVIGATION
if user_county == "OC":
    sidebar_icon = "🍊"
else:
    sidebar_icon = "🏙️"

st.sidebar.title(f"{sidebar_icon} {current_client_name}")

st.sidebar.markdown("**🏆 Overall Progress:**")
st.sidebar.progress(overall_percent, text=f"{filled_overall_questions} of {total_overall_questions} total answered")
st.sidebar.markdown("---")

selected_tab = st.sidebar.radio("Navigate", tabs, format_func=lambda x: tab_display_dict[x])

# --- SECTION PROGRESS TRACKER LOGIC ---
tab_questions = df_config[df_config['Tab'] == selected_tab]

actionable_questions = tab_questions[~tab_questions['Type'].isin(['subheader', 'readonly'])]
total_questions = len(actionable_questions)
filled_questions = 0

for index, row in actionable_questions.iterrows():
    col_name = row['Column Name']
    if col_name in df_data.columns:
        val = format_cell_value(df_data.at[user_row_index, col_name])
        if val != "":
            filled_questions += 1

progress_percent = int((filled_questions / total_questions) * 100) if total_questions > 0 else 100

st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 Currently Editing:")
st.sidebar.info(f"**{selected_tab}**")

st.sidebar.markdown("**📊 Section Progress:**")
st.sidebar.progress(progress_percent, text=f"{filled_questions} of {total_questions} answered")


# 7. DYNAMIC FORM GENERATOR

st.markdown(f"<h1 style='margin-top: 0px; padding-top: 0px;'>{selected_tab}</h1>", unsafe_allow_html=True)
    
if 'Tab Description' in df_config.columns:
    descriptions = tab_questions['Tab Description'].dropna().unique()
    if len(descriptions) > 0 and str(descriptions[0]).strip() != "":
        st.markdown(f"<p style='color: var(--text-color); opacity: 0.8; margin-top: -15px; margin-bottom: 20px;'>{str(descriptions[0])}</p>", unsafe_allow_html=True)

# --- UPDATED: CSS FOR NOTICEABLE COLOR CHANGES ---
st.markdown("""
    <style>
        /* The glowing outline when a user clicks into a box */
        div[data-baseweb="input"]:focus-within, 
        div[data-baseweb="textarea"]:focus-within,
        div[data-baseweb="select"]:focus-within {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 8px rgba(28, 131, 225, 0.3) !important; /* Soft blue glow */
            transition: all 0.2s ease-in-out;
        }
        
        /* If the box is empty (showing the placeholder space), make it pure white */
        div[data-baseweb="input"] input:placeholder-shown,
        div[data-baseweb="textarea"] textarea:placeholder-shown {
            background-color: #ffffff !important;
        }

        /* If the box has text typed in it (placeholder hidden), turn it a noticeable gray */
        div[data-baseweb="input"] input:not(:placeholder-shown),
        div[data-baseweb="textarea"] textarea:not(:placeholder-shown) {
            background-color: #e2e6ea !important;
        }
    </style>
""", unsafe_allow_html=True)

with st.form(key='dynamic_form'):

    # --- TOP SAVE BUTTON (Now 'primary' so it uses your blue theme color!) ---
    submitted_top = st.form_submit_button("💾 Save Progress", key="save_top", use_container_width=True, type="primary")

    user_responses = {}
    is_first_item = True  

    for index, row in tab_questions.iterrows():
        col_name = row['Column Name']
        label = row['Label']
        input_type = row['Type']
        
        is_financial = "Expenditure" in selected_tab or "Budget" in selected_tab or "💲" in selected_tab
        
        # --- SUBHEADER LOGIC ---
        if input_type == 'subheader':
            if not is_first_item:
                st.markdown("<hr style='margin-top: 25px; margin-bottom: 15px;'>", unsafe_allow_html=True) 
            
            st.markdown(f"<h3 style='margin-top: 0px; margin-bottom: 10px;'>{label}</h3>", unsafe_allow_html=True)
            is_first_item = False
            continue 
            
        # SAFETY CHECK
        if col_name in df_data.columns:
            raw_current_val = df_data.at[user_row_index, col_name]
        else:
            raw_current_val = ""
            
        clean_current_val = format_cell_value(raw_current_val)

        # --- 1. DISPLAY THE QUESTION LABEL FIRST ---
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

        # --- 2. CONTEXTUAL DATA (LAST YEAR & JLHA) ---
        # UPDATED: Changed #a3a8b8 to #666666 for proper contrast in Light Mode
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
                        st.markdown(f"<div style='color: #666666; font-size: 0.85em; margin-top: -10px; margin-bottom: 5px;'>💰 <b>Last Year's Total:</b>{separator}{display_prev}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='color: #666666; font-size: 0.85em; margin-top: -10px; margin-bottom: 5px;'>🗓️ <b>Last year's response:</b>{separator}{display_prev_text}</div>", unsafe_allow_html=True)

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
                        st.markdown(f"<div style='color: #666666; font-size: 0.85em; margin-top: -5px; margin-bottom: 5px;'>🐟 <b>JLHA Expenses:</b>{separator}{display_jlha}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='color: #666666; font-size: 0.85em; margin-top: -5px; margin-bottom: 5px;'>🐟 <b>JLHA Expenses:</b>{separator}{display_jlha_text}</div>", unsafe_allow_html=True)

        # --- 3. RENDER THE WIDGET ---
        if input_type == 'text':
             user_responses[col_name] = st.text_input(label="hidden_label", label_visibility="collapsed", value=clean_current_val, placeholder=" ", key=col_name)
        
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label="hidden_label", label_visibility="collapsed", value=clean_current_val, placeholder=" ", key=col_name)
             
        elif input_type == 'readonly':
             display_text = clean_current_val
             
             if display_text == "" and 'Previous_Col' in row and pd.notna(row['Previous_Col']):
                 prev_col_name = str(row['Previous_Col']).strip()
                 if prev_col_name in df_data.columns:
                     display_text = format_cell_value(df_data.at[user_row_index, prev_col_name])
             
             display_text = re.sub(r'(?i)(\d+\s*BMPs completed:)', r'<u>**\1**</u>', display_text)
             display_text = re.sub(r'(?i)(BMPs in progress:)', r'<u>**\1**</u>', display_text)
             display_text = display_text.replace('\n', '  \n')
             
             if display_text != "":
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
        
        is_first_item = False 
        st.write("")
    
    # --- BOTTOM SAVE BUTTON (Also updated to primary blue!) ---
    st.write("")
    submitted_bottom = st.form_submit_button("💾 Save Progress", key="save_bottom", use_container_width=True, type="primary")
    
    # 8. SUBMISSION LOGIC
    if submitted_top or submitted_bottom:
        headers_list = list(headers)
        
        for col, new_val in user_responses.items():
            df_data.at[user_row_index, col] = new_val
            
            if col in headers_list:
                col_idx = headers_list.index(col)
                df_raw.iat[user_row_index + 4, col_idx] = new_val
        
        df_raw.columns = df_raw.iloc[0]
        df_to_save = df_raw.iloc[1:].copy()
        
        conn.update(worksheet=f"{user_county}_Data", data=df_to_save)
        st.success(f"✅ Saved data for {selected_tab}!")
        st.rerun()
