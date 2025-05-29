import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
import io

# --- Configuration for Streamlit Page ---
st.set_page_config(
    page_title="📊 Excel to SQL Query Generator",
    layout="centered",
    initial_sidebar_state="auto"
)

# --- Custom CSS for design (minimal for now, we can add more later) ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');

    html, body, [class*="st-"] {
        font-family: 'Poppins', sans-serif;
    }
    h1 {
        color: #2ECC71; /* Green for a data-focused app */
        text-align: center;
    }
    .stButton>button {
        background-color: #3498DB; /* Blue button */
        color: white;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 1.1em;
        border: none;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #2980B9;
        transform: translateY(-2px);
    }
    .stTextInput label, .stFileUploader label {
        font-weight: 600;
        color: #333;
    }
    .stCode {
        background-color: #ecf0f1; /* Light gray for code blocks */
        border-left: 5px solid #2ECC71;
        padding: 10px;
        border-radius: 5px;
        overflow-x: auto; /* Enable horizontal scrolling for long queries */
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📊 Excel to SQL Query Generator")
st.markdown("Upload your Excel file, ask a question, and get a SQL query!")

# --- API Key Input (first element) ---
api_key_from_env = os.environ.get("GOOGLE_API_KEY")

if "gemini_api_key_input_sql" not in st.session_state:
    st.session_state.gemini_api_key_input_sql = ""

placeholder_text = "Enter your Google Gemini API key here"
if api_key_from_env and not st.session_state.gemini_api_key_input_sql:
    st.session_state.gemini_api_key_input_sql = api_key_from_env
    placeholder_text = "API key loaded from environment variable"

gemini_api_key = st.text_input(
    "Google Gemini API Key",
    type="password",
    value=st.session_state.gemini_api_key_input_sql,
    placeholder=placeholder_text,
    help="You can get your API key from https://aistudio.google.com/app/apikey",
    key="gemini_api_key_input_sql_widget"
)

st.session_state.gemini_api_key_input_sql = gemini_api_key

current_api_key = st.session_state.gemini_api_key_input_sql.strip()


# Only proceed if an API key is available
if not current_api_key:
    st.warning("Please enter your Google Gemini API Key to use the generator.")
    st.stop() # Stop the execution of the rest of the app

# Configure the Gemini API key now that we have it
try:
    genai.configure(api_key=current_api_key)
    # Ping the model to ensure the key is valid (optional, but good for early error detection)
    model = genai.GenerativeModel('gemini-1.5-flash') # Using 1.5-flash for potential cost-effectiveness and speed
    # model.generate_content("test", generation_config=genai.types.GenerationConfig(max_output_tokens=1)) # Small test
except Exception as e:
    st.error(f"Failed to initialize Gemini model or API key is invalid. Error: {e}")
    st.warning("Please check your API key and refresh the page.")
    st.stop() # Halt execution if API key is invalid

# --- Excel File Uploader ---
uploaded_file = st.file_uploader(
    "Upload an Excel file (.xlsx)",
    type=["xlsx"],
    key="excel_uploader"
)

df = None
table_name = "data_table" # Default table name for SQL generation

if uploaded_file:
    try:
        # Read the Excel file into a pandas DataFrame
        df = pd.read_excel(uploaded_file)
        st.success(f"Successfully loaded '{uploaded_file.name}'.")

        # Display the first few rows and columns
        st.subheader("Preview of your data:")
        st.dataframe(df.head())

        # Display table schema for context
        st.subheader("Deduced Table Schema (for SQL Generation):")
        schema_info = pd.DataFrame({
            'Column Name': df.columns,
            'Data Type (Python)': df.dtypes.astype(str)
        })
        st.dataframe(schema_info)

        # Allow user to specify a table name
        default_table_name = uploaded_file.name.split('.')[0].replace(' ', '_').lower()
        table_name = st.text_input(
            "Enter a desired SQL table name for the query (e.g., sales_data)",
            value=default_table_name,
            help="This name will be used in the generated SQL queries (e.g., SELECT * FROM your_table_name)."
        )

    except Exception as e:
        st.error(f"Error reading Excel file: {e}. Please ensure it's a valid .xlsx file.")
        df = None # Reset df if there's an error

# --- SQL Query Generation ---
if df is not None:
    st.subheader("Ask a question about your data:")
    user_question = st.text_area(
        "Enter your natural language question (e.g., 'What is the sum of sales for each product category?')",
        height=100,
        placeholder="e.g., 'Show me the average age of customers in New York'",
        key="user_sql_question"
    )

    if st.button("Generate SQL Query"):
        if not user_question.strip():
            st.warning("Please enter a question to generate a SQL query.")
        else:
            with st.spinner("Generating SQL query..."):
                try:
                    # Construct the prompt for the LLM
                    # We provide column names and data types as context
                    columns = df.columns.tolist()
                    # Convert pandas dtypes to common SQL types for better LLM understanding
                    # This is a simplified mapping, might need refinement
                    dtype_mapping = {
                        'int64': 'INTEGER', 'float64': 'REAL', 'object': 'TEXT',
                        'datetime64[ns]': 'DATETIME', 'bool': 'BOOLEAN'
                    }
                    sql_columns_with_types = []
                    for col_name in columns:
                        sql_type = dtype_mapping.get(str(df[col_name].dtype), 'TEXT')
                        sql_columns_with_types.append(f"{col_name} {sql_type}")
                    schema_description = ", ".join(sql_columns_with_types)

                    prompt = f"""
                    You are an expert in SQL. Your task is to write a SQL query based on a user's question and a given table schema.
                    The table name is `{table_name}`.
                    The table has the following columns and their approximate SQL types:
                    {schema_description}

                    Based on this information, generate a SQL query that answers the user's question.
                    Ensure the query is standard SQL (e.g., compatible with SQLite, PostgreSQL, MySQL).
                    Do NOT include any explanations, just the SQL query itself.

                    User Question: {user_question}

                    SQL Query:
                    """

                    response = model.generate_content(prompt)
                    generated_sql = response.text.strip()

                    # Clean up common LLM formatting issues (e.g., Markdown code blocks)
                    if generated_sql.startswith("```sql"):
                        generated_sql = generated_sql[len("```sql"):].strip()
                    if generated_sql.endswith("```"):
                        generated_sql = generated_sql[:-len("```")].strip()

                    st.success("SQL Query Generated!")
                    st.code(generated_sql, language='sql')

                except Exception as e:
                    st.error(f"Error generating SQL query: {e}")
                    st.info("Please try rephrasing your question or check your API key.")
                    