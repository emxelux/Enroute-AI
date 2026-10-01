from tavily import TavilyClient
from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

# @tool
def tavily_search(query: str) -> str:
    """Search the web for information.
    
    Args:
        query: The search string query to look up on the web.
    """
    if not query or not isinstance(query, str):
        return "Error: Invalid query provided."
        
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