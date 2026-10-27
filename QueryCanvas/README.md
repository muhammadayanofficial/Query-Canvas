# QueryCanvas

QueryCanvas is a local SQL workbench for exploring CSV datasets with Python, Flask, and SQLite. It includes a dataset explorer, read-only SQL editor, result grid, CSV export, saved queries, schema inspection, and optional Gemini-assisted SQL drafting.

## Features

- Import CSV files (maximum 5 MB, 50,000 rows, and 80 columns).
- Import and save multiple datasets in a local SQLite database.
- Run read-only `SELECT` and `WITH` queries against the currently selected dataset.
- Use the built-in sample orders dataset to try the app immediately.
- Inspect schema, view up to 200 rows, and export result rows to CSV.
- Save and delete reusable queries.
- Optionally draft SQL from a plain-English question using the Gemini API.
- Responsive three-pane workbench layout and keyboard shortcut `Ctrl+Enter` / `Cmd+Enter` to run.

## Requirements

- Python 3.10 or newer.
- Internet connection during setup to install the packages in `requirements.txt`.
- A Gemini API key only if you want AI query generation. Manual SQL and CSV imports work without a key.

## Setup on Windows / VS Code

1. Extract `QueryCanvas.zip`.
2. Open the `QueryCanvas` folder in VS Code.
3. Open the integrated terminal and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation on your machine, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate the environment again.

4. Copy `.env.example` to `.env`. You can leave `GEMINI_API_KEY` empty to use manual SQL. For AI SQL drafting, put your own Gemini API key in `.env` and keep that file private.
5. Start the application:

```powershell
python app.py
```

6. Open `http://127.0.0.1:5000` in your browser.

## Example query

The app starts with a sample table named `orders_sample`:

```sql
SELECT
    region,
    SUM(revenue) AS total_revenue,
    COUNT(*) AS order_count
FROM orders_sample
GROUP BY region
ORDER BY total_revenue DESC;
```

After importing a CSV, select it in the Explorer pane and use the generated table name shown in the Schema panel.

## AI configuration

`.env` example:

```env
SECRET_KEY=replace_with_a_random_secret_key
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.8-flash
FLASK_DEBUG=false
```

The API key is read only by Python and is never sent to browser JavaScript. The model can be changed with `GEMINI_MODEL` if your API account uses a different available model.

## Safety and limitations

- The SQL runner only permits read-only queries, limits results to 200 rows, restricts reads to the selected dataset table, and applies a short execution timeout.
- It does not execute uploaded code.
- CSV content is stored in `instance/querycanvas.sqlite3` on your computer. Avoid uploading sensitive information to a shared machine.
- AI-generated SQL should be reviewed before running. If the API is unavailable or no key is configured, manual SQL remains available.
- This is a local prototype, not a multi-user hosted service. Do not expose the Flask development server directly to the public internet.

## Tests

Run the basic tests with:

```powershell
python -m unittest discover -s tests -v
```

The tests cover safe column-name generation, CSV value parsing, read-only query validation, table access restrictions, and one-statement execution.
