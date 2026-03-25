# AI Data Analyst

An intelligent web application that allows users to upload CSV files and ask natural language questions about their data. Powered by AI (Groq/Llama), it provides instant insights, statistical analysis, and automatic chart generation.

## Features

- **CSV Upload & Analysis**: Upload any CSV file and get instant statistical summaries
- **AI-Powered Insights**: Ask questions in plain English and receive detailed analysis from advanced AI
- **Automatic Chart Generation**: AI suggests and generates relevant charts (bar, line, scatter, histogram, pie)
- **Interactive Web Interface**: Modern, responsive UI with drag-and-drop file upload
- **Data Preview**: View your data in a clean table format before asking questions
- **Conversation History**: Follow-up questions remember previous context
- **Export Charts**: Right-click to save generated charts as PNG files

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Data Processing**: Pandas for CSV analysis and statistics
- **Visualization**: Matplotlib for chart generation
- **AI**: Groq API with Llama 3.3 70B model
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Deployment**: Gunicorn for production

## Installation

### Prerequisites

- Python 3.8 or higher
- A free Groq API key (get one at [console.groq.com](https://console.groq.com))

### Setup

1. **Clone or download this repository**

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Create a `.env` file in the project root:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   SECRET_KEY=your_random_secret_key_here
   UPLOAD_FOLDER=uploads
   ```

5. **Run the application**:
   ```bash
   python app.py
   ```

6. **Open your browser** and go to `http://localhost:5000`

## Usage

1. **Upload a CSV file**: Drag and drop or click to select a CSV file
2. **Review your data**: Check the file info and preview table
3. **Ask questions**: Type natural language questions like:
   - "What are the total sales by region?"
   - "Show me the trend of sales over time"
   - "Which product has the highest sales?"
   - "What's the average price?"
4. **View insights**: Get AI-generated analysis with relevant statistics
5. **See charts**: Automatic chart generation based on your question
6. **Follow up**: Ask follow-up questions that reference previous answers

## Sample Data

The repository includes `uploads/sales_data_sample.csv` - a sample sales dataset you can use to test the application.

## API Endpoints

- `GET /` - Main application page
- `POST /upload` - Upload CSV file
- `GET /preview` - Get data preview
- `GET /summary` - Get statistical summary
- `POST /ask` - Ask AI questions
- `POST /chart` - Generate charts
- `POST /reset` - Clear session
- `GET /health` - Health check

## Configuration

### Environment Variables

- `GROQ_API_KEY`: Your Groq API key (required)
- `SECRET_KEY`: Flask session secret key (required)
- `UPLOAD_FOLDER`: Directory for uploaded files (default: 'uploads')
- `MAX_CONTENT_LENGTH`: Maximum file size in bytes (default: 5MB)

### File Size Limits

- Maximum CSV file size: 5MB
- Only CSV files are accepted
- Files are stored temporarily in the uploads folder

## Development

### Running in Debug Mode

The application runs in debug mode by default when started with `python app.py`. This provides:
- Automatic code reloading
- Detailed error pages
- Debug logging

### Production Deployment

For production, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Project Structure

```
ai-data-analyst/
├── app.py                 # Main Flask application
├── analysis.py           # CSV analysis and summarization
├── chart.py              # Chart generation with Matplotlib
├── gemini_helper.py      # AI integration (Groq API)
├── requirements.txt      # Python dependencies
├── static/
│   └── app.js           # Frontend JavaScript
├── templates/
│   └── index.html       # Main HTML template
└── uploads/             # Uploaded CSV files (auto-created)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is open source. Feel free to use and modify as needed.

## Troubleshooting

### Common Issues

1. **"GROQ_API_KEY not found"**: Make sure your `.env` file exists and contains the correct API key
2. **"Only .csv files are allowed"**: Ensure your uploaded file has a `.csv` extension
3. **Chart not generating**: Check that your data has numeric columns for charting
4. **Large files failing**: Files are limited to 5MB by default

### Getting Help

- Check the browser console for JavaScript errors
- Review Flask logs in the terminal for backend errors
- Ensure all dependencies are installed correctly

## Future Enhancements

- Support for additional file formats (Excel, JSON)
- More chart types and customization options
- Data cleaning and preprocessing tools
- Export analysis reports as PDF
- User accounts and saved analyses
- API endpoints for programmatic access
