import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

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
# We use ttl=0 so it always grabs fresh data
df_data = conn.read(worksheet="Data", ttl=0)
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

# --- NEW FEATURE: DYNAMIC SECTION DESCRIPTION ---
# We check if the column exists so the app doesn't crash if you haven't updated the sheet yet
if 'Tab Description' in df_config.columns:
    # Grab the description, dropping any empty cells
    descriptions = tab_questions['Tab Description'].dropna().unique()
    
    # If a description exists and isn't blank, display it!
    if len(descriptions) > 0 and str(descriptions[0]).strip() != "":
        st.markdown(str(descriptions[0]))
        st.write("") # Adds a tiny bit of breathing room before the form starts

with st.form(key='dynamic_form'):
    
    user_responses = {}

    for index, row in tab_questions.iterrows():
        col_name = row['Column Name']
        label = row['Label']
        input_type = row['Type']
        
        # Get existing value from Data sheet
        current_val = df_data.at[user_row_index, col_name]

        # --- 1. DISPLAY THE QUESTION LABEL FIRST ---
        st.markdown(f"**{label}**")

        # --- 2. CHECK FOR PREVIOUS YEAR'S DATA ---
        if 'Previous_Col' in row and pd.notna(row['Previous_Col']):
            prev_col_name = str(row['Previous_Col']).strip()
            
            # Make sure you actually created this column in the Data sheet!
            if prev_col_name in df_data.columns:
                prev_val = df_data.at[user_row_index, prev_col_name]
                
                # If there is actually data there, display it as read-only text
                if pd.notna(prev_val) and str(prev_val).strip() != "":
                    st.caption(f"🗓️ **Last year's response:** {prev_val}")

        # --- 3. RENDER THE WIDGET (Space collapsed so it sits cleanly below the text) ---
        if input_type == 'text':
             user_responses[col_name] = st.text_input(label=label, label_visibility="collapsed", value=str(current_val) if pd.notna(current_val) else "", key=col_name)
        
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label=label, label_visibility="collapsed", value=str(current_val) if pd.notna(current_val) else "", key=col_name)
        
        elif input_type == 'dropdown':
            # Get options from the 'Options' column, split by comma
            options_str = str(row['Options']) if pd.notna(row['Options']) else ""
            options = [opt.strip() for opt in options_str.split(',')]
            
            # Find the index of the currently saved value (so it stays selected)
            try:
                current_index = options.index(str(current_val))
            except ValueError:
                current_index = 0
            
            user_responses[col_name] = st.selectbox(label=label, label_visibility="collapsed", options=options, index=current_index, key=col_name)
        
        elif input_type == 'number':
            user_responses[col_name] = st.number_input(label=label, label_visibility="collapsed", value=float(current_val) if pd.notna(current_val) else 0.0, key=col_name)
        
        elif input_type == 'checkbox':
            # Checkbox needs boolean
            is_checked = True if str(current_val).lower() == 'true' else False
            # Checkboxes render their labels inline, so we don't collapse this one!
            user_responses[col_name] = st.checkbox(label="Check if Yes", value=is_checked, key=col_name)
        
        elif input_type == 'date':
             user_responses[col_name] = st.text_input(label=label, label_visibility="collapsed", value=str(current_val) if pd.notna(current_val) else "", key=col_name)
        
        # Add a little visual space between questions
        st.write("")
    
    # 7. SAVE BUTTON
    submitted = st.form_submit_button("💾 Save Progress")
    if submitted:
        # Update the specific cells in the dataframe
        for col, new_val in user_responses.items():
            df_data.at[user_row_index, col] = new_val
        
        # Write back to Google Sheets
        conn.update(worksheet="Data", data=df_data)
        st.success(f"✅ Saved data for {selected_tab}!")
        st.rerun()
