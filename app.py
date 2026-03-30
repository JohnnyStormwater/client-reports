import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

# --- HELPER FUNCTIONS FOR FORMATTING ---
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

def format_currency(val_str):
    """
    Forces numbers in the financial tab back into currency formatting
    (e.g., '7000' -> '$7,000') just in case Google Sheets passes raw numbers.
    """
    if "$" in val_str:
        return val_str # If it already has a $, leave it alone!
    try:
        clean_num = val_str.replace(",", "")
        f_val = float(clean_num)
        if f_val.is_integer():
            return f"${int(f_val):,}"
        else:
            return f"${f_val:,.2f}"
    except ValueError:
        return val_str # If it's pure text like "N/A", leave it as text

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
user_county = user_info['County'].iloc[0] 

# 4. LOAD THE CORRECT DATA & CONFIG SHEETS DYNAMICALLY
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
if user_county == "OC":
    sidebar_icon = "🍊"
else:
    sidebar_icon = "🏙️"

st.sidebar.title(f"{sidebar_icon} {current_client_name}")
st.sidebar.markdown("---")
tabs = df_config['Tab'].unique()
selected_tab = st.sidebar.radio("Navigate", tabs)

# 7. DYNAMIC FORM GENERATOR
st.header(selected_tab)

tab_questions = df_config[df_config['Tab'] == selected_tab]

# --- DYNAMIC SECTION DESCRIPTION ---
if 'Tab Description' in df_config.columns:
    descriptions = tab_questions['Tab Description'].dropna().unique()
    if len(descriptions) > 0 and str(descriptions[0]).strip() != "":
        st.markdown(str(descriptions[0]))
        st.write("") 

with st.form(key='dynamic_form'):
    # TOP SAVE BUTTON
    submitted_top = st.form_submit_button("💾 Save Progress", key="save_top")
    
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
                # Add a tiny visual gap before the divider so it groups nicely with the NEW section
                st.write("") 
                st.markdown("---") 
            
            # Adjusted margin-bottom to bring the next question closer to the subheader
            st.markdown(f"<h3 style='margin-top: 0px; margin-bottom: 10px;'><u>{label}</u></h3>", unsafe_allow_html=True)
            is_first_item = False
            continue 
            
        # SAFETY CHECK
        if col_name in df_data.columns:
            raw_current_val = df_data.at[user_row_index, col_name]
        else:
            raw_current_val = ""
            
        clean_current_val = format_cell_value(raw_current_val)

        # --- 1. DISPLAY THE QUESTION LABEL FIRST ---
        # Strip out any accidental asterisks written in the spreadsheet data
        display_label = str(label).replace("**", "").strip()
        
        if "•" in display_label:
            parts = display_label.split("•")
            formatted_label = f"**{parts[0].strip()}**\n" 
            for part in parts[1:]:
                if part.strip(): 
                    formatted_label += f"* **{part.strip()}**\n" 
            st.markdown(formatted_label)
        else:
            # Smart Multi-Line Bolding Logic
            formatted_parts = []
            for line in display_label.split('\n'):
                if line.strip(): 
                    formatted_parts.append(f"**{line.strip()}**")
            
            st.markdown("  \n\n".join(formatted_parts))

        # --- 2. CONTEXTUAL DATA (LAST YEAR & JLHA) ---
        if 'Previous_Col' in row and pd.notna(row['Previous_Col']):
            prev_col_name = str(row['Previous_Col']).strip()
            
            if prev_col_name in df_data.columns:
                raw_prev_val = df_data.at[user_row_index, prev_col_name]
                clean_prev_val = format_cell_value(raw_prev_val)
                
                if clean_prev_val != "" and input_type != 'readonly':
                    if is_financial:
                        display_prev = format_currency(clean_prev_val)
                        st.caption(f"💰 **Last Year's Total:** {display_prev}")
                    else:
                        st.caption(f"🗓️ **Last year's response:** {clean_prev_val}")

        if 'JLHA_Col' in df_config.columns and 'JLHA_Col' in row and pd.notna(row['JLHA_Col']):
            jlha_col_name = str(row['JLHA_Col']).strip()
            
            if jlha_col_name in df_data.columns:
                raw_jlha_val = df_data.at[user_row_index, jlha_col_name]
                clean_jlha_val = format_cell_value(raw_jlha_val)
                
                if clean_jlha_val != "" and input_type != 'readonly':
                    display_jlha = format_currency(clean_jlha_val) if is_financial else clean_jlha_val
                    st.caption(f"🐟 **JLHA Expenses:** {display_jlha}")

        # --- 3. RENDER THE WIDGET ---
        if input_type == 'text':
             user_responses[col_name] = st.text_input(label="hidden_label", label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        elif input_type == 'textarea':
             user_responses[col_name] = st.text_area(label="hidden_label", label_visibility="collapsed", value=clean_current_val, key=col_name)
             
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
                num_val = float(clean_current_val)
                if num_val.is_integer():
                    num_val = int(num_val)
            except ValueError:
                num_val = 0
                
            user_responses[col_name] = st.number_input(label="hidden_label", label_visibility="collapsed", value=num_val, key=col_name)
        
        elif input_type == 'checkbox':
            is_checked = True if str(clean_current_val).lower() == 'true' else False
            user_responses[col_name] = st.checkbox(label="Check if Yes", value=is_checked, key=col_name)
        
        elif input_type == 'date':
             user_responses[col_name] = st.text_input(label="hidden_label", label_visibility="collapsed", value=clean_current_val, key=col_name)
        
        # We removed the extra st.write("") here so the form elements stay tight!
        is_first_item = False 
    
    # 8. BOTTOM SAVE BUTTON & SUBMISSION LOGIC
    # Add a little space right before the bottom save button so it doesn't crowd the last question
    st.write("") 
    submitted_bottom = st.form_submit_button("💾 Save Progress", key="save_bottom")
    
    if submitted_top or submitted_bottom:
        for col, new_val in user_responses.items():
            df_data.at[user_row_index, col] = new_val
        
        conn.update(worksheet=f"{user_county}_Data", data=df_data)
        st.success(f"✅ Saved data for {selected_tab}!")
        st.rerun()
