import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

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

# --- THE ROUTER ---
# 3. READ DIRECTORY TO FIND THE USER'S COUNTY
df_directory = conn.read(worksheet="Directory", ttl=0)
df_directory['Token'] = df_directory['Token'].astype(str)

user_info = df_directory[df_directory['Token'] == user_token]
if user_info.empty:
    st.error("⛔ Invalid Token. Please check your link or the Directory tab.")
    st.stop()

# Extract the user's Client Name and County
current_client_name = user_info['Client'].iloc[0]
user_county = user_info['County'].iloc[0] # This will pull "LA", "OC", etc.

# 4. LOAD THE CORRECT DATA & CONFIG SHEETS DYNAMICALLY
# --- UPDATED: skiprows=3 to account for your new header row! ---
df_data = conn.read(worksheet=f"{user_county}_Data", ttl=0, keep_default_na=False, skiprows=3)
df_data['Token'] = df_data['Token'].astype(str)

df_config = conn.read(worksheet=f"{user_county}_Config", ttl=0)

# 5. FIND THE USER'S ROW IN THEIR SPECIFIC DATA SHEET
user_row_index = df_data[df_data['Token'] == user_token].index
if user_row_index.empty:
    st.error(f"⛔ Token found in Directory, but missing from {user_county}_Data sheet!")
    st.stop()

user_row_index = user_row_index[0] 

# 6. SIDEBAR NAVIGATION
st.sidebar.title(f"🏙️ {current_client_name}")
st.sidebar.markdown("---")
tabs = df_config['Tab'].unique()
selected_tab = st.sidebar.radio("Navigate", tabs)

# 7. DYNAMIC FORM GENERATOR
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
        # Smart bullet point formatter
        display_label = str(label)
        if "•" in display_label:
            parts = display_label.split("•")
            formatted_label = f"**{parts[0].strip()}**\n" # The main question text
            for part in parts[1:]:
                if part.strip(): # Make sure it's not a blank space
                    formatted_label += f"* **{part.strip()}**\n" # Markdown bullet point
            st.markdown(formatted_label)
        else:
            st.markdown(f"**{display_label}**")

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
             
        # --- READ-ONLY LOGIC WITH AUTO-FORMATTING ---
        elif input_type == 'readonly':
             display_text = clean_current_val
             
             # Smart Fallback
             if display_text == "" and 'Previous_Col' in row and pd.notna(row['Previous_Col']):
                 prev_col_name = str(row['Previous_Col']).strip()
                 if prev_col_name in df_data.columns:
                     display_text = format_cell_value(df_data.at[user_row_index, prev_col_name])
             
             # Dynamic bolding & underlining
             display_text = re.sub(r'(?i)(\d+\s*BMPs completed:)', r'<u>**\1**</u>', display_text)
             display_text = re.sub(r'(?i)(BMPs in progress:)', r'<u>**\1**</u>', display_text)
             
             # Replace standard newlines with Markdown breaks
             display_text = display_text.replace('\n', '  \n')
             
             # Print as standard text
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
    
    # 8. SAVE BUTTON
    submitted = st.form_submit_button("💾 Save Progress")
    if submitted:
        for col, new_val in user_responses.items():
            df_data.at[user_row_index, col] = new_val
        
        # --- Save back to the correct County's Data sheet! ---
        conn.update(worksheet=f"{user_county}_Data", data=df_data)
        st.success(f"✅ Saved data for {selected_tab}!")
        st.rerun()
