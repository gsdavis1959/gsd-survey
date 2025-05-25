import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Text # Added Text for clarity, though String would also work
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pandas as pd
import datetime
import openai
import os
import smtplib
import json
from email.message import EmailMessage



client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# WARNING: Hardcoding API keys is a security risk. Prefer environment variables.


# Database connection details
engine = create_engine('sqlite:///data.db')
Base = declarative_base()

class User(Base):
    __tablename__ = "users_personality"  # New table for personality data

    id = Column(Integer, primary_key=True)
    current_date = Column(String)
    ratings = Column(Text)  # Store ratings as JSON string (SQLite uses TEXT)
    personality_assessment = Column(Text) # Store OpenAI response (SQLite uses TEXT)

# Function to load questions from Excel
@st.cache_data # Cache the data to avoid reloading on every script run
def load_questions(file_path="questions.csv"): # Changed to accept file_path, defaults to questions.csv
    # if uploaded_file_obj is None:
    #     # st.info("Please upload the questions.xlsx file.") # Optional: message if no file uploaded yet
    #     return None
    try:
        # Construct the absolute path to the questions.csv file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        absolute_file_path = os.path.join(script_dir, file_path)
        df = pd.read_csv(absolute_file_path)
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        # Basic validation
        required_columns = ['Item#', 'QuestionStatement', 'MinRating', 'MaxRating', 'MinRatingAnchor', 'MaxRatingAnchor']
        if not all(col in df.columns for col in required_columns):
            st.error(f"The uploaded CSV file must contain columns: {', '.join(required_columns)}")
            return None
        return df
    except FileNotFoundError:
        st.error(f"Error: The file '{file_path}' was not found in the same directory as the app. Please ensure it exists.")
        return None
    except Exception as e:
        st.error(f"Error loading or parsing '{file_path}': {e}")
        return None



# Function to send the email with a DataFrame attachment
def send_email_with_attachment(csv_file_path):
    try:
        # Email configuration
        sender_email = "gsdavis1959@gmail.com"
        receiver_email = "gsdavis1959@gmail.com"
        app_password = "zexi eytr nhcx odsq"  # Use an app password for security

        # Create the email message
        msg = EmailMessage()
        msg['Subject'] = "File from Website"
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg.set_content('File Attached')

        # Attach the CSV file
        with open(csv_file_path, 'rb') as file:
            msg.add_attachment(file.read(), maintype='application', subtype='csv', filename=os.path.basename(csv_file_path))

        # Send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)

        os.remove(csv_file_path) # Clean up the temporary CSV file

        return "Email sent successfully!"
    except Exception as e:
        return f"Error sending email: {e}"



# Create the database and the table if they don't exist
Base.metadata.create_all(engine)

# Creating a session to interact with the database
Session = sessionmaker(bind=engine)
session = Session()

# Initialize session state for personality assessment text
if "personality_assessment_text" not in st.session_state:
    st.session_state.personality_assessment_text = None

# # File uploader for questions.xlsx - REMOVED
# st.sidebar.header("Load Personality Questions")
# uploaded_excel_file = st.sidebar.file_uploader("Upload your questions CSV file", type=["csv"])


# Load questions
questions_df = load_questions() # Now loads "questions.csv" by default

# Function to generate personality assessment
def get_personality_assessment(ratings_dict, questions_data_df):
    formatted_questions_ratings = []
    for item_id, rating in ratings_dict.items():
        question_row = questions_data_df[questions_data_df['Item#'] == item_id]
        if not question_row.empty:
            question_text = question_row['QuestionStatement'].iloc[0]
            min_rating_val = question_row['MinRating'].iloc[0]
            max_rating_val = question_row['MaxRating'].iloc[0]
            min_anchor = question_row['MinRatingAnchor'].iloc[0]
            max_anchor = question_row['MaxRatingAnchor'].iloc[0]
            formatted_questions_ratings.append(
                f"- Question: \"{question_text}\" (Rated: {rating} on a scale of {min_rating_val}-{max_rating_val}, where {min_rating_val} means '{min_anchor}' and {max_rating_val} means '{max_anchor}')"
            )
        else:
            # Fallback if question text not found, though Item# should always be in questions_data_df
            formatted_questions_ratings.append(f"- {item_id}: {rating} (Question text not found)")
    
    ratings_details_string = "\n".join(formatted_questions_ratings)

    prompt = f"""
You are an expert in personality assessment with a PhD in psychometrics and personality.
Use the Big 5 personality traits framework to evaluate the questions and my ratings . 
Format the response in four sections. 
Section 1: Provide a bullet point list of the Big 5 dimensions and the scores. 
Section 2: Write a brief 500 word analysis of my personality; provide meaningful insigts about how I might be percieved by others.
Characterize my personality in a style that is engaging and relatable. Try not to use the statements in your observations.
Section 3; Recommend occumpations and hobbies that could be a good fit for me. 
Section 4: Describe "blind spots" you see in my personality, or areas where I may not be aware of when I interact with others. 
Highlist any potential areas for growth or development. Identify where interaction with others might be difficult
or challenging for me.
Here are the questions and their ratings:
{ratings_details_string}

Provide a concise personality assessment in a single paragraph (around 150-200 words).
"""
    try:
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=[{"role": "user", "content": prompt}]
        )
        assessment_text = response.choices[0].message.content.strip()
        return assessment_text
    except Exception as e:
        st.error(f"Error communicating with OpenAI: {e}")
        return "Could not retrieve assessment due to an error."

def add_user_assessment(submission_date, ratings_dict, assessment_text):
    ratings_json = json.dumps(ratings_dict)
    new_assessment_entry = User(
        current_date=submission_date,
        ratings=ratings_json,
        personality_assessment=assessment_text
    )
    session.add(new_assessment_entry)
    session.commit()

# Main input
st.title("Personality Assessment") 
st.write("This experimental site uses ChatGPT to offer insights into your personality based on your self-ratings. This is not a clinical diagnostic tool and is not intended to replace professional psychological advice. All information collected will be kept confidential and used solely for research purposes. By continuing, you indicate your informed consent to participate.")

if questions_df is not None:
    # Use columns to center the questions
    col1, col_main, col3 = st.columns([1, 3, 1])

    with col_main:
        st.subheader("Please rate the following statements:")
        
        current_ratings = {}
        for index, row in questions_df.iterrows():
            item_id = row['Item#']
            question_statement = row['QuestionStatement']
            min_rating = int(row['MinRating'])
            max_rating = int(row['MaxRating'])
            min_anchor = row['MinRatingAnchor']
            max_anchor = row['MaxRatingAnchor']
            
            slider_key = f"rating_{item_id}"

            # Initialize slider state if not present (e.g., for first run or after clearing)
            if slider_key not in st.session_state:
                st.session_state[slider_key] = int(min_rating + (max_rating - min_rating) / 2) # Default to midpoint

            st.markdown(f"---")
            st.markdown(f"**{question_statement}**")
            
            # Display anchors below the question, above the slider
            # st.caption(f"Scale: {min_rating} ({min_anchor}) to {max_rating} ({max_anchor})")
            
            # Slider with anchors in help text or as part of a more complex label
            # For simplicity, we'll use the anchors in the label or surrounding text.
            
            # Layout for slider with anchors at ends (conceptual)
            s_col1, s_col2, s_col3 = st.columns([2,6,2]) # Increased width for anchors and slider
            with s_col1:
                st.caption(min_anchor)
            with s_col2:
                current_ratings[item_id] = st.slider(
                    label=f"Rate for '{item_id}'", 
                    min_value=min_rating, 
                    max_value=max_rating, 
                    key=slider_key,
                    label_visibility="collapsed" # Hide the actual label string, rely on surrounding text
                )
            with s_col3:
                st.caption(max_anchor)

        if st.button("Get Personality Assessment"):
            if not current_ratings:
                st.warning("Please answer the questions before getting an assessment.")
            else:
                with st.spinner("Analyzing your responses..."):
                    assessment = get_personality_assessment(current_ratings, questions_df)
                    st.session_state.personality_assessment_text = assessment
        
        if st.session_state.personality_assessment_text:
            st.markdown("---")
            st.subheader("Your Personality Assessment:")
            st.write(st.session_state.personality_assessment_text)

if st.button("Click to Finish Session"):
    if questions_df is None:
        st.error("Cannot finish session as questions could not be loaded.")
    elif not st.session_state.get('personality_assessment_text'):
        st.warning("Please get your personality assessment before finishing the session.")
    else:
        # Collect final ratings
        final_ratings = {}
        for index, row in questions_df.iterrows():
            item_id = row['Item#']
            slider_key = f"rating_{item_id}"
            if slider_key in st.session_state:
                final_ratings[item_id] = st.session_state[slider_key]
            else: # Should not happen if assessment was generated
                final_ratings[item_id] = int(row['MinRating'] + (row['MaxRating'] - row['MinRating']) / 2)

        submission_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        add_user_assessment(submission_time, final_ratings, st.session_state.personality_assessment_text)
        
        # Prepare data for CSV
        sql = "SELECT * FROM users_personality"
        db_df = pd.read_sql(sql, con=engine)

        # Expand the 'ratings' JSON column
        if not db_df.empty and 'ratings' in db_df.columns:
            try:
                ratings_expanded = db_df['ratings'].apply(lambda x: json.loads(x) if pd.notna(x) and x else {})
                ratings_df = pd.json_normalize(ratings_expanded)
                # Ensure all possible question item columns exist, even if some rows don't have them
                for item_id in questions_df['Item#']:
                    if item_id not in ratings_df.columns:
                        ratings_df[item_id] = pd.NA 
                db_df = pd.concat([db_df.drop(columns=['ratings']), ratings_df], axis=1)
            except json.JSONDecodeError as e:
                st.error(f"Error processing ratings data for CSV: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred while preparing CSV data: {e}")

        csv_file_name = "personality_assessment_data.csv"
        db_df.to_csv(csv_file_name, index=False)
        
        email_result = send_email_with_attachment(csv_file_name)
        st.success(f"Thank you for your participation! {email_result}")
        
        # Clear session state for a new test
        keys_to_delete = ['personality_assessment_text']
        for index, row in questions_df.iterrows():
            keys_to_delete.append(f"rating_{row['Item#']}")
        
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
else:
    # This block will now primarily trigger if questions_df is None due to file not found or format error
    if questions_df is None: # Simplified condition
        st.warning("Questions file ('questions.csv') not loaded or is improperly formatted. Please ensure 'questions.csv' exists in the same directory as the app and has the required columns: Item#, QuestionStatement, MinRating, MaxRating, MinRatingAnchor, MaxRatingAnchor.")


st.sidebar.info("This app is for research and educational purposes.")

# To run this app:
# 1. Save this code as app.py.
# 2. Prepare a CSV file with columns: Item#, QuestionStatement, MinRating, MaxRating, MinRatingAnchor, MaxRatingAnchor
#    Example row: Q1, "I enjoy social gatherings.", 0, 10, "Strongly Disagree", "Strongly Agree"
# 3. Install necessary libraries: pip install streamlit sqlalchemy pandas openpyxl openai
# 4. Run from terminal: streamlit run app.py
