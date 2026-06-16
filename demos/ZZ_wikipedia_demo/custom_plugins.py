import aiohttp
from pydantic import BaseModel
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from sk_agents.ska_types import BasePlugin


class SearchResultPage(BaseModel):
    page_key: str
    title: str
    excerpt: str
    description: str


class Page(BaseModel):
    page_key: str
    title: str
    content: str


class WikipediaPlugin(BasePlugin):
    @kernel_function(
        description="Search for Wikipedia pages related to a given query and return the results."
    )
    async def search(self, search_query: str, num_results: int = 2) -> list[SearchResultPage]:
        search_url = f"https://api.wikimedia.org/core/v1/wikipedia/en/search/page?q={search_query}&limit={num_results}"
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url) as response:
                response.raise_for_status()
                data = await response.json()
                pages = [
                    SearchResultPage(
                        page_key=page["key"],
                        title=page["title"],
                        excerpt=page["excerpt"],
                        description=page["description"],
                    )
                    for page in data["pages"]
                ]
                return pages

    @kernel_function(description="Retrieve a Wikipedia page's content")
    async def get_page_content(self, page_key: str) -> Page:
        page_url = f"https://api.wikimedia.org/core/v1/wikipedia/en/page/{page_key}"
        async with aiohttp.ClientSession() as session:
            async with session.get(page_url) as response:
                response.raise_for_status()
                data = await response.json()
                return Page(page_key=data["key"], title=data["title"], content=data["source"])
