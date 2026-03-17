import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re  # NEW: We need this to smartly find and format text!

# --- HELPER FUNCTION FOR FORMATTING ---
def format_cell_value(val):
    """
    Cleans up the value from Google Sheets so:
    1. '99.0' becomes '99'
    2. '99.6' stays '99.6'
    3. 'None', 'N/A', '0' show up as text instead of disappearing
    """
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

# 1. SETUP & CONNECTION
st.set_page_config(page_title="Client Reporting Portal", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. GET USER IDENTITY (From URL)
params = st.query_params
user_token = params.get("token", None)

if not user_token:
    st.error("⛔ Access Denied. No token provided.")
    st.stop()

# 3. LOAD DATA & CONFIG
df_data = conn.read(worksheet="Data", ttl=0, keep_default_na=False)
df_data['Token'] = df_data['Token'].astype(str)
df_config = conn.read(worksheet="Config", ttl=0)

# 4. FIND THE USER'S ROW
user_row_index = df_data[df_data['Token'] == user_token].index
if user_row_index.empty:
    st.error("⛔ Invalid Token. Please check your link.")
    st.stop()

user_row_index = user_row_index[0] 
current_client_name = df_data.at[user_row_index, 'Client']

# 5. SIDEBAR NAVIGATION
st.sidebar.title(f"🏙️ {current_client_name}")
st.sidebar.markdown("---")
tabs = df_config['Tab'].unique()
selected_tab = st.sidebar.radio("Navigate", tabs)

# 6. DYNAMIC FORM GENERATOR
st.header(f"{selected_tab} Reporting")

tab_questions = df_config[df_config['Tab'] == selected_tab]

# --- DYNAMIC SECTION DESCRIPTION ---
if 'Tab Description' in df_config.columns:
    descriptions = tab_questions['Tab Description'].dropna().unique()
    if len(descriptions) > 0 and str(descriptions[0]).strip() != "":
        st.markdown(str(descriptions[0]))
        st.write("") 

with st.form(key='dynamic_form'):
    user_responses = {}

    for index, row in tab_questions.iterrows():
        col_name = row['Column Name']
        label = row['Label']
        input_type = row['Type']
        
        # --- SUBHEADER LOGIC WITH UNDERLINE ---
        if input_type == 'subheader':
            st.markdown("---") 
            st.markdown(f"### <u>{label}</u>", unsafe_allow_html=True)
            st.write("") 
            continue 
            
        # SAFETY CHECK
        if col_name in df_data.columns:
            raw_current_val = df_data.at[user_row_index, col_name]
        else:
            raw_current_val = ""
            
        clean_current_val = format_cell_value(raw_current_val)

        # --- 1. DISPLAY THE QUESTION LABEL FIRST ---
        st.markdown(f"**{label}**")

        # --- 2. CHECK FOR PREVIOUS YEAR'S DATA ---
        if 'Previous_Col' in row and pd.notna(row['Previous_Col']):
            prev_col_name = str(row['Previous_Col']).strip()
            
            if prev_col_name in df_data.columns:
                raw_prev_val = df_data.at[user_row_index, prev_col_name]
                clean_prev_val = format_cell_value(raw_prev_val)
                
                # Only show the "Last year's response" caption if it is NOT a readonly field
                if clean_prev_val != "" and input_type != 'readonly':
                    st.caption(f"🗓️ **Last year's response:** {clean_prev_val}")

        # --- 3. RENDER THE WIDGET ---
        if input_type == 'text':
             user_responses[col_name] = st.text_input(label=label, label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label=label, label_visibility="collapsed", value=clean_current_val, key=col_name)
             
        # --- UPDATED READ-ONLY LOGIC WITH AUTO-FORMATTING ---
        elif input_type == 'readonly':
             display_text = clean_current_val
             
             # Smart Fallback
             if display_text == "" and 'Previous_Col' in row and pd.notna(row['Previous_Col']):
                 prev_col_name = str(row['Previous_Col']).strip()
                 if prev_col_name in df_data.columns:
                     display_text = format_cell_value(df_data.at[user_row_index, prev_col_name])
             
             # --- DYNAMIC BOLDING & UNDERLINING ---
             # This automatically finds "[Any Number] BMPs completed:" and wraps it in <u>** **</u>
             display_text = re.sub(r'(?i)(\d+\s*BMPs completed:)', r'<u>**\1**</u>', display_text)
             
             # This automatically finds "BMPs in progress:" and wraps it in <u>** **</u>
             display_text = re.sub(r'(?i)(BMPs in progress:)', r'<u>**\1**</u>', display_text)
             
             # Replace standard newlines with Markdown breaks so your spreadsheet formatting stays perfect
             display_text = display_text.replace('\n', '  \n')
             
             # Print as standard text. unsafe_allow_html=True tells Streamlit to actually render the <u> tag!
             if display_text != "":
                 st.markdown(display_text, unsafe_allow_html=True)
        
        elif input_type == 'dropdown':
            options_str = str(row['Options']) if pd.notna(row['Options']) else ""
            options = [opt.strip() for opt in options_str.split(',')]
            
            try:
                current_index = options.index(clean_current_val)
            except ValueError:
                current_index = 0
            
            user_responses[col_name] = st.selectbox(label=label, label_visibility="collapsed", options=options, index=current_index, key=col_name)
        
        elif input_type == 'number':
            try:
                num_val = float(clean_current_val)
                if num_val.is_integer():
                    num_val = int(num_val)
            except ValueError:
                num_val = 0
                
            user_responses[col_name] = st.number_input(label=label, label_visibility="collapsed", value=num_val, key=col_name)
        
        elif input_type == 'checkbox':
            is_checked = True if str(clean_current_val).lower() == 'true' else False
            user_responses[col_name] = st.checkbox(label="Check if Yes", value=is_checked, key=col_name)
        
        elif input_type == 'date':
             user_responses[col_name] = st.text_input(label=label, label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        st.write("")
    
    # 7. SAVE BUTTON
    submitted = st.form_submit_button("💾 Save Progress")
    if submitted:
        for col, new_val in user_responses.items():
            df_data.at[user_row_index, col] = new_val
        
        conn.update(worksheet="Data", data=df_data)
        st.success(f"✅ Saved data for {selected_tab}!")
        st.rerun()
