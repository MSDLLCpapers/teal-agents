from semantic_kernel.functions.kernel_function_decorator import kernel_function
from sk_agents.ska_types import BasePlugin


class GoogleSearchPlugin(BasePlugin):
    @kernel_function(
        description="Search Google for information, returns results with a snippet and body content"
    )
    def google_search(self, query: str, num_results: int = 2, max_chars: int = 500) -> list:  # type: ignore[type-arg]
        import os
        import time

        import requests
        from bs4 import BeautifulSoup
        from dotenv import load_dotenv

        load_dotenv()

        api_key = os.getenv("GOOGLE_API_KEY")
        search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

        if not api_key or not search_engine_id:
            raise ValueError(
                "API key or Search Engine ID not found in environment variables"
            )

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query,
            "num": num_results,
        }

        response = requests.get(url, params=params)  # type: ignore[arg-type]

        if response.status_code != 200:
            print(response.json())
            raise Exception(f"Error in API request: {response.status_code}")

        results = response.json().get("items", [])

        def get_page_content(url: str) -> str:
            try:
                response = requests.get(url, timeout=10)
                soup = BeautifulSoup(response.content, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                words = text.split()
                content = ""
                for word in words:
                    if len(content) + len(word) + 1 > max_chars:
                        break
                    content += " " + word
                return content.strip()
            except Exception as e:
                print(f"Error fetching {url}: {str(e)}")
                return ""

        enriched_results = []
        for item in results:
            body = get_page_content(item["link"])
            enriched_results.append(
                {
                    "title": item["title"],
                    "link": item["link"],
                    "snippet": item["snippet"],
                    "body": body,
                }
            )
            time.sleep(1)  # Be respectful to the servers

        return enriched_results
