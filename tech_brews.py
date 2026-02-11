import streamlit as st
import requests
import json
import re

SERPER_API_KEY = st.secrets["SERPER_API_KEY"]
OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
DEFAULT_NOTION_URL = "https://techbrews.notion.site/Welcome-to-Tech-Brews-a9805827439d46f3b9d60a10bf39ebda"

MAX_LINKS_TO_FOLLOW = 5

class NotionPageReader:
    def __init__(self, serper_key, openrouter_key):
        self.serper_key = serper_key
        self.openrouter_key = openrouter_key
        self.visited_urls = set()
        self.page_contents = {}
        
    def extract_page_content(self, url):
        if url in self.visited_urls:
            return self.page_contents.get(url, "")
        
        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    'X-API-KEY': self.serper_key,
                    'Content-Type': 'application/json'
                },
                json={"q": f"site:{url}"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                content = ""
                if "organic" in data:
                    for result in data["organic"][:3]:
                        content += f"\n\n{result.get('title', '')}\n{result.get('snippet', '')}\n"
                
                self.visited_urls.add(url)
                self.page_contents[url] = content
                return content
            
            return ""
                
        except Exception as e:
            st.error(f"Error extracting content: {str(e)}")
            return ""
    
    def extract_notion_links(self, text):
        pattern = r'https://(?:www\.)?notion\.(?:site|so)/[^\s\)"\']+'
        return list(set(re.findall(pattern, text)))
    
    def ask_llm_for_links(self, question, main_content, available_links):
        if not available_links:
            return []
        
        prompt = f"""Given this question: "{question}"

Available links:
{chr(10).join([f"- {link}" for link in available_links[:20]])}

Return ONLY a JSON array of the 3 most relevant URLs: ["url1", "url2", "url3"]
If none needed, return: []"""

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/techbrews",
                    "X-Title": "TechBrews Assistant"
                },
                json={
                    "model": "google/gemini-flash-1.5",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content'].strip()
                if content.startswith('['):
                    return json.loads(content)[:MAX_LINKS_TO_FOLLOW]
            return []
                
        except Exception:
            return []
    
    def answer_question(self, question, url, follow_links=True):
        with st.spinner("Reading main page..."):
            main_content = self.extract_page_content(url)
        
        if not main_content:
            return "Couldn't extract content from the page."
        
        all_content = f"=== Main Page ===\n{main_content}\n"
        
        if follow_links:
            links = self.extract_notion_links(main_content)
            
            if links:
                relevant_links = self.ask_llm_for_links(question, main_content, links)
                
                if relevant_links:
                    st.info(f"Following {len(relevant_links)} relevant links...")
                    
                    for link in relevant_links:
                        link_content = self.extract_page_content(link)
                        if link_content:
                            all_content += f"\n\n=== {link} ===\n{link_content}\n"
        
        with st.spinner("Generating answer..."):
            return self.generate_answer(question, all_content)
    
    def generate_answer(self, question, context):
        prompt = f"""Based on this content from Tech Brews Notion pages, answer: "{question}"

Content:
{context}

Provide a clear, concise answer with relevant details."""

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/techbrews",
                    "X-Title": "TechBrews Assistant"
                },
                json={
                    "model": "google/gemini-flash-1.5",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            
            error_msg = f"API Error {response.status_code}"
            try:
                error_detail = response.json()
                if 'error' in error_detail:
                    error_msg += f": {error_detail['error'].get('message', '')}"
            except:
                pass
            return error_msg
                
        except Exception as e:
            return f"Error: {str(e)}"


def main():
    st.set_page_config(
        page_title="Tech Brews Assistant",
        page_icon="☕",
        layout="wide"
    )
    
    st.title("☕ Tech Brews Assistant")
    st.markdown("Ask questions about the Tech Brews community")
    
    reader = NotionPageReader(SERPER_API_KEY, OPENROUTER_API_KEY)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        question = st.text_input(
            "Your question:",
            placeholder="What is Tech Brews all about?",
        )
    
    with col2:
        follow_links = st.checkbox("Follow links", value=True)
    
    if question:
        answer = reader.answer_question(question, DEFAULT_NOTION_URL, follow_links)
        
        st.markdown("### Answer")
        st.markdown(answer)
        
        if reader.visited_urls:
            with st.expander("Sources"):
                for url in reader.visited_urls:
                    st.text(url)


if __name__ == "__main__":
    main()
