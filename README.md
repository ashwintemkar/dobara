# Dobara

A repair-shop counter. Customers and jobs live in Supabase. A new complaint is sent, with that customer's real rows, to Gemma on OpenRouter. The slip is saved, and any open counter updates through Supabase Realtime.

Nothing about a customer is stored in the source code. The shop rule (comeback days, labor, quotes) is one row you can edit on the page.

## Run the SQL

In a **new** Supabase project, open the SQL editor and run `schema.sql`.

That creates `policy`, `technicians`, `customers`, `jobs`, and `decisions`, lets the public anon key read them, and adds the tables to Realtime. Writes go through this server with the service role key.

## Environment

Copy `.env.example` to `.env` and fill it in. Do not commit `.env`.

```
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
OPENROUTER_API_KEY
OPENROUTER_MODEL=google/gemma-3-4b-it
```

The anon key is safe in the browser. The service role key and the OpenRouter key stay on the server.

## Local

```powershell
py -m pip install -r requirements.txt
py server.py
```

Open http://127.0.0.1:8080

Add a technician, a customer, then a job. Type a new complaint for that phone and press **Ask Gemma**.

`py check.py` checks that a decision is rejected when it cites a job that does not exist, skips an unpaid job, or names someone who is not on the floor.

## Render

`render.yaml` is a web service named `dobara`. Connect the GitHub repo, add the five environment variables, and deploy. The start command is `uvicorn server:app --host 0.0.0.0 --port $PORT`.
