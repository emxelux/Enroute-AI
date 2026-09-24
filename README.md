# Enroute-AI - AI Travel Planner Agent

## How to run?

*This assumes that you already have uv installed globally using pip install uv*

1. Create an environment with the following
```bash
uv init
uv venv
source .venv/scripts/activate
```
2. Install the dependencies

```bash 

uv add -r requirements.txt
```

3. Start the server
   ```bash

   uvicorn main:app --reload
   ```

###### You can now access the api swagger documentation at https://localhost:8000/docs
