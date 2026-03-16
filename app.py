import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

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
    
    # Convert to string and clean whitespace
    str_val = str(val).strip()
    
    # If pandas converted an empty cell to 'nan'
    if str_val.lower() == 'nan':
        return ""
        
    try:
        # Check if it's a number
        float_val = float(str_val)
        # If it's a perfect whole number (e.g., 99.0), drop the .0
        if float_val.is_integer():
            return str(int(float_val))
        # If it has a real decimal (e.g., 99.6), leave it
        else:
            return str(float_val)
    except ValueError:
        # If it's plain text (like "None", "N/A", or "Yes"), just return the text!
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
# keep_default_na=False tells pandas to stop turning "N/A" into blank values!
df_data = conn.read(worksheet="Data", ttl=0, keep_default_na=False)
df_data['Token'] = df_data['Token'].astype(str)
df_config = conn.read(worksheet="Config", ttl=0)

# 4. FIND THE USER'S ROW
user_row_index = df_data[df_data['Token'] == user_token].index
if user_row_index.empty:
    st.error("⛔ Invalid Token. Please check your link.")
    st.stop()

user_row_index = user_row_index[0] # Get the actual integer index
current_client_name = df_data.at[user_row_index, 'Client']

# 5. SIDEBAR NAVIGATION
st.sidebar.title(f"🏙️ {current_client_name}")
st.sidebar.markdown("---")
# Get unique tabs from your Config sheet
tabs = df_config['Tab'].unique()
selected_tab = st.sidebar.radio("Navigate", tabs)

# 6. DYNAMIC FORM GENERATOR
st.header(f"{selected_tab} Reporting")

# Filter config for just this tab
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
        
        # Get existing value and run it through our new formatting function
        raw_current_val = df_data.at[user_row_index, col_name]
        clean_current_val = format_cell_value(raw_current_val)

        # --- 1. DISPLAY THE QUESTION LABEL FIRST ---
        st.markdown(f"**{label}**")

        # --- 2. CHECK FOR PREVIOUS YEAR'S DATA ---
        if 'Previous_Col' in row and pd.notna(row['Previous_Col']):
            prev_col_name = str(row['Previous_Col']).strip()
            
            if prev_col_name in df_data.columns:
                raw_prev_val = df_data.at[user_row_index, prev_col_name]
                clean_prev_val = format_cell_value(raw_prev_val)
                
                # If there is actually data there (including "None" or "0"), display it
                if clean_prev_val != "":
                    st.caption(f"🗓️ **Last year's response:** {clean_prev_val}")

        # --- 3. RENDER THE WIDGET ---
        if input_type == 'text':
             user_responses[col_name] = st.text_input(label=label, label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label=label, label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        elif input_type == 'dropdown':
            options_str = str(row['Options']) if pd.notna(row['Options']) else ""
            options = [opt.strip() for opt in options_str.split(',')]
            
            try:
                current_index = options.index(clean_current_val)
            except ValueError:
                current_index = 0
            
            user_responses[col_name] = st.selectbox(label=label, label_visibility="collapsed", options=options, index=current_index, key=col_name)
        
        elif input_type == 'number':
            # Number inputs require actual numbers. If it's text like "None", fallback to 0.
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
