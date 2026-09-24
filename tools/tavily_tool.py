from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


def tavily_search(query):
    response = client.search(
        query=query,
        max_results=5
    )
    

    results = []
    for i, r in enumerate(response["results"], 1):
        title = r.get("title", "unknown")
        url = r.get("url", "")
        content = r.get("content", "")

        results.append(f"""
        **{title}**
        *source url*: {url}
        \n\n\n
        {content}
        """)
    return "\n\n".join(results)


